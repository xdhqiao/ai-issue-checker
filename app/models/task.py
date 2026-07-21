from datetime import datetime, timezone

from mongoengine import BooleanField, DateTimeField, Document, IntField, StringField

from app.common.constants import State, TaskType


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class TaskModel(Document):
    meta = {
        "collection": "ai_issue_checker_task",
        "indexes": [
            {"fields": ["project_id", "review_version"], "unique": True},
            ("state", "next_retry_time", "create_time"),
            ("task_type", "state", "-create_time"),
            "-create_time",
        ],
    }

    project_id = StringField(required=True)
    review_version = StringField(required=True)
    version_code_path = StringField(required=True)
    task_type = IntField(required=True, default=TaskType.POLYSPACE_CONFIRMATION.value)
    state = IntField(required=True, default=State.PENDING.value)
    completion_status = StringField(default="pending")
    failure_message = StringField(default="")
    file_num = IntField(default=0)
    reviewed_file_num = IntField(default=0)
    issue_num = IntField(default=0)
    red_issue_num = IntField(default=0)
    orange_issue_num = IntField(default=0)
    author_num = IntField(default=0)
    llm_prompt_tokens = IntField(default=0)
    llm_completion_tokens = IntField(default=0)
    llm_total_tokens = IntField(default=0)
    llm_call_count = IntField(default=0)
    llm_elapsed_ms = IntField(default=0)
    process_time = IntField(default=0)
    retry_count = IntField(default=0)
    next_retry_time = DateTimeField()
    lease_owner = StringField(default="")
    lease_token = StringField(default="")
    lease_expires_at = DateTimeField()
    heartbeat_time = DateTimeField()
    last_start_time = DateTimeField()
    completion_email_sent = BooleanField(default=False)
    create_time = DateTimeField(default=utc_now, required=True)
    update_time = DateTimeField(default=utc_now, required=True)

