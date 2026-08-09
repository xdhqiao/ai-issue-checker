from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta, timezone

from app.models.code_file import CodeFileModel
from app.models.task import TaskModel
from app.schemas.admin import DashboardResponse, DashboardTrendPoint


BEIJING_TIMEZONE = timezone(timedelta(hours=8))


class DashboardService:
    def get_dashboard(
        self,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
    ) -> DashboardResponse:
        query = TaskModel.objects
        if date_from is not None:
            query = query.filter(create_time__gte=date_from)
        if date_to is not None:
            query = query.filter(create_time__lte=date_to)
        tasks = list(
            query.only(
                "id",
                "project_id",
                "create_time",
                "file_num",
                "reviewed_file_num",
                "issue_num",
                "red_issue_num",
                "llm_prompt_tokens",
                "llm_completion_tokens",
                "llm_total_tokens",
                "llm_elapsed_ms",
            )
        )

        task_ids = [str(task.id) for task in tasks]
        tool_call_num = 0
        model_round_num = 0
        if task_ids:
            code_files = CodeFileModel.objects(task_id__in=task_ids).only("tool_calls", "model_rounds")
            for code_file in code_files:
                tool_call_num += len(code_file.tool_calls or [])
                model_round_num += len(code_file.model_rounds or [])

        issue_num = sum(int(task.issue_num or 0) for task in tasks)
        red_issue_num = sum(int(task.red_issue_num or 0) for task in tasks)
        return DashboardResponse(
            date_from=date_from,
            date_to=date_to,
            task_num=len(tasks),
            project_num=len({task.project_id for task in tasks}),
            llm_total_tokens=sum(int(task.llm_total_tokens or 0) for task in tasks),
            llm_prompt_tokens=sum(int(task.llm_prompt_tokens or 0) for task in tasks),
            llm_completion_tokens=sum(int(task.llm_completion_tokens or 0) for task in tasks),
            llm_elapsed_ms=sum(int(task.llm_elapsed_ms or 0) for task in tasks),
            file_num=sum(int(task.file_num or 0) for task in tasks),
            reviewed_file_num=sum(int(task.reviewed_file_num or 0) for task in tasks),
            tool_call_num=tool_call_num,
            model_round_num=model_round_num,
            issue_num=issue_num,
            red_issue_num=red_issue_num,
            red_issue_ratio=round(red_issue_num / issue_num, 6) if issue_num else 0,
            daily_trends=self._daily_trends(tasks, date_from, date_to),
        )

    def _daily_trends(
        self,
        tasks: list[TaskModel],
        date_from: datetime | None,
        date_to: datetime | None,
    ) -> list[DashboardTrendPoint]:
        daily: dict[date, dict[str, int]] = defaultdict(lambda: {"tasks": 0, "issues": 0})
        for task in tasks:
            day = self._beijing_date(task.create_time)
            daily[day]["tasks"] += 1
            daily[day]["issues"] += int(task.issue_num or 0)

        dates = self._trend_dates(daily, date_from, date_to)
        return [
            DashboardTrendPoint(
                date=day.isoformat(),
                task_num=daily[day]["tasks"],
                issue_num=daily[day]["issues"],
            )
            for day in dates
        ]

    def _trend_dates(
        self,
        daily: dict[date, dict[str, int]],
        date_from: datetime | None,
        date_to: datetime | None,
    ) -> list[date]:
        if date_from is not None and date_to is not None:
            start = self._beijing_date(date_from)
            end = self._beijing_date(date_to)
            return [start + timedelta(days=offset) for offset in range((end - start).days + 1)]
        return sorted(daily)

    @staticmethod
    def _beijing_date(value: datetime) -> date:
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(BEIJING_TIMEZONE).date()
