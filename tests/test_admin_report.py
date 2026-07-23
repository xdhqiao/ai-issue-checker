from copy import deepcopy

from app.common.constants import State
from app.models.code_file import CodeFileModel
from app.schemas.task import TaskCreate
from app.services.task_submission import TaskSubmissionService


def test_admin_filters_sorts_and_links_report(client, payload):
    task = TaskSubmissionService().submit(TaskCreate.model_validate(payload))
    response = client.get("/api/admin/tasks", params={"project_id": "engine", "sort_by": "red_issue_num", "sort_order": "desc"})
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["report_path"] == "/reports/engine-ecu/v1.html"
    assert client.get(f"/reports/{task.id}.html").status_code == 200
    report_page = client.get("/reports/engine-ecu/v1.html")
    assert report_page.status_code == 200
    assert "返回任务列表" not in report_page.text
    assert "report.js?v=20260722-friendly-route2" in report_page.text


def test_report_and_source_endpoints(client, payload):
    task = TaskSubmissionService().submit(TaskCreate.model_validate(payload))
    code_file = CodeFileModel.objects(task_id=str(task.id)).first()
    code_file.state = State.COMPLETED.value
    code_file.issues[0].confidence = 0.77
    code_file.save()
    response = client.get(f"/api/reports/tasks/{task.id}")
    assert response.status_code == 200
    body = response.json()
    assert body["summary"]["red_issue_num"] == 1
    assert body["files"][0]["issues"][0]["confidence"] == 0.77
    friendly = client.get("/api/reports/projects/engine-ecu/versions/v1")
    assert friendly.status_code == 200
    assert friendly.json()["task_id"] == str(task.id)
    source = client.get(f"/api/code-files/{code_file.id}/source")
    assert source.status_code == 200
    assert source.json()["lines"] == ["int divide(int a, int b) { return a / b; }"]


def test_author_overview_and_detail_statistics(client, payload):
    TaskSubmissionService().submit(TaskCreate.model_validate(payload))
    orange_payload = deepcopy(payload)
    orange_payload["review_version"] = "v2"
    orange_payload["files"][0]["issues"][0]["id"] = 8894
    orange_payload["files"][0]["issues"][0]["severity_color"] = "orange"
    TaskSubmissionService().submit(TaskCreate.model_validate(orange_payload))

    response = client.get("/api/admin/authors")
    assert response.status_code == 200
    body = response.json()
    assert body["project_num"] == 1
    assert body["version_num"] == 2
    assert body["red_issue_num"] == 1
    assert body["orange_issue_num"] == 1
    assert body["total"] == 1
    assert body["items"][0]["author"] == "dahai"
    assert body["items"][0]["detail_path"] == "/admin/authors/dahai.html"

    detail = client.get("/api/admin/authors/dahai", params={"severity": "orange"})
    assert detail.status_code == 200
    detail_body = detail.json()
    assert detail_body["project_num"] == 1
    assert detail_body["version_num"] == 1
    assert detail_body["red_issue_num"] == 0
    assert detail_body["orange_issue_num"] == 1
    assert detail_body["items"][0]["report_path"] == "/reports/engine-ecu/v2.html"

    empty = client.get("/api/admin/authors", params={"date_from": "2099-01-01T00:00:00Z"})
    assert empty.status_code == 200
    assert empty.json()["total"] == 0


def test_author_pages_are_available(client):
    overview = client.get("/admin/authors.html")
    assert overview.status_code == 200
    assert "问题等级" not in overview.text
    assert overview.text.count('data-lpignore="true"') == 2
    assert "author_date_guard.js?v=20260722-3" in overview.text

    detail = client.get("/admin/authors/dahai.html")
    assert detail.status_code == 200
    assert "问题等级" in detail.text
    assert detail.text.count('data-lpignore="true"') == 2
    assert "author_date_guard.js?v=20260722-3" in detail.text

    openapi = client.get("/openapi.json").json()
    overview_parameters = openapi["paths"]["/api/admin/authors"]["get"]["parameters"]
    assert "severity" not in {parameter["name"] for parameter in overview_parameters}


def test_admin_page_exposes_manual_retry_action(client):
    page = client.get("/admin/tasks.html")
    script = client.get("/static/admin_tasks.js?v=20260723-retry1")
    assert page.status_code == 200
    assert "操作" in page.text
    assert "admin_tasks.js?v=20260723-retry1" in page.text
    assert script.status_code == 200
    assert "继续确认" in script.text
