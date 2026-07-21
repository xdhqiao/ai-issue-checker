from __future__ import annotations

from threading import Lock

from mongoengine import NotUniqueError

from app.common.constants import State, TaskType
from app.models.code_file import CodeFileModel, Issue
from app.models.task import TaskModel, utc_now
from app.schemas.task import TaskCreate


_submission_lock = Lock()


class TaskSubmissionService:
    """Replace one project/version atomically enough for a single API deployment.

    A unique MongoDB index is the cross-process guard. The local lock ensures that
    file cleanup and recreation cannot interleave inside one application process.
    """

    def submit(self, payload: TaskCreate) -> TaskModel:
        with _submission_lock:
            previous = TaskModel.objects(
                project_id=payload.project_id,
                review_version=payload.review_version,
            ).first()
            if previous is not None:
                CodeFileModel.objects(task_id=str(previous.id)).delete()
                previous.delete()

            colors = [issue.severity_color.strip().lower() for file in payload.files for issue in file.issues]
            authors = {file.file_author.strip() for file in payload.files if file.file_author.strip()}
            task = TaskModel(
                project_id=payload.project_id,
                review_version=payload.review_version,
                version_code_path=payload.version_code_path,
                task_type=TaskType.POLYSPACE_CONFIRMATION.value,
                state=State.PENDING.value,
                completion_status="pending",
                file_num=len(payload.files),
                issue_num=len(colors),
                red_issue_num=colors.count("red"),
                orange_issue_num=colors.count("orange"),
                author_num=len(authors),
                create_time=utc_now(),
                update_time=utc_now(),
            )
            try:
                task.save(force_insert=True)
            except NotUniqueError:
                # A second server won the same project/version race. Remove the
                # winner's data and let this newest request become authoritative.
                winner = TaskModel.objects(
                    project_id=payload.project_id,
                    review_version=payload.review_version,
                ).first()
                if winner is not None:
                    CodeFileModel.objects(task_id=str(winner.id)).delete()
                    winner.delete()
                task.save(force_insert=True)

            code_files = []
            for item in payload.files:
                code_files.append(
                    CodeFileModel(
                        task_id=str(task.id),
                        project_id=task.project_id,
                        review_version=task.review_version,
                        file_name=item.file_name,
                        file_author=item.file_author,
                        state=State.PENDING.value,
                        completion_status="pending",
                        issues=[
                            Issue(
                                issue_id=issue.id,
                                check=issue.check,
                                function=issue.function,
                                line=issue.line,
                                col=issue.col,
                                detail=issue.detail,
                                severity_color=issue.severity_color,
                                comment=issue.comment,
                            )
                            for issue in item.issues
                        ],
                    )
                )
            if code_files:
                try:
                    CodeFileModel.objects.insert(code_files, load_bulk=False)
                except Exception:
                    CodeFileModel.objects(task_id=str(task.id)).delete()
                    task.delete()
                    raise
            return task
