import os

os.environ["APP_ENABLE_SCHEDULER"] = "false"
os.environ["LLM_MOCK_ENABLED"] = "true"
os.environ["MONGO_MOCK"] = "true"
os.environ["MONGODB_DB"] = "ai_issue_checker_test"

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.core.database import connect_to_mongo, disconnect_mongo
from app.main import app
from app.models.code_file import CodeFileModel
from app.models.task import TaskModel


@pytest.fixture(autouse=True)
def clean_database():
    get_settings.cache_clear()
    settings = get_settings()
    connect_to_mongo(settings)
    TaskModel.drop_collection()
    CodeFileModel.drop_collection()
    yield
    connect_to_mongo(settings)
    TaskModel.drop_collection()
    CodeFileModel.drop_collection()
    disconnect_mongo(settings)


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def payload(tmp_path):
    source = tmp_path / "version" / "Apps" / "Math" / "Math.c"
    source.parent.mkdir(parents=True)
    source.write_text("int divide(int a, int b) { return a / b; }\n", encoding="utf-8")
    return {
        "project_id": "engine-ecu",
        "review_version": "v1",
        "version_code_path": str(tmp_path / "version"),
        "files": [
            {
                "file_name": "Apps/Math/Math.c",
                "file_author": "dahai",
                "issues": [
                    {
                        "id": 8893,
                        "check": "Division by zero",
                        "function": "divide()",
                        "line": 1,
                        "col": 35,
                        "detail": "scalar division by zero may occur",
                        "severity_color": "red",
                        "comment": "polyspace comment",
                    }
                ],
            }
        ],
    }

