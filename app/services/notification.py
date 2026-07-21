from __future__ import annotations

from html import escape
from urllib.parse import quote

from app.core.config import Settings, get_settings
from app.models.code_file import CodeFileModel
from app.models.task import TaskModel
from app.services.email_service import EmailServer


class ReviewNotificationService:
    def __init__(self, settings: Settings | None = None, email_server: EmailServer | None = None) -> None:
        self.settings = settings or get_settings()
        self.email_server = email_server or EmailServer(self.settings)

    def send_review_completed(self, task: TaskModel) -> bool:
        files = list(CodeFileModel.objects(task_id=str(task.id)).order_by("file_author", "file_name"))
        subject = f"Polyspace issue 二次确认完成：{task.project_id} {task.review_version}"
        report_path = f"/reports/{quote(str(task.id), safe='')}.html"
        parameters = {
            "project_id": escape(task.project_id),
            "review_version": escape(task.review_version),
            "file_num": task.file_num or 0,
            "issue_num": task.issue_num or 0,
            "red_issue_num": task.red_issue_num or 0,
            "owner_rows": self._owner_rows(files),
            "report_url": escape(f"{self.settings.email_report_base_url.rstrip('/')}{report_path}", quote=True),
        }
        if self.settings.email_admin_receiver_list:
            self.email_server.send(subject, "review_completed_email.html", parameters, self.settings.email_admin_receiver_list)
        owners = sorted({item.file_author.strip() for item in files if item.file_author.strip()})
        for owner in owners:
            receiver = owner if "@" in owner else self._owner_email(owner)
            if receiver:
                self.email_server.send(subject, "review_completed_email.html", parameters, [receiver])
        return True

    def _owner_email(self, owner: str) -> str:
        domain = self.settings.email_account_domain.strip().lstrip("@")
        return f"{owner}@{domain}" if domain else ""

    @staticmethod
    def _owner_rows(files: list[CodeFileModel]) -> str:
        counters: dict[str, int] = {}
        for item in files:
            key = item.file_author.strip() or "未分配"
            counters[key] = counters.get(key, 0) + len(item.issues)
        if not counters:
            return '<tr><td colspan="2">暂无问题</td></tr>'
        return "".join(f"<tr><td>{escape(owner)}</td><td>{count}</td></tr>" for owner, count in sorted(counters.items()))

