from copy import deepcopy
from datetime import datetime, timezone

import pytest

from app.models.code_file import CodeFileModel, ModelRoundTrace, ToolCallTrace
from app.schemas.task import TaskCreate
from app.services.task_submission import TaskSubmissionService


def _submit_dashboard_data(payload):
    first_task = TaskSubmissionService().submit(TaskCreate.model_validate(payload))
    first_task.create_time = datetime(2026, 7, 10, 0, 30, tzinfo=timezone.utc)
    first_task.reviewed_file_num = 1
    first_task.llm_prompt_tokens = 100
    first_task.llm_completion_tokens = 20
    first_task.llm_total_tokens = 120
    first_task.llm_elapsed_ms = 1000
    first_task.save()
    first_file = CodeFileModel.objects(task_id=str(first_task.id)).first()
    first_file.model_rounds = [
        ModelRoundTrace(round_index=1, model="primary"),
        ModelRoundTrace(round_index=2, model="primary"),
    ]
    first_file.tool_calls = [
        ToolCallTrace(round_index=1, tool_call_id="tool-1", tool_name="file_read"),
    ]
    first_file.save()

    second_payload = deepcopy(payload)
    second_payload["project_id"] = "brake-ecu"
    second_payload["review_version"] = "v2"
    orange_issue = deepcopy(second_payload["files"][0]["issues"][0])
    orange_issue.update({"id": 8894, "severity_color": "orange"})
    gray_issue = deepcopy(second_payload["files"][0]["issues"][0])
    gray_issue.update({"id": 8895, "severity_color": "gray"})
    second_payload["files"][0]["issues"].extend([orange_issue, gray_issue])
    second_task = TaskSubmissionService().submit(TaskCreate.model_validate(second_payload))
    second_task.create_time = datetime(2026, 7, 11, 15, 30, tzinfo=timezone.utc)
    second_task.reviewed_file_num = 0
    second_task.llm_prompt_tokens = 250
    second_task.llm_completion_tokens = 80
    second_task.llm_total_tokens = 330
    second_task.llm_elapsed_ms = 2500
    second_task.save()
    second_file = CodeFileModel.objects(task_id=str(second_task.id)).first()
    second_file.model_rounds = [ModelRoundTrace(round_index=1, model="fallback")]
    second_file.tool_calls = [
        ToolCallTrace(round_index=1, tool_call_id="tool-2", tool_name="file_read"),
        ToolCallTrace(round_index=1, tool_call_id="tool-3", tool_name="file_find"),
    ]
    second_file.save()


def test_dashboard_aggregates_tasks_files_llm_usage_and_daily_trends(client, payload):
    _submit_dashboard_data(payload)

    response = client.get(
        "/api/admin/dashboard",
        params={
            "date_from": "2026-07-09T16:00:00Z",
            "date_to": "2026-07-12T15:59:59.999Z",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["task_num"] == 2
    assert body["project_num"] == 2
    assert body["file_num"] == 2
    assert body["reviewed_file_num"] == 1
    assert body["issue_num"] == 4
    assert body["red_issue_num"] == 2
    assert body["red_issue_ratio"] == pytest.approx(0.5)
    assert body["llm_prompt_tokens"] == 350
    assert body["llm_completion_tokens"] == 100
    assert body["llm_total_tokens"] == 450
    assert body["llm_elapsed_ms"] == 3500
    assert body["tool_call_num"] == 3
    assert body["model_round_num"] == 3
    assert body["daily_trends"] == [
        {"date": "2026-07-10", "task_num": 1, "issue_num": 1},
        {"date": "2026-07-11", "task_num": 1, "issue_num": 3},
        {"date": "2026-07-12", "task_num": 0, "issue_num": 0},
    ]


def test_dashboard_filters_by_task_create_time_and_validates_range(client, payload):
    _submit_dashboard_data(payload)

    response = client.get(
        "/api/admin/dashboard",
        params={
            "date_from": "2026-07-09T16:00:00Z",
            "date_to": "2026-07-10T15:59:59.999Z",
        },
    )
    assert response.status_code == 200
    assert response.json()["task_num"] == 1
    assert response.json()["issue_num"] == 1

    invalid = client.get(
        "/api/admin/dashboard",
        params={
            "date_from": "2026-07-12T00:00:00Z",
            "date_to": "2026-07-10T00:00:00Z",
        },
    )
    assert invalid.status_code == 422
    assert invalid.json()["detail"] == "开始日期不能晚于结束日期"


def test_dashboard_page_and_admin_entry_are_available(client):
    page = client.get("/admin/dashboard.html")
    assert page.status_code == 200
    assert "Polyspace Issue 数据看板" in page.text
    assert "每日任务量" in page.text
    assert "dashboard.js?v=20260729-1" in page.text

    admin_page = client.get("/admin/tasks.html")
    assert admin_page.status_code == 200
    assert 'href="/admin/dashboard.html"' in admin_page.text
    assert "数据看板" in admin_page.text
