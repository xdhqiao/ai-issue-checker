from fastapi import APIRouter, Query, status
from mongoengine import ValidationError

from app.core.exceptions import NotFoundError
from app.models.code_file import CodeFileModel
from app.models.task import TaskModel
from app.schemas.task import TaskCreate, TaskListResponse, TaskResponse
from app.services.task_retry import TaskRetryService
from app.services.task_submission import TaskSubmissionService


router = APIRouter(tags=["tasks"])


@router.post("/api/tasks", response_model=TaskResponse, status_code=status.HTTP_201_CREATED)
@router.post("/tasks", response_model=TaskResponse, status_code=status.HTTP_201_CREATED, include_in_schema=False)
@router.post("/tasks/trigger", response_model=TaskResponse, status_code=status.HTTP_201_CREATED, include_in_schema=False)
def create_task(payload: TaskCreate) -> TaskResponse:
    return TaskResponse.from_model(TaskSubmissionService().submit(payload))


@router.get("/api/tasks", response_model=TaskListResponse)
def list_tasks(limit: int = Query(default=50, ge=1, le=200), offset: int = Query(default=0, ge=0)) -> TaskListResponse:
    query = TaskModel.objects.order_by("-create_time")
    return TaskListResponse(items=[TaskResponse.from_model(item) for item in query.skip(offset).limit(limit)], total=query.count())


@router.get("/api/tasks/{task_id}", response_model=TaskResponse)
def get_task(task_id: str) -> TaskResponse:
    try:
        task = TaskModel.objects(id=task_id).first()
    except ValidationError:
        task = None
    if task is None:
        raise NotFoundError("Task not found")
    return TaskResponse.from_model(task)


@router.post("/api/tasks/{task_id}/retry", response_model=TaskResponse)
def retry_task(task_id: str) -> TaskResponse:
    return TaskResponse.from_model(TaskRetryService().retry_failed_task(task_id))


@router.delete("/api/tasks/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_task(task_id: str) -> None:
    try:
        task = TaskModel.objects(id=task_id).first()
    except ValidationError:
        task = None
    if task is None:
        raise NotFoundError("Task not found")
    CodeFileModel.objects(task_id=str(task.id)).delete()
    task.delete()
