from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timedelta, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from mongoengine.queryset.visitor import Q

from app.common.constants import State
from app.core.config import Settings, get_settings
from app.models.task import TaskModel, utc_now
from app.services.review_service import ReviewTaskService


logger = logging.getLogger(__name__)


class ReviewScheduler:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.scheduler = AsyncIOScheduler()
        self.worker_id = f"issue-checker-{uuid.uuid4()}"
        self._active_future: asyncio.Task[None] | None = None
        self._active_task_id = ""
        self._active_lease_token = ""

    def start(self) -> None:
        if self.scheduler.running:
            return
        self.scheduler.add_job(
            self._safe_poll,
            "interval",
            seconds=max(1, self.settings.scheduler_interval_seconds),
            next_run_time=utc_now(),
            id="polyspace-issue-confirmation-dispatcher",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )
        self.scheduler.start()

    def shutdown(self) -> None:
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)

    async def wait_for_shutdown(self, timeout_seconds: int) -> bool:
        if self._active_future is None or self._active_future.done():
            return True
        try:
            await asyncio.wait_for(asyncio.shield(self._active_future), timeout=max(0, timeout_seconds))
            return True
        except TimeoutError:
            logger.warning("Issue confirmation worker did not stop within %s seconds", timeout_seconds)
            return False
        except (asyncio.CancelledError, Exception):
            return True

    async def run_once(self) -> None:
        await self._poll()

    async def _safe_poll(self) -> None:
        try:
            await self._poll()
        except Exception:
            logger.exception("Scheduler poll failed; the next interval will retry")

    async def _poll(self) -> None:
        if self._active_future is not None:
            if not self._active_future.done():
                await asyncio.to_thread(self._heartbeat)
                return
            try:
                self._active_future.result()
            except Exception:
                logger.exception("Task worker failed: task_id=%s", self._active_task_id)
            self._clear_active()

        task = await asyncio.to_thread(self.claim_next_task)
        if task is None:
            return
        self._active_task_id = str(task.id)
        self._active_lease_token = task.lease_token or ""
        self._active_future = asyncio.create_task(self._run_claimed_task(task))

    async def _run_claimed_task(self, task: TaskModel) -> None:
        service = ReviewTaskService(self.settings, lease_token=task.lease_token or "")
        await asyncio.to_thread(service.review_task, task)

    def claim_next_task(self) -> TaskModel | None:
        now = utc_now()
        candidates = TaskModel.objects(state__in=[State.PENDING.value, State.RUNNING.value, State.FAILED.value]).order_by("create_time")
        for candidate in candidates:
            if not self._eligible(candidate, now):
                continue
            token = str(uuid.uuid4())
            query = Q(id=candidate.id, state=candidate.state)
            if candidate.lease_token:
                query &= Q(lease_token=candidate.lease_token)
            else:
                query &= (Q(lease_token="") | Q(lease_token__exists=False))
            claimed = TaskModel.objects(query).modify(
                new=True,
                set__state=State.RUNNING.value,
                set__completion_status="running",
                set__lease_owner=self.worker_id,
                set__lease_token=token,
                set__lease_expires_at=now + timedelta(seconds=max(10, self.settings.scheduler_lease_seconds)),
                set__heartbeat_time=now,
                set__last_start_time=now,
                set__update_time=now,
            )
            if claimed is not None:
                return claimed
        return None

    def _eligible(self, task: TaskModel, now: datetime) -> bool:
        lease_expired = not task.lease_token or task.lease_expires_at is None or self._at_or_before(task.lease_expires_at, now)
        if task.state in {State.PENDING.value, State.RUNNING.value}:
            return lease_expired
        if task.state == State.FAILED.value and int(task.retry_count or 0) < max(1, self.settings.scheduler_max_task_retries):
            return lease_expired and (task.next_retry_time is None or self._at_or_before(task.next_retry_time, now))
        return False

    def _heartbeat(self) -> None:
        if not self._active_task_id or not self._active_lease_token:
            return
        now = utc_now()
        TaskModel.objects(id=self._active_task_id, lease_token=self._active_lease_token).update_one(
            set__heartbeat_time=now,
            set__lease_expires_at=now + timedelta(seconds=max(10, self.settings.scheduler_lease_seconds)),
            set__update_time=now,
        )

    def _clear_active(self) -> None:
        self._active_future = None
        self._active_task_id = ""
        self._active_lease_token = ""

    @staticmethod
    def _at_or_before(value: datetime, now: datetime) -> bool:
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value <= now

