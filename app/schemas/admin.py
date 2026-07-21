from datetime import datetime
from typing import Literal

from pydantic import BaseModel


AdminTaskSortField = Literal[
    "project_id", "review_version", "task_type", "state", "red_issue_num", "issue_num", "create_time"
]
SortOrder = Literal["asc", "desc"]


class AdminTaskItem(BaseModel):
    id: str
    project_id: str
    review_version: str
    task_type: int
    state: int
    status: str
    red_issue_num: int
    issue_num: int
    create_time: datetime
    report_path: str


class AdminTaskListResponse(BaseModel):
    items: list[AdminTaskItem]
    total: int
    page: int
    page_size: int
    total_pages: int

