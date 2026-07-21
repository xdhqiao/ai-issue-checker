from app.models.code_file import CodeFileModel
from app.models.task import TaskModel


def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok"}


def test_submission_creates_task_files_and_counts(client, payload):
    response = client.post("/api/tasks", json=payload)
    assert response.status_code == 201
    body = response.json()
    assert body["state"] == 0
    assert body["file_num"] == 1
    assert body["issue_num"] == 1
    assert body["red_issue_num"] == 1
    assert body["author_num"] == 1
    code_file = CodeFileModel.objects(task_id=body["id"]).first()
    assert code_file.issues[0].comment == "polyspace comment"
    assert code_file.issues[0].confidence is None


def test_duplicate_project_version_removes_old_task_and_all_files(client, payload):
    first = client.post("/api/tasks", json=payload).json()
    replacement = {**payload, "files": []}
    second_response = client.post("/api/tasks", json=replacement)
    assert second_response.status_code == 201
    second = second_response.json()
    assert second["id"] != first["id"]
    assert TaskModel.objects(project_id="engine-ecu", review_version="v1").count() == 1
    assert TaskModel.objects(id=first["id"]).count() == 0
    assert CodeFileModel.objects(task_id=first["id"]).count() == 0


def test_input_rejects_unsafe_file_path(client, payload):
    payload["files"][0]["file_name"] = "../secret.c"
    assert client.post("/api/tasks", json=payload).status_code == 422

    payload["files"][0]["file_name"] = "C:/Windows/secret.c"
    assert client.post("/api/tasks", json=payload).status_code == 422
