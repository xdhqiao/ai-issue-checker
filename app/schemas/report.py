from datetime import datetime

from pydantic import BaseModel


class ReportIssue(BaseModel):
    id: int
    check: str
    function: str
    line: int
    col: int
    detail: str
    severity_color: str
    confidence: float | None
    comment: str


class ReportFile(BaseModel):
    id: str
    file_name: str
    file_author: str
    state: int
    status: str
    failure_message: str
    llm_call_count: int
    llm_prompt_tokens: int
    llm_completion_tokens: int
    llm_total_tokens: int
    llm_elapsed_ms: int
    process_time: int
    issues: list[ReportIssue]


class ReportSummary(BaseModel):
    file_num: int
    issue_num: int
    red_issue_num: int
    orange_issue_num: int
    author_num: int


class ReportProgress(BaseModel):
    percentage: int
    reviewed_file_num: int
    total_file_num: int
    pending_file_num: int
    running_file_num: int
    failed_file_num: int


class ReportMetrics(BaseModel):
    llm_call_count: int
    llm_prompt_tokens: int
    llm_completion_tokens: int
    llm_total_tokens: int
    llm_elapsed_ms: int
    process_time: int


class TaskReportResponse(BaseModel):
    task_id: str
    project_id: str
    review_version: str
    task_type: int
    state: int
    status: str
    completion_status: str
    failure_message: str
    create_time: datetime
    update_time: datetime
    summary: ReportSummary
    progress: ReportProgress
    metrics: ReportMetrics
    authors: list[str]
    files: list[ReportFile]
    total_files: int
    page: int
    page_size: int
    total_pages: int


class SourceResponse(BaseModel):
    file_id: str
    file_name: str
    total_lines: int
    lines: list[str]
