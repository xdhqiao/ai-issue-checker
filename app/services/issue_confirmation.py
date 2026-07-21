from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.core.config import Settings
from app.models.code_file import CodeFileModel, ModelRoundTrace, ToolCallTrace
from app.services.llm_client import LLMClient
from app.services.prompts import ISSUE_CONFIRMATION_TOOLS, SYSTEM_PROMPT
from app.services.review_tools import IssueConfirmationToolRunner


@dataclass
class ConfirmationResult:
    confidences: list[float]
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    call_count: int = 0
    elapsed_ms: int = 0
    model_rounds: list[ModelRoundTrace] = field(default_factory=list)
    tool_calls: list[ToolCallTrace] = field(default_factory=list)


class IssueConfirmationService:
    def __init__(self, settings: Settings, llm_client: LLMClient | None = None) -> None:
        self.settings = settings
        self.llm_client = llm_client or LLMClient(settings)

    def confirm(self, code_file: CodeFileModel, version_root: Path) -> ConfirmationResult:
        issue_count = len(code_file.issues)
        if issue_count == 0:
            return ConfirmationResult(confidences=[])
        if self.llm_client.is_mock:
            return ConfirmationResult(confidences=[0.5] * issue_count)

        # Deliberately expose only the four requested Polyspace fields. IDs,
        # severity, comments, authors and paths remain display-only metadata.
        issue_payload = [
            {"check": issue.check, "function": issue.function, "line": issue.line, "detail": issue.detail}
            for issue in code_file.issues
        ]
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": json.dumps({"issues": issue_payload}, ensure_ascii=False)},
        ]
        runner = IssueConfirmationToolRunner(version_root, code_file.file_name, issue_count, self.settings)
        result = ConfirmationResult(confidences=[])
        started = time.monotonic()

        for round_index in range(1, max(1, self.settings.llm_max_tool_rounds) + 1):
            if time.monotonic() - started > max(1, self.settings.llm_file_timeout_seconds):
                raise TimeoutError("issue confirmation exceeded file timeout")
            request_started = time.monotonic()
            assistant = self.llm_client.chat(messages, ISSUE_CONFIRMATION_TOOLS)
            trace = assistant.get("_llm_trace") or {}
            usage = trace.get("usage") or {}
            prompt_tokens = int(usage.get("prompt_tokens") or 0)
            completion_tokens = int(usage.get("completion_tokens") or 0)
            total_tokens = int(usage.get("total_tokens") or prompt_tokens + completion_tokens)
            elapsed_ms = int(trace.get("elapsed_ms") or (time.monotonic() - request_started) * 1000)
            result.prompt_tokens += prompt_tokens
            result.completion_tokens += completion_tokens
            result.total_tokens += total_tokens
            result.call_count += 1
            result.elapsed_ms += elapsed_ms
            result.model_rounds.append(
                ModelRoundTrace(
                    round_index=round_index,
                    model=str(trace.get("model") or self.settings.llm_model),
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    total_tokens=total_tokens,
                    elapsed_ms=elapsed_ms,
                    finish_reason=str(trace.get("finish_reason") or ""),
                )
            )
            messages.append(assistant)
            tool_calls = assistant.get("tool_calls") or []
            if not tool_calls:
                if self._json_fallback(assistant.get("content"), runner):
                    runner.done = len(runner.confidences) == issue_count
                if runner.done:
                    break
                messages.append({"role": "user", "content": "Use submit_confidences for every issue, then call task_done."})
                continue

            for tool_call in tool_calls:
                function = tool_call.get("function") or {}
                name = str(function.get("name") or "")
                raw_arguments = function.get("arguments") or "{}"
                tool_started = time.monotonic()
                try:
                    arguments = json.loads(raw_arguments) if isinstance(raw_arguments, str) else raw_arguments
                    if not isinstance(arguments, dict):
                        raise ValueError("tool arguments must be an object")
                    tool_result = runner.run(name, arguments)
                except Exception as exc:
                    tool_result = {"error": f"invalid tool arguments: {type(exc).__name__}: {exc}"}
                result.tool_calls.append(
                    ToolCallTrace(
                        round_index=round_index,
                        tool_call_id=str(tool_call.get("id") or ""),
                        tool_name=name,
                        elapsed_ms=int((time.monotonic() - tool_started) * 1000),
                        success=0 if tool_result.get("error") else 1,
                        error_message=str(tool_result.get("error") or ""),
                    )
                )
                messages.append(runner.tool_result_message(str(tool_call.get("id") or ""), tool_result))
            if runner.done:
                break

        if runner.failed:
            raise RuntimeError(runner.failure_message or "model reported confirmation failure")
        if not runner.done or len(runner.confidences) != issue_count:
            raise RuntimeError("model did not submit confidence for every issue before the round limit")
        result.confidences = [runner.confidences[index] for index in range(issue_count)]
        return result

    @staticmethod
    def _json_fallback(content: Any, runner: IssueConfirmationToolRunner) -> bool:
        try:
            parsed = json.loads(str(content or ""))
        except json.JSONDecodeError:
            return False
        values = parsed.get("confidences") if isinstance(parsed, dict) else None
        if not isinstance(values, list):
            return False
        if values and isinstance(values[0], (int, float)):
            items = [{"issue_index": index, "confidence": value} for index, value in enumerate(values)]
        else:
            items = values
        response = runner.submit_confidences({"items": items})
        return not response.get("errors") and len(runner.confidences) == runner.issue_count
