from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import timedelta
from pathlib import Path

from app.common.constants import State
from app.core.config import Settings, get_settings
from app.models.code_file import CodeFileModel
from app.models.task import TaskModel, utc_now
from app.services.issue_confirmation import IssueConfirmationService
from app.services.notification import ReviewNotificationService


logger = logging.getLogger(__name__)


class LeaseLostError(RuntimeError):
    pass


class ReviewTaskService:
    def __init__(self, settings: Settings | None = None, lease_token: str = "") -> None:
        self.settings = settings or get_settings()
        self.lease_token = lease_token

    def review_task(self, task: TaskModel) -> TaskModel:
        started = time.monotonic()
        try:
            self._assert_lease(task.id)
            version_root = self._version_root(task.version_code_path)
            pending_ids = [
                str(item.id)
                for item in CodeFileModel.objects(task_id=str(task.id), state__ne=State.COMPLETED.value).only("id")
            ]
            if pending_ids:
                concurrency = min(max(1, self.settings.file_concurrency), len(pending_ids))
                with ThreadPoolExecutor(max_workers=concurrency, thread_name_prefix="issue-confirm") as executor:
                    futures = [executor.submit(self._review_file, file_id, str(task.id), version_root) for file_id in pending_ids]
                    for future in as_completed(futures):
                        try:
                            future.result()
                        except LeaseLostError:
                            raise
                        except Exception:
                            logger.exception("File issue confirmation failed: task_id=%s", task.id)
            self._assert_lease(task.id)
            task = self._finalize(task.id, int((time.monotonic() - started) * 1000))
            if task.state == State.COMPLETED.value and not task.completion_email_sent:
                try:
                    ReviewNotificationService(self.settings).send_review_completed(task)
                except Exception:
                    logger.exception("Completion email failed: task_id=%s", task.id)
                else:
                    TaskModel.objects(id=task.id).update_one(set__completion_email_sent=True, set__update_time=utc_now())
                    task.completion_email_sent = True
            return task
        except LeaseLostError:
            raise
        except Exception as exc:
            logger.exception("Task issue confirmation failed: task_id=%s", task.id)
            return self._fail_task(task.id, exc, int((time.monotonic() - started) * 1000))

    def _review_file(self, file_id: str, task_id: str, version_root: Path) -> None:
        self._assert_lease(task_id)
        claimed = CodeFileModel.objects(id=file_id, task_id=task_id, state__ne=State.COMPLETED.value).modify(
            new=True,
            set__state=State.RUNNING.value,
            set__completion_status="running",
            set__failure_message="",
            set__task_lease_token=self.lease_token,
            set__update_time=utc_now(),
        )
        if claimed is None:
            return
        started = time.monotonic()
        try:
            result = IssueConfirmationService(self.settings).confirm(claimed, version_root)
            self._assert_lease(task_id)
            for index, confidence in enumerate(result.confidences):
                claimed.issues[index].confidence = confidence
            updated = CodeFileModel.objects(id=file_id, task_id=task_id, task_lease_token=self.lease_token).update_one(
                set__issues=claimed.issues,
                set__state=State.COMPLETED.value,
                set__completion_status="completed",
                set__failure_message="",
                set__llm_prompt_tokens=result.prompt_tokens,
                set__llm_completion_tokens=result.completion_tokens,
                set__llm_total_tokens=result.total_tokens,
                set__llm_call_count=result.call_count,
                set__llm_elapsed_ms=result.elapsed_ms,
                set__process_time=int((time.monotonic() - started) * 1000),
                set__model_rounds=result.model_rounds,
                set__tool_calls=result.tool_calls,
                set__update_time=utc_now(),
            )
            if not updated:
                raise LeaseLostError("file checkpoint lease was replaced")
        except LeaseLostError:
            raise
        except Exception as exc:
            CodeFileModel.objects(id=file_id, task_id=task_id, task_lease_token=self.lease_token).update_one(
                set__state=State.FAILED.value,
                set__completion_status="failed",
                set__failure_message=f"{type(exc).__name__}: {exc}",
                set__process_time=int((time.monotonic() - started) * 1000),
                set__update_time=utc_now(),
            )
            raise

    def _finalize(self, task_id: object, run_ms: int) -> TaskModel:
        task = TaskModel.objects(id=task_id).first()
        if task is None:
            raise LeaseLostError("task was deleted")
        self._assert_lease(task.id)
        files = list(CodeFileModel.objects(task_id=str(task.id)))
        failed = [item for item in files if item.state != State.COMPLETED.value]
        task.reviewed_file_num = sum(1 for item in files if item.state == State.COMPLETED.value)
        task.llm_prompt_tokens = sum(int(item.llm_prompt_tokens or 0) for item in files)
        task.llm_completion_tokens = sum(int(item.llm_completion_tokens or 0) for item in files)
        task.llm_total_tokens = sum(int(item.llm_total_tokens or 0) for item in files)
        task.llm_call_count = sum(int(item.llm_call_count or 0) for item in files)
        task.llm_elapsed_ms = sum(int(item.llm_elapsed_ms or 0) for item in files)
        task.process_time = int(task.process_time or 0) + run_ms
        if failed:
            task.state = State.FAILED.value
            task.completion_status = "failed"
            task.retry_count = int(task.retry_count or 0) + 1
            task.failure_message = f"{len(failed)} file(s) failed; scheduler will retry unfinished files"
            if task.retry_count < max(1, self.settings.scheduler_max_task_retries):
                task.next_retry_time = utc_now() + timedelta(seconds=max(0, self.settings.scheduler_retry_backoff_seconds))
            else:
                task.next_retry_time = None
        else:
            task.state = State.COMPLETED.value
            task.completion_status = "completed"
            task.failure_message = ""
            task.next_retry_time = None
        query = TaskModel.objects(id=task.id)
        if self.lease_token:
            query = query.filter(lease_token=self.lease_token)
        persisted = query.modify(
            new=True,
            set__reviewed_file_num=task.reviewed_file_num,
            set__llm_prompt_tokens=task.llm_prompt_tokens,
            set__llm_completion_tokens=task.llm_completion_tokens,
            set__llm_total_tokens=task.llm_total_tokens,
            set__llm_call_count=task.llm_call_count,
            set__llm_elapsed_ms=task.llm_elapsed_ms,
            set__process_time=task.process_time,
            set__state=task.state,
            set__completion_status=task.completion_status,
            set__retry_count=task.retry_count,
            set__failure_message=task.failure_message,
            set__next_retry_time=task.next_retry_time,
            set__lease_owner="",
            set__lease_token="",
            set__lease_expires_at=None,
            set__update_time=utc_now(),
        )
        if persisted is None:
            raise LeaseLostError("task lease changed before final checkpoint")
        return persisted

    def _fail_task(self, task_id: object, exc: Exception, run_ms: int) -> TaskModel:
        query = TaskModel.objects(id=task_id)
        if self.lease_token:
            query = query.filter(lease_token=self.lease_token)
        task = query.first()
        if task is None:
            raise LeaseLostError("task lease was replaced")
        retry_count = int(task.retry_count or 0) + 1
        next_retry_time = None
        if retry_count < max(1, self.settings.scheduler_max_task_retries):
            next_retry_time = utc_now() + timedelta(seconds=max(0, self.settings.scheduler_retry_backoff_seconds))
        persisted = query.modify(
            new=True,
            set__state=State.FAILED.value,
            set__completion_status="failed",
            set__failure_message=f"{type(exc).__name__}: {exc}",
            set__retry_count=retry_count,
            set__process_time=int(task.process_time or 0) + run_ms,
            set__next_retry_time=next_retry_time,
            set__lease_owner="",
            set__lease_token="",
            set__lease_expires_at=None,
            set__update_time=utc_now(),
        )
        if persisted is None:
            raise LeaseLostError("task lease changed before failure checkpoint")
        return persisted

    def _assert_lease(self, task_id: object) -> None:
        task = TaskModel.objects(id=task_id).only("lease_token").first()
        if task is None:
            raise LeaseLostError("task was deleted or replaced")
        if self.lease_token and task.lease_token != self.lease_token:
            raise LeaseLostError("task lease is no longer owned by this worker")

    def _version_root(self, configured_path: str) -> Path:
        root = Path(configured_path).resolve()
        if not root.is_dir():
            raise FileNotFoundError(f"version_code_path does not exist or is not a directory: {configured_path}")
        if self.settings.code_repository_root:
            allowed = Path(self.settings.code_repository_root).resolve()
            try:
                root.relative_to(allowed)
            except ValueError as exc:
                raise ValueError("version_code_path is outside CODE_REPOSITORY_ROOT") from exc
        return root
