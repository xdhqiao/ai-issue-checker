from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "ai-issue-checker"
    app_env: str = "local"
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    app_enable_scheduler: bool = True

    mongodb_uri: str = "mongodb://mongodb:27017/ai_issue_checker"
    mongodb_db: str = "ai_issue_checker"
    mongodb_alias: str = "default"
    mongo_mock: bool = False

    scheduler_interval_seconds: int = 5
    scheduler_lease_seconds: int = 180
    scheduler_max_task_retries: int = 3
    scheduler_retry_backoff_seconds: int = 30
    scheduler_shutdown_grace_seconds: int = 30
    file_concurrency: int = 4

    llm_url: str = ""
    llm_api_key: str = ""
    llm_model: str = "deepseek-v4-flash"
    llm_fallback_model: str = "deepseek-v4-flash"
    llm_timeout_seconds: int = 120
    llm_api_retry_times: int = 2
    llm_retry_backoff_seconds: float = 1.0
    llm_retry_backoff_max_seconds: float = 8.0
    llm_max_tool_rounds: int = 30
    llm_file_timeout_seconds: int = 600
    llm_mock_enabled: bool = True

    code_repository_root: str = ""
    review_allowed_extensions: str = Field(
        default=(
            ".py,.js,.jsx,.ts,.tsx,.go,.java,.kt,.c,.h,.cpp,.hpp,.cc,.cs,.rs,"
            ".php,.rb,.swift,.scala,.sql,.yaml,.yml,.json,.toml,.ini,.md,.sh,"
            ".ps1,.html,.css,.scss,.vue"
        )
    )
    review_exclude_dirs: str = ".git,__pycache__,node_modules,.venv,venv,dist,build,.pytest_cache"
    review_tool_max_read_lines: int = 500
    review_tool_max_search_matches: int = 100
    review_tool_max_file_bytes: int = 2 * 1024 * 1024
    source_api_max_file_bytes: int = 5 * 1024 * 1024

    email_sender: str = "ci-ai-codereview@example.com"
    email_admin_receivers: str = "admin@example.com"
    email_account_domain: str = "example.com"
    email_report_base_url: str = "http://127.0.0.1:8000"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @property
    def allowed_extension_set(self) -> set[str]:
        return {item.strip().lower() for item in self.review_allowed_extensions.split(",") if item.strip()}

    @property
    def excluded_dir_set(self) -> set[str]:
        return {item.strip() for item in self.review_exclude_dirs.split(",") if item.strip()}

    @property
    def email_admin_receiver_list(self) -> list[str]:
        return list(dict.fromkeys(item.strip() for item in self.email_admin_receivers.split(",") if item.strip()))


@lru_cache
def get_settings() -> Settings:
    return Settings()

