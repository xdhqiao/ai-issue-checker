from datetime import datetime, timedelta, timezone

from app.common.constants import State
from app.core.config import Settings
from app.models.code_file import CodeFileModel
from app.models.task import TaskModel
from app.schemas.task import TaskCreate
from app.services.issue_confirmation import IssueConfirmationService
from app.services.review_service import ReviewTaskService
from app.services.scheduler import ReviewScheduler
from app.services.task_submission import TaskSubmissionService


def test_mock_review_writes_only_confidence_and_completes(payload):
    task = TaskSubmissionService().submit(TaskCreate.model_validate(payload))
    scheduler = ReviewScheduler(Settings(mongo_mock=True, llm_mock_enabled=True))
    claimed = scheduler.claim_next_task()
    completed = ReviewTaskService(Settings(mongo_mock=True, llm_mock_enabled=True), claimed.lease_token).review_task(claimed)
    code_file = CodeFileModel.objects(task_id=str(task.id)).first()
    assert completed.state == State.COMPLETED.value
    assert completed.reviewed_file_num == 1
    assert code_file.state == State.COMPLETED.value
    assert code_file.issues[0].confidence == 0.5
    assert code_file.issues[0].check == "Division by zero"
    assert code_file.issues[0].comment == "polyspace comment"


def test_scheduler_reclaims_interrupted_running_task(payload):
    task = TaskSubmissionService().submit(TaskCreate.model_validate(payload))
    task.state = State.RUNNING.value
    task.lease_owner = "dead-worker"
    task.lease_token = "expired-token"
    task.lease_expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    task.save()
    scheduler = ReviewScheduler(Settings(scheduler_lease_seconds=60))
    claimed = scheduler.claim_next_task()
    assert claimed.id == task.id
    assert claimed.lease_token != "expired-token"
    assert claimed.lease_owner == scheduler.worker_id


def test_scheduler_skips_completed_files_when_resuming(payload):
    task = TaskSubmissionService().submit(TaskCreate.model_validate(payload))
    code_file = CodeFileModel.objects(task_id=str(task.id)).first()
    code_file.state = State.COMPLETED.value
    code_file.issues[0].confidence = 0.91
    code_file.save()
    scheduler = ReviewScheduler(Settings(llm_mock_enabled=True))
    claimed = scheduler.claim_next_task()
    ReviewTaskService(Settings(llm_mock_enabled=True), claimed.lease_token).review_task(claimed)
    code_file.reload()
    assert code_file.issues[0].confidence == 0.91


def test_llm_receives_only_four_polyspace_fields(payload):
    task = TaskSubmissionService().submit(TaskCreate.model_validate(payload))
    code_file = CodeFileModel.objects(task_id=str(task.id)).first()

    class FakeLLM:
        is_mock = False

        def chat(self, messages, tools):
            import json

            issue = json.loads(messages[1]["content"])["issues"][0]
            assert set(issue) == {"check", "function", "line", "detail"}
            assert "8893" not in messages[1]["content"]
            assert "red" not in messages[1]["content"]
            assert "polyspace comment" not in messages[1]["content"]
            return {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {"id": "a", "type": "function", "function": {"name": "submit_confidences", "arguments": '{"items":[{"issue_index":0,"confidence":0.82}]}' }},
                    {"id": "b", "type": "function", "function": {"name": "task_done", "arguments": '{"state":"DONE"}' }},
                ],
                "_llm_trace": {"model": "fake", "usage": {"prompt_tokens": 10, "completion_tokens": 2, "total_tokens": 12}, "elapsed_ms": 4, "finish_reason": "tool_calls"},
            }

    result = IssueConfirmationService(Settings(llm_mock_enabled=False, llm_url="http://unused"), FakeLLM()).confirm(
        code_file, __import__("pathlib").Path(payload["version_code_path"])
    )
    assert result.confidences == [0.82]
    assert result.total_tokens == 12
    assert result.call_count == 1

