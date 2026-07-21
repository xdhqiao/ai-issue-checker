from __future__ import annotations

import logging
from pathlib import Path
from string import Template
from typing import Mapping, Sequence

from app.core.config import Settings, get_settings


logger = logging.getLogger(__name__)


class EmailServer:
    """Same replaceable/logging email boundary used by ci-ai-codereview."""

    def __init__(self, settings: Settings | None = None, template_root: Path | None = None) -> None:
        self.settings = settings or get_settings()
        self.sender = self.settings.email_sender
        self.template_root = template_root or Path(__file__).resolve().parents[1] / "templates"

    def send(self, subject: str, email_template: str, parameters: Mapping[str, object], receivers: Sequence[str]) -> str:
        receivers = tuple(dict.fromkeys(item.strip() for item in receivers if item and item.strip()))
        if not receivers:
            return ""
        rendered = self.render(email_template, parameters)
        logger.info(
            "Mock email sent: sender=%s receivers=%s subject=%s html_length=%s",
            self.sender,
            ",".join(receivers),
            subject,
            len(rendered),
        )
        return rendered

    def render(self, email_template: str, parameters: Mapping[str, object]) -> str:
        path = (self.template_root / email_template).resolve()
        if self.template_root.resolve() not in path.parents:
            raise ValueError("email template must stay inside the template directory")
        return Template(path.read_text(encoding="utf-8")).substitute({key: str(value) for key, value in parameters.items()})

