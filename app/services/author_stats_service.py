from __future__ import annotations

from datetime import datetime
from math import ceil
from urllib.parse import quote

from app.models.code_file import CodeFileModel
from app.models.task import TaskModel
from app.schemas.admin import (
    AuthorDetailResponse,
    AuthorStatsItem,
    AuthorStatsResponse,
    AuthorVersionItem,
    SeverityFilter,
)


class AuthorStatsService:
    def list_authors(
        self,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> AuthorStatsResponse:
        tasks = self._tasks(date_from, date_to)
        task_map = {str(task.id): task for task in tasks}
        groups: dict[str, dict[str, object]] = {}
        if task_map:
            for code_file in CodeFileModel.objects(task_id__in=list(task_map)):
                author = (code_file.file_author or "").strip()
                if not author:
                    continue
                red, orange = self._issue_counts(code_file)
                if not red and not orange:
                    continue
                group = groups.setdefault(
                    author,
                    {"projects": set(), "versions": set(), "red": 0, "orange": 0},
                )
                task = task_map[code_file.task_id]
                group["projects"].add(task.project_id)  # type: ignore[union-attr]
                group["versions"].add(code_file.task_id)  # type: ignore[union-attr]
                group["red"] = int(group["red"]) + red
                group["orange"] = int(group["orange"]) + orange

        author_groups = sorted(groups.items(), key=lambda item: item[0].lower())
        start = (page - 1) * page_size
        page_items = author_groups[start : start + page_size]
        project_ids = set()
        version_ids = set()
        for _, values in author_groups:
            project_ids.update(values["projects"])
            version_ids.update(values["versions"])
        return AuthorStatsResponse(
            items=[
                AuthorStatsItem(
                    author=author,
                    project_num=len(values["projects"]),
                    version_num=len(values["versions"]),
                    red_issue_num=int(values["red"]),
                    orange_issue_num=int(values["orange"]),
                    detail_path=f"/admin/authors/{quote(author, safe='')}.html",
                )
                for author, values in page_items
            ],
            project_num=len(project_ids),
            version_num=len(version_ids),
            red_issue_num=sum(int(values["red"]) for _, values in author_groups),
            orange_issue_num=sum(int(values["orange"]) for _, values in author_groups),
            total=len(author_groups),
            page=page,
            page_size=page_size,
            total_pages=ceil(len(author_groups) / page_size) if author_groups else 0,
        )

    def get_author(
        self,
        author: str,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        severity: SeverityFilter = "all",
        page: int = 1,
        page_size: int = 20,
    ) -> AuthorDetailResponse:
        normalized_author = author.strip()
        tasks = self._tasks(date_from, date_to)
        task_map = {str(task.id): task for task in tasks}
        groups: dict[str, dict[str, int]] = {}
        if task_map:
            files = CodeFileModel.objects(task_id__in=list(task_map), file_author=normalized_author)
            for code_file in files:
                red, orange = self._issue_counts(code_file)
                group = groups.setdefault(code_file.task_id, {"red": 0, "orange": 0})
                group["red"] += red
                group["orange"] += orange

        rows = [
            (task_map[task_id], values)
            for task_id, values in groups.items()
            if self._matches_severity(values["red"], values["orange"], severity)
        ]
        rows.sort(key=lambda item: item[0].create_time, reverse=True)
        start = (page - 1) * page_size
        page_rows = rows[start : start + page_size]
        return AuthorDetailResponse(
            author=normalized_author,
            items=[
                AuthorVersionItem(
                    task_id=str(task.id),
                    project_id=task.project_id,
                    review_version=task.review_version,
                    red_issue_num=values["red"],
                    orange_issue_num=values["orange"],
                    create_time=task.create_time,
                    report_path=(
                        f"/reports/{quote(task.project_id, safe='')}/"
                        f"{quote(task.review_version, safe='')}.html"
                    ),
                )
                for task, values in page_rows
            ],
            project_num=len({task.project_id for task, _ in rows}),
            version_num=len(rows),
            red_issue_num=sum(values["red"] for _, values in rows),
            orange_issue_num=sum(values["orange"] for _, values in rows),
            total=len(rows),
            page=page,
            page_size=page_size,
            total_pages=ceil(len(rows) / page_size) if rows else 0,
        )

    @staticmethod
    def _tasks(date_from: datetime | None, date_to: datetime | None) -> list[TaskModel]:
        query = TaskModel.objects
        if date_from is not None:
            query = query.filter(create_time__gte=date_from)
        if date_to is not None:
            query = query.filter(create_time__lte=date_to)
        return list(query.only("id", "project_id", "review_version", "create_time"))

    @staticmethod
    def _issue_counts(code_file: CodeFileModel) -> tuple[int, int]:
        colors = [str(issue.severity_color or "").strip().lower() for issue in code_file.issues]
        return colors.count("red"), colors.count("orange")

    @staticmethod
    def _matches_severity(red: int, orange: int, severity: SeverityFilter) -> bool:
        if severity == "red":
            return red > 0
        if severity == "orange":
            return orange > 0
        return red + orange > 0
