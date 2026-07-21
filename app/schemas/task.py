from datetime import datetime
from pathlib import PurePosixPath
import re

from pydantic import BaseModel, Field, field_validator, model_validator

from app.common.constants import state_label
from app.models.task import TaskModel


class PolyspaceIssueCreate(BaseModel):
    id: int
    check: str = Field(min_length=1, max_length=500)
    function: str = Field(default="", max_length=1000)
    line: int = Field(ge=1)
    col: int = Field(ge=0)
    detail: str = Field(min_length=1)
    severity_color: str = Field(min_length=1, max_length=50)
    comment: str = ""

    @field_validator("check", "function", "detail", "severity_color", "comment")
    @classmethod
    def strip_text(cls, value: str) -> str:
        return value.strip()


class PolyspaceFileCreate(BaseModel):
    file_name: str = Field(min_length=1, max_length=2000)
    file_author: str = Field(default="", max_length=500)
    issues: list[PolyspaceIssueCreate] = Field(default_factory=list)

    @field_validator("file_name")
    @classmethod
    def validate_file_name(cls, value: str) -> str:
        normalized = value.replace("\\", "/").strip()
        while normalized.startswith("./"):
            normalized = normalized[2:]
        path = PurePosixPath(normalized)
        if not normalized or path.is_absolute() or re.match(r"^[A-Za-z]:", normalized) or ".." in path.parts:
            raise ValueError("file_name must be a repository-relative path")
        return normalized

    @field_validator("file_author")
    @classmethod
    def strip_author(cls, value: str) -> str:
        return value.strip()

    @model_validator(mode="after")
    def unique_issue_ids(self):
        ids = [issue.id for issue in self.issues]
        if len(ids) != len(set(ids)):
            raise ValueError("issue ids must be unique within a file")
        return self


class TaskCreate(BaseModel):
    project_id: str = Field(min_length=1, max_length=500)
    review_version: str = Field(min_length=1, max_length=500)
    version_code_path: str = Field(min_length=1, max_length=4000)
    files: list[PolyspaceFileCreate] = Field(default_factory=list)

    @field_validator("project_id", "review_version", "version_code_path")
    @classmethod
    def strip_required(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("value cannot be blank")
        return value

    @model_validator(mode="after")
    def unique_file_names(self):
        names = [item.file_name for item in self.files]
        if len(names) != len(set(names)):
            raise ValueError("file_name values must be unique within a task")
        return self


class TaskResponse(BaseModel):
    id: str
    project_id: str
    review_version: str
    version_code_path: str
    task_type: int
    state: int
    status: str
    completion_status: str
    failure_message: str
    file_num: int
    reviewed_file_num: int
    issue_num: int
    red_issue_num: int
    orange_issue_num: int
    author_num: int
    llm_prompt_tokens: int
    llm_completion_tokens: int
    llm_total_tokens: int
    llm_call_count: int
    llm_elapsed_ms: int
    process_time: int
    retry_count: int
    create_time: datetime
    update_time: datetime

    @classmethod
    def from_model(cls, task: TaskModel) -> "TaskResponse":
        return cls(
            id=str(task.id),
            project_id=task.project_id,
            review_version=task.review_version,
            version_code_path=task.version_code_path,
            task_type=int(task.task_type or 1),
            state=int(task.state or 0),
            status=state_label(int(task.state or 0)),
            completion_status=task.completion_status or "",
            failure_message=task.failure_message or "",
            file_num=int(task.file_num or 0),
            reviewed_file_num=int(task.reviewed_file_num or 0),
            issue_num=int(task.issue_num or 0),
            red_issue_num=int(task.red_issue_num or 0),
            orange_issue_num=int(task.orange_issue_num or 0),
            author_num=int(task.author_num or 0),
            llm_prompt_tokens=int(task.llm_prompt_tokens or 0),
            llm_completion_tokens=int(task.llm_completion_tokens or 0),
            llm_total_tokens=int(task.llm_total_tokens or 0),
            llm_call_count=int(task.llm_call_count or 0),
            llm_elapsed_ms=int(task.llm_elapsed_ms or 0),
            process_time=int(task.process_time or 0),
            retry_count=int(task.retry_count or 0),
            create_time=task.create_time,
            update_time=task.update_time,
        )


class TaskListResponse(BaseModel):
    items: list[TaskResponse]
    total: int
