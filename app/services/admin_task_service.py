from datetime import datetime
from math import ceil
from urllib.parse import quote

from app.common.constants import state_label
from app.models.task import TaskModel
from app.schemas.admin import AdminTaskItem, AdminTaskListResponse, AdminTaskSortField, SortOrder


class AdminTaskService:
    def list_tasks(
        self,
        project_id: str = "",
        review_version: str = "",
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        task_type: int | None = None,
        state: int | None = None,
        sort_by: AdminTaskSortField = "create_time",
        sort_order: SortOrder = "desc",
        page: int = 1,
        page_size: int = 20,
    ) -> AdminTaskListResponse:
        query = TaskModel.objects
        if project_id.strip():
            query = query.filter(project_id__icontains=project_id.strip())
        if review_version.strip():
            query = query.filter(review_version__icontains=review_version.strip())
        if date_from is not None:
            query = query.filter(create_time__gte=date_from)
        if date_to is not None:
            query = query.filter(create_time__lte=date_to)
        if task_type is not None:
            query = query.filter(task_type=task_type)
        if state is not None:
            query = query.filter(state=state)
        total = query.count()
        order = f"-{'create_time' if sort_by == 'create_time' else sort_by}" if sort_order == "desc" else sort_by
        tasks = query.order_by(order).skip((page - 1) * page_size).limit(page_size)
        return AdminTaskListResponse(
            items=[
                AdminTaskItem(
                    id=str(task.id),
                    project_id=task.project_id,
                    review_version=task.review_version,
                    task_type=int(task.task_type or 1),
                    state=int(task.state or 0),
                    status=state_label(int(task.state or 0)),
                    red_issue_num=int(task.red_issue_num or 0),
                    issue_num=int(task.issue_num or 0),
                    create_time=task.create_time,
                    report_path=(
                        f"/reports/{quote(task.project_id, safe='')}/"
                        f"{quote(task.review_version, safe='')}.html"
                    ),
                )
                for task in tasks
            ],
            total=total,
            page=page,
            page_size=page_size,
            total_pages=ceil(total / page_size) if total else 0,
        )
