from __future__ import annotations

import json
import logging
import random
import time
from typing import Any

import httpx

from app.core.config import Settings


logger = logging.getLogger(__name__)
RETRYABLE_STATUS_CODES = {408, 429, 500, 502, 503, 504}


class LLMClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    @property
    def is_mock(self) -> bool:
        return self.settings.llm_mock_enabled or not self.settings.llm_url

    def chat(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        if self.is_mock:
            return {
                "role": "assistant",
                "content": "{}",
                "_llm_trace": {
                    "model": self.settings.llm_model,
                    "usage": {},
                    "elapsed_ms": 0,
                    "finish_reason": "mock",
                },
            }
        payload: dict[str, Any] = {
            "model": self.settings.llm_model,
            "messages": [{k: v for k, v in item.items() if not k.startswith("_")} for item in messages],
            "temperature": 0.1,
        }
        if tools:
            payload.update({"tools": tools, "tool_choice": "auto"})
        headers = {"Content-Type": "application/json"}
        if self.settings.llm_api_key:
            headers["Authorization"] = f"Bearer {self.settings.llm_api_key}"

        total_attempts = max(0, self.settings.llm_api_retry_times) + 1
        started = time.monotonic()
        for attempt in range(1, total_attempts + 1):
            model = self.settings.llm_model if attempt == 1 else (self.settings.llm_fallback_model or self.settings.llm_model)
            payload["model"] = model
            try:
                response = httpx.post(
                    self._chat_completions_url(),
                    headers=headers,
                    json=payload,
                    timeout=self.settings.llm_timeout_seconds,
                )
                response.raise_for_status()
                data = response.json()
                choice = data["choices"][0]
                message = choice["message"]
                message["_llm_trace"] = {
                    "model": data.get("model") or model,
                    "usage": data.get("usage") or {},
                    "elapsed_ms": int((time.monotonic() - started) * 1000),
                    "finish_reason": choice.get("finish_reason") or "",
                }
                return message
            except Exception as exc:
                if attempt >= total_attempts or not self._retryable(exc):
                    raise
                base = self.settings.llm_retry_backoff_seconds * (2 ** (attempt - 1))
                delay = min(self.settings.llm_retry_backoff_max_seconds, base)
                time.sleep(random.uniform(delay * 0.8, delay * 1.2) if delay else 0)
                logger.warning("LLM request failed, retrying: %s", exc)
        raise RuntimeError("LLM request exhausted")

    def _chat_completions_url(self) -> str:
        base = self.settings.llm_url.rstrip("/")
        return base if base.endswith("/chat/completions") else f"{base}/chat/completions"

    @staticmethod
    def _retryable(exc: Exception) -> bool:
        if isinstance(exc, httpx.HTTPStatusError):
            return exc.response.status_code in RETRYABLE_STATUS_CODES
        return isinstance(exc, (httpx.TransportError, json.JSONDecodeError, KeyError, IndexError, TypeError, ValueError))

