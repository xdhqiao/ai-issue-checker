from datetime import datetime, timezone

from mongoengine import DateTimeField, Document, EmbeddedDocument, EmbeddedDocumentField, FloatField, IntField, ListField, StringField

from app.common.constants import State


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Issue(EmbeddedDocument):
    issue_id = IntField(required=True)
    check = StringField(required=True)
    function = StringField(default="")
    line = IntField(required=True)
    col = IntField(required=True)
    detail = StringField(required=True)
    severity_color = StringField(required=True)
    comment = StringField(default="")
    confidence = FloatField()


class ModelRoundTrace(EmbeddedDocument):
    round_index = IntField(required=True)
    model = StringField(default="")
    prompt_tokens = IntField(default=0)
    completion_tokens = IntField(default=0)
    total_tokens = IntField(default=0)
    elapsed_ms = IntField(default=0)
    finish_reason = StringField(default="")
    error_message = StringField(default="")
    create_time = DateTimeField(default=utc_now)


class ToolCallTrace(EmbeddedDocument):
    round_index = IntField(required=True)
    tool_call_id = StringField(default="")
    tool_name = StringField(default="")
    elapsed_ms = IntField(default=0)
    success = IntField(default=1)
    error_message = StringField(default="")
    create_time = DateTimeField(default=utc_now)


class CodeFileModel(Document):
    meta = {
        "collection": "ai_issue_checker_code_file",
        "indexes": [("task_id", "file_name"), ("task_id", "state"), ("task_id", "file_author")],
    }

    task_id = StringField(required=True)
    project_id = StringField(required=True)
    review_version = StringField(required=True)
    file_name = StringField(required=True)
    file_author = StringField(default="")
    state = IntField(required=True, default=State.PENDING.value)
    completion_status = StringField(default="pending")
    failure_message = StringField(default="")
    issues = ListField(EmbeddedDocumentField(Issue), default=list)
    llm_prompt_tokens = IntField(default=0)
    llm_completion_tokens = IntField(default=0)
    llm_total_tokens = IntField(default=0)
    llm_call_count = IntField(default=0)
    llm_elapsed_ms = IntField(default=0)
    process_time = IntField(default=0)
    model_rounds = ListField(EmbeddedDocumentField(ModelRoundTrace), default=list)
    tool_calls = ListField(EmbeddedDocumentField(ToolCallTrace), default=list)
    task_lease_token = StringField(default="")
    create_time = DateTimeField(default=utc_now, required=True)
    update_time = DateTimeField(default=utc_now, required=True)
