from pathlib import Path

from mongoengine import ValidationError

from app.core.config import Settings, get_settings
from app.core.exceptions import NotFoundError, PayloadTooLargeError
from app.models.code_file import CodeFileModel
from app.models.task import TaskModel
from app.schemas.report import SourceResponse


class SourceService:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def read(self, file_id: str) -> SourceResponse:
        try:
            code_file = CodeFileModel.objects(id=file_id).first()
        except ValidationError:
            code_file = None
        if code_file is None:
            raise NotFoundError("Code file not found")
        task = TaskModel.objects(id=code_file.task_id).first()
        if task is None:
            raise NotFoundError("Task not found")
        root = Path(task.version_code_path).resolve()
        candidate = (root / code_file.file_name).resolve()
        try:
            candidate.relative_to(root)
        except ValueError as exc:
            raise NotFoundError("Source path is outside version_code_path") from exc
        if self.settings.code_repository_root:
            allowed = Path(self.settings.code_repository_root).resolve()
            try:
                candidate.relative_to(allowed)
            except ValueError as exc:
                raise NotFoundError("Source path is outside CODE_REPOSITORY_ROOT") from exc
        if not candidate.is_file():
            raise NotFoundError("Source file not found")
        if candidate.stat().st_size > self.settings.source_api_max_file_bytes:
            raise PayloadTooLargeError("Source file exceeds SOURCE_API_MAX_FILE_BYTES")
        lines = candidate.read_text(encoding="utf-8", errors="replace").splitlines()
        return SourceResponse(file_id=str(code_file.id), file_name=code_file.file_name, total_lines=len(lines), lines=lines)
