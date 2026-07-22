from math import ceil

from mongoengine import ValidationError

from app.common.constants import State, state_label
from app.core.exceptions import NotFoundError
from app.models.code_file import CodeFileModel
from app.models.task import TaskModel
from app.schemas.report import ReportFile, ReportIssue, ReportMetrics, ReportProgress, ReportSummary, TaskReportResponse


class TaskReportService:
    def find_task(self, task_id: str) -> TaskModel:
        try:
            task = TaskModel.objects(id=task_id).first()
        except ValidationError:
            task = None
        if task is None:
            raise NotFoundError("Task not found")
        return task

    def find_task_by_project_version(self, project_id: str, review_version: str) -> TaskModel:
        task = TaskModel.objects(project_id=project_id, review_version=review_version).first()
        if task is None:
            raise NotFoundError("Task not found")
        return task

    def get_report_by_project_version(
        self,
        project_id: str,
        review_version: str,
        author: str = "",
        page: int = 1,
        page_size: int = 20,
    ) -> TaskReportResponse:
        task = self.find_task_by_project_version(project_id, review_version)
        return self.get_report(str(task.id), author=author, page=page, page_size=page_size)

    def get_report(self, task_id: str, author: str = "", page: int = 1, page_size: int = 20) -> TaskReportResponse:
        task = self.find_task(task_id)
        all_files = list(CodeFileModel.objects(task_id=str(task.id)).order_by("file_name"))
        authors = sorted({item.file_author.strip() for item in all_files if item.file_author.strip()})
        filtered = [item for item in all_files if not author or item.file_author == author]
        page_files = filtered[(page - 1) * page_size : page * page_size]
        state_counts = {state: sum(1 for item in all_files if item.state == state) for state in range(4)}
        percentage = round(state_counts[State.COMPLETED.value] * 100 / len(all_files)) if all_files else (100 if task.state == State.COMPLETED.value else 0)
        return TaskReportResponse(
            task_id=str(task.id),
            project_id=task.project_id,
            review_version=task.review_version,
            task_type=int(task.task_type or 1),
            state=int(task.state or 0),
            status=state_label(int(task.state or 0)),
            completion_status=task.completion_status or "",
            failure_message=task.failure_message or "",
            create_time=task.create_time,
            update_time=task.update_time,
            summary=ReportSummary(
                file_num=int(task.file_num or 0), issue_num=int(task.issue_num or 0),
                red_issue_num=int(task.red_issue_num or 0), orange_issue_num=int(task.orange_issue_num or 0),
                author_num=int(task.author_num or 0),
            ),
            progress=ReportProgress(
                percentage=percentage,
                reviewed_file_num=state_counts[State.COMPLETED.value],
                total_file_num=len(all_files),
                pending_file_num=state_counts[State.PENDING.value],
                running_file_num=state_counts[State.RUNNING.value],
                failed_file_num=state_counts[State.FAILED.value],
            ),
            metrics=ReportMetrics(
                llm_call_count=int(task.llm_call_count or 0), llm_prompt_tokens=int(task.llm_prompt_tokens or 0),
                llm_completion_tokens=int(task.llm_completion_tokens or 0), llm_total_tokens=int(task.llm_total_tokens or 0),
                llm_elapsed_ms=int(task.llm_elapsed_ms or 0), process_time=int(task.process_time or 0),
            ),
            authors=authors,
            files=[self._file(item) for item in page_files],
            total_files=len(filtered),
            page=page,
            page_size=page_size,
            total_pages=ceil(len(filtered) / page_size) if filtered else 0,
        )

    @staticmethod
    def _file(item: CodeFileModel) -> ReportFile:
        return ReportFile(
            id=str(item.id), file_name=item.file_name, file_author=item.file_author or "",
            state=int(item.state or 0), status=state_label(int(item.state or 0)), failure_message=item.failure_message or "",
            llm_call_count=int(item.llm_call_count or 0), llm_prompt_tokens=int(item.llm_prompt_tokens or 0),
            llm_completion_tokens=int(item.llm_completion_tokens or 0), llm_total_tokens=int(item.llm_total_tokens or 0),
            llm_elapsed_ms=int(item.llm_elapsed_ms or 0), process_time=int(item.process_time or 0),
            issues=[
                ReportIssue(
                    id=issue.issue_id, check=issue.check, function=issue.function or "", line=issue.line, col=issue.col,
                    detail=issue.detail, severity_color=issue.severity_color, confidence=issue.confidence, comment=issue.comment or "",
                )
                for issue in item.issues
            ],
        )
