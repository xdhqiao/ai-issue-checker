from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Query, Response
from fastapi.responses import FileResponse

from app.schemas.admin import (
    AdminTaskListResponse,
    AdminTaskSortField,
    AuthorDetailResponse,
    AuthorStatsResponse,
    SeverityFilter,
    SortOrder,
)
from app.services.admin_task_service import AdminTaskService
from app.services.author_stats_service import AuthorStatsService


router = APIRouter(tags=["admin"])
PAGE = Path(__file__).resolve().parents[1] / "static" / "admin_tasks.html"
AUTHOR_STATS_PAGE = Path(__file__).resolve().parents[1] / "static" / "author_stats.html"
AUTHOR_DETAIL_PAGE = Path(__file__).resolve().parents[1] / "static" / "author_detail.html"


@router.get("/admin/tasks.html", include_in_schema=False)
def admin_tasks_page() -> FileResponse:
    return FileResponse(PAGE, headers={"Cache-Control": "no-store"})


@router.get("/admin/authors.html", include_in_schema=False)
def author_stats_page() -> FileResponse:
    return FileResponse(AUTHOR_STATS_PAGE, headers={"Cache-Control": "no-store"})


@router.get("/admin/authors/{author}.html", include_in_schema=False)
def author_detail_page(author: str) -> FileResponse:
    return FileResponse(AUTHOR_DETAIL_PAGE, headers={"Cache-Control": "no-store"})


@router.get("/api/admin/tasks", response_model=AdminTaskListResponse)
def list_admin_tasks(
    response: Response,
    project_id: str = Query(default="", max_length=500),
    review_version: str = Query(default="", max_length=500),
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    task_type: int | None = Query(default=None, ge=1, le=1),
    state: int | None = Query(default=None, ge=0, le=3),
    sort_by: AdminTaskSortField = "create_time",
    sort_order: SortOrder = "desc",
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> AdminTaskListResponse:
    response.headers["Cache-Control"] = "no-store"
    return AdminTaskService().list_tasks(project_id, review_version, date_from, date_to, task_type, state, sort_by, sort_order, page, page_size)


@router.get("/api/admin/authors", response_model=AuthorStatsResponse)
def list_author_stats(
    response: Response,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> AuthorStatsResponse:
    response.headers["Cache-Control"] = "no-store"
    return AuthorStatsService().list_authors(date_from, date_to, page, page_size)


@router.get("/api/admin/authors/{author}", response_model=AuthorDetailResponse)
def get_author_stats(
    author: str,
    response: Response,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    severity: SeverityFilter = "all",
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> AuthorDetailResponse:
    response.headers["Cache-Control"] = "no-store"
    return AuthorStatsService().get_author(author, date_from, date_to, severity, page, page_size)
