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
    assert body["items"][0]["report_path"] == f"/reports/{task.id}.html"
    assert client.get(f"/reports/{task.id}.html").status_code == 200


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
    source = client.get(f"/api/code-files/{code_file.id}/source")
    assert source.status_code == 200
    assert source.json()["lines"] == ["int divide(int a, int b) { return a / b; }"]
