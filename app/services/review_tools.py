from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Iterator

from app.core.config import Settings


class IssueConfirmationToolRunner:
    def __init__(self, root_dir: Path, current_file_name: str, issue_count: int, settings: Settings) -> None:
        self.root_dir = root_dir.resolve()
        self.current_file_name = self._normalize(current_file_name)
        self.issue_count = issue_count
        self.settings = settings
        self.confidences: dict[int, float] = {}
        self.done = False
        self.failed = False
        self.failure_message = ""

    def run(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        try:
            if name == "file_find":
                return self.file_find(arguments)
            if name in {"read_file", "file_read", "file_read_diff"}:
                return self.read_file(arguments)
            if name == "code_search":
                return self.code_search(arguments)
            if name in {"find_definition", "find_references", "call_graph"}:
                return self.symbol_search(arguments, name)
            if name == "submit_confidences":
                return self.submit_confidences(arguments)
            if name == "task_done":
                return self.task_done(arguments)
            return {"error": f"Unsupported tool: {name}"}
        except Exception as exc:
            return {"error": f"{name} failed: {type(exc).__name__}: {exc}"}

    def file_find(self, arguments: dict[str, Any]) -> dict[str, Any]:
        query = str(arguments.get("query_name") or arguments.get("query") or "").lower()
        limit = self._limit(arguments.get("limit"), 20)
        matches = []
        for path in self._iter_files():
            relative = path.relative_to(self.root_dir).as_posix()
            if query in relative.lower():
                matches.append({"file_path": relative})
                if len(matches) >= limit:
                    break
        return {"matches": matches, "truncated": len(matches) >= limit}

    def read_file(self, arguments: dict[str, Any]) -> dict[str, Any]:
        requested = str(arguments.get("file_path") or self.current_file_name)
        path = self._safe_path(requested)
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        start = max(1, int(arguments.get("start_line") or 1))
        requested_end = max(start, int(arguments.get("end_line") or len(lines)))
        end = min(requested_end, start + max(1, self.settings.review_tool_max_read_lines) - 1, len(lines))
        return {
            "file_path": path.relative_to(self.root_dir).as_posix(),
            "total_lines": len(lines),
            "line_range": f"{start}-{end}",
            "is_truncated": end < len(lines),
            "lines": [{"line_number": number, "line": lines[number - 1]} for number in range(start, end + 1)],
        }

    def code_search(self, arguments: dict[str, Any]) -> dict[str, Any]:
        query = str(arguments.get("search_text") or arguments.get("query") or "")
        regex = bool(arguments.get("regex", False))
        case_sensitive = bool(arguments.get("case_sensitive", False))
        limit = self._limit(arguments.get("limit"), self.settings.review_tool_max_search_matches)
        flags = 0 if case_sensitive else re.IGNORECASE
        pattern = re.compile(query, flags) if regex else None
        needle = query if case_sensitive else query.lower()
        matches: list[dict[str, Any]] = []
        for path in self._iter_files():
            for line_number, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
                candidate = line if case_sensitive else line.lower()
                if (pattern.search(line) if pattern else needle in candidate):
                    matches.append({"file_path": path.relative_to(self.root_dir).as_posix(), "line_number": line_number, "line": line})
                    if len(matches) >= limit:
                        return {"matches": matches, "truncated": True}
        return {"matches": matches, "truncated": False}

    def symbol_search(self, arguments: dict[str, Any], name: str) -> dict[str, Any]:
        symbol = str(arguments.get("symbol") or "").strip()
        if not symbol:
            return {"error": "symbol is required"}
        result = self.code_search({"search_text": symbol, "regex": False, "case_sensitive": True, "limit": arguments.get("limit")})
        result["operation"] = name
        return result

    def submit_confidences(self, arguments: dict[str, Any]) -> dict[str, Any]:
        items = arguments.get("items")
        if not isinstance(items, list):
            return {"accepted": False, "error": "items must be an array"}
        errors: list[str] = []
        for item in items:
            if not isinstance(item, dict):
                errors.append("each item must be an object")
                continue
            try:
                index = int(item["issue_index"])
                confidence = float(item["confidence"])
            except (KeyError, TypeError, ValueError):
                errors.append("issue_index and confidence are required")
                continue
            if index < 0 or index >= self.issue_count:
                errors.append(f"issue_index {index} is out of range")
            elif confidence < 0 or confidence > 1:
                errors.append(f"confidence for issue_index {index} must be between 0 and 1")
            else:
                self.confidences[index] = confidence
        return {
            "accepted": not errors,
            "accepted_count": len(self.confidences),
            "remaining_issue_indexes": [i for i in range(self.issue_count) if i not in self.confidences],
            "errors": errors,
        }

    def task_done(self, arguments: dict[str, Any]) -> dict[str, Any]:
        state = str(arguments.get("state") or "FAILED").upper()
        if state == "DONE" and len(self.confidences) != self.issue_count:
            return {"done": False, "error": "confidence is missing for one or more issues", "remaining_issue_indexes": [i for i in range(self.issue_count) if i not in self.confidences]}
        self.done = True
        self.failed = state != "DONE"
        self.failure_message = str(arguments.get("summary") or "") if self.failed else ""
        return {"done": True, "state": state}

    def tool_result_message(self, tool_call_id: str, result: dict[str, Any]) -> dict[str, Any]:
        return {"role": "tool", "tool_call_id": tool_call_id, "content": json.dumps(result, ensure_ascii=False)}

    def _safe_path(self, relative: str) -> Path:
        normalized = self._normalize(relative)
        if not normalized:
            raise ValueError("file_path is required")
        candidate = (self.root_dir / normalized).resolve()
        try:
            candidate.relative_to(self.root_dir)
        except ValueError as exc:
            raise ValueError("file path escapes version_code_path") from exc
        if not candidate.is_file():
            raise FileNotFoundError(normalized)
        if candidate.suffix.lower() not in self.settings.allowed_extension_set:
            raise ValueError("file extension is not allowed")
        if candidate.stat().st_size > self.settings.review_tool_max_file_bytes:
            raise ValueError("file exceeds review tool size limit")
        return candidate

    def _iter_files(self) -> Iterator[Path]:
        for discovered in self.root_dir.rglob("*"):
            try:
                path = discovered.resolve()
                path.relative_to(self.root_dir)
            except (OSError, ValueError):
                continue
            if not path.is_file() or any(part in self.settings.excluded_dir_set for part in path.relative_to(self.root_dir).parts):
                continue
            if path.suffix.lower() not in self.settings.allowed_extension_set:
                continue
            try:
                if path.stat().st_size <= self.settings.review_tool_max_file_bytes:
                    yield path
            except OSError:
                continue

    @staticmethod
    def _normalize(value: str) -> str:
        value = str(value or "").replace("\\", "/").strip()
        if value.startswith("/") or re.match(r"^[A-Za-z]:", value):
            raise ValueError("absolute paths are not allowed")
        parts = [part for part in value.split("/") if part not in {"", "."}]
        if ".." in parts:
            raise ValueError("path traversal is not allowed")
        return "/".join(parts)

    def _limit(self, value: Any, default: int) -> int:
        try:
            parsed = int(value) if value is not None else default
        except (TypeError, ValueError):
            parsed = default
        return min(max(1, parsed), max(1, self.settings.review_tool_max_search_matches))
