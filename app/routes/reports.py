from pathlib import Path

from fastapi import APIRouter, Query, Response
from fastapi.responses import FileResponse

from app.schemas.report import SourceResponse, TaskReportResponse
from app.services.report_service import TaskReportService
from app.services.source_service import SourceService


router = APIRouter(tags=["reports"])
PAGE = Path(__file__).resolve().parents[1] / "static" / "report.html"


@router.get("/reports/{task_id}.html", include_in_schema=False)
def report_page(task_id: str) -> FileResponse:
    TaskReportService().find_task(task_id)
    return FileResponse(PAGE, headers={"Cache-Control": "no-store"})


@router.get("/api/reports/tasks/{task_id}", response_model=TaskReportResponse)
def report_api(
    task_id: str,
    response: Response,
    author: str = Query(default="", max_length=500),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> TaskReportResponse:
    response.headers["Cache-Control"] = "no-store"
    return TaskReportService().get_report(task_id, author, page, page_size)


@router.get("/api/code-files/{file_id}/source", response_model=SourceResponse)
def source_api(file_id: str, response: Response) -> SourceResponse:
    response.headers["Cache-Control"] = "no-store"
    return SourceService().read(file_id)

