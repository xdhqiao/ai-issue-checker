from copy import deepcopy

from app.common.constants import State
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


def test_manual_retry_preserves_completed_files(client, payload):
    retry_payload = deepcopy(payload)
    retry_payload["files"].append(
        {
            **deepcopy(payload["files"][0]),
            "file_name": "Apps/Math/Other.c",
            "issues": [{**deepcopy(payload["files"][0]["issues"][0]), "id": 8894}],
        }
    )
    task_id = client.post("/api/tasks", json=retry_payload).json()["id"]
    files = list(CodeFileModel.objects(task_id=task_id).order_by("file_name"))
    completed_file, failed_file = files
    completed_file.state = State.COMPLETED.value
    completed_file.completion_status = "completed"
    completed_file.issues[0].confidence = 0.91
    completed_file.save()
    failed_file.state = State.FAILED.value
    failed_file.completion_status = "failed"
    failed_file.failure_message = "LLM unavailable"
    failed_file.save()

    task = TaskModel.objects(id=task_id).first()
    task.state = State.FAILED.value
    task.completion_status = "failed"
    task.retry_count = 1
    task.next_retry_time = None
    task.save()
    assert client.post(f"/api/tasks/{task_id}/retry").status_code == 409

    task.retry_count = 2
    task.next_retry_time = None
    task.save()

    admin_item = client.get("/api/admin/tasks").json()["items"][0]
    assert admin_item["can_retry"] is True

    response = client.post(f"/api/tasks/{task_id}/retry")
    assert response.status_code == 200
    assert response.json()["state"] == State.PENDING.value
    assert response.json()["retry_count"] == 2

    completed_file.reload()
    failed_file.reload()
    assert completed_file.state == State.COMPLETED.value
    assert completed_file.issues[0].confidence == 0.91
    assert failed_file.state == State.PENDING.value
    assert failed_file.failure_message == ""
