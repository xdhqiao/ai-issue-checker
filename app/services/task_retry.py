from __future__ import annotations

import uuid
from datetime import timedelta

from mongoengine import ValidationError

from app.common.constants import State
from app.core.config import Settings, get_settings
from app.core.exceptions import ConflictError, NotFoundError
from app.models.code_file import CodeFileModel
from app.models.task import TaskModel, utc_now


class TaskRetryService:
    """Restart only unfinished files after automatic retries are exhausted."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def retry_failed_task(self, task_id: str) -> TaskModel:
        try:
            task = TaskModel.objects(id=task_id).first()
        except ValidationError:
            task = None
        if task is None:
            raise NotFoundError("Task not found")
        max_automatic_retries = max(0, self.settings.scheduler_max_task_retries)
        if (
            task.state != State.FAILED.value
            or task.next_retry_time is not None
            or int(task.retry_count or 0) <= max_automatic_retries
        ):
            raise ConflictError("Task is not available for manual retry")

        now = utc_now()
        preparation_token = f"manual-retry-{uuid.uuid4()}"
        prepared = TaskModel.objects(
            id=task.id,
            state=State.FAILED.value,
            next_retry_time=None,
            retry_count__gt=max_automatic_retries,
        ).modify(
            new=True,
            set__state=State.PENDING.value,
            set__completion_status="pending",
            set__failure_message="",
            set__next_retry_time=None,
            set__lease_owner="manual-retry",
            set__lease_token=preparation_token,
            set__lease_expires_at=now + timedelta(seconds=max(10, self.settings.scheduler_lease_seconds)),
            set__update_time=now,
        )
        if prepared is None:
            raise ConflictError("Task state changed before manual retry")

        CodeFileModel.objects(
            task_id=str(task.id),
            state__ne=State.COMPLETED.value,
        ).update(
            set__state=State.PENDING.value,
            set__completion_status="pending",
            set__failure_message="",
            set__task_lease_token="",
            set__update_time=now,
        )

        released = TaskModel.objects(id=task.id, lease_token=preparation_token).modify(
            new=True,
            set__lease_owner="",
            set__lease_token="",
            set__lease_expires_at=None,
            set__heartbeat_time=None,
            set__update_time=utc_now(),
        )
        if released is None:
            raise ConflictError("Task retry preparation lease was replaced")
        return released
