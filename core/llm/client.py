"""OpenAI-compatible LLM client (works for cloud APIs and local servers)."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from core.config import LLMConfig
from core.exceptions import LLMError

logger = logging.getLogger(__name__)

_JSON_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)


class LLMClient:
    """Minimal chat-completion client.

    Both the ``openai`` cloud provider and self-hosted OpenAI-compatible
    servers (vLLM, Ollama, LM Studio, ...) are addressed through the same
    interface, differing only by ``base_url`` / ``api_key``.
    """

    def __init__(self, config: LLMConfig) -> None:
        self.config = config
        self._client = None

    def _ensure_client(self):
        if self._client is not None:
            return self._client
        try:
            from openai import OpenAI  # noqa: PLC0415
        except ImportError as exc:  # pragma: no cover - environment guard
            raise LLMError(f"openai package unavailable: {exc}") from exc
        # Local servers often do not require an API key but the SDK insists on
        # a non-empty string.
        self._client = OpenAI(
            base_url=self.config.base_url,
            api_key=self.config.api_key or "not-needed",
            timeout=self.config.timeout,
        )
        return self._client

    def chat(self, messages: list[dict], **overrides: Any) -> str:
        client = self._ensure_client()
        params: dict[str, Any] = {
            "model": self.config.model,
            "messages": messages,
            "temperature": self.config.temperature,
            "max_tokens": self.config.max_tokens,
        }
        params.update(overrides)
        try:
            response = client.chat.completions.create(**params)
        except Exception as exc:
            raise LLMError(f"LLM request failed: {exc}") from exc
        if not response.choices:
            raise LLMError("LLM returned no choices")
        content = response.choices[0].message.content
        return content or ""

    def chat_json(self, messages: list[dict], **overrides: Any) -> dict:
        raw = self.chat(messages, **overrides)
        return parse_json_response(raw)

    def chat_json_array(self, messages: list[dict], **overrides: Any) -> list[dict]:
        """Request a JSON array and return it as a list of dicts."""

        raw = self.chat(messages, **overrides)
        return parse_json_array(raw)

    def test_connection(self) -> tuple[bool, str]:
        try:
            reply = self.chat([{"role": "user", "content": "回复 ok"}], max_tokens=16)
        except LLMError as exc:
            return False, str(exc)
        return True, reply.strip() or "connected"


def parse_json_response(raw: str) -> dict:
    """Robustly parse a JSON object out of an LLM response.

    Handles ```json fences, leading/trailing prose, and trailing commas.
    Raises :class:`LLMError` when no object can be recovered.
    """

    if raw is None:
        raise LLMError("Empty LLM response")
    text = raw.strip()
    if not text:
        raise LLMError("Empty LLM response")

    fence = _JSON_FENCE.search(text)
    if fence:
        text = fence.group(1).strip()

    candidates = [text]
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end > start:
        candidates.append(text[start : end + 1])

    for candidate in candidates:
        for attempt in (candidate, _strip_trailing_commas(candidate)):
            try:
                data = json.loads(attempt)
            except json.JSONDecodeError:
                continue
            if isinstance(data, dict):
                return data
            if isinstance(data, list):
                return {"items": data}

    raise LLMError(f"Could not parse JSON from LLM response: {raw[:200]!r}")


def parse_json_array(raw: str) -> list[dict]:
    """Robustly parse a JSON array out of an LLM response.

    Handles ```json fences, surrounding prose, a top-level array, and arrays
    wrapped in an object (e.g. ``{"items": [...]}``).  Raises
    :class:`LLMError` when no array can be recovered.
    """

    if raw is None:
        raise LLMError("Empty LLM response")
    text = raw.strip()
    if not text:
        raise LLMError("Empty LLM response")

    fence = _JSON_FENCE.search(text)
    if fence:
        text = fence.group(1).strip()

    candidates: list[str] = [text]
    start = text.find("[")
    if start != -1:
        candidates.append(text[start:])
        end = text.rfind("]")
        if end > start:
            candidates.append(text[start : end + 1])

    for candidate in candidates:
        for attempt in (candidate, _strip_trailing_commas(candidate)):
            parsed: Any
            try:
                parsed = json.loads(attempt)
            except json.JSONDecodeError:
                parsed = _raw_decode_array(attempt)
            array = _coerce_array(parsed)
            if array is not None:
                return array

    raise LLMError(f"Could not parse JSON array from LLM response: {raw[:200]!r}")


def _raw_decode_array(text: str) -> Any:
    """Extract a leading JSON array even if followed by trailing prose."""

    start = text.find("[")
    if start == -1:
        return None
    try:
        data, _ = json.JSONDecoder().raw_decode(text[start:])
    except json.JSONDecodeError:
        return None
    return data


def _coerce_array(data: Any) -> list[dict] | None:
    if data is None:
        return None
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    if isinstance(data, dict):
        for key in ("items", "results", "analyses", "data"):
            value = data.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
        for value in data.values():
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
    return None


def _strip_trailing_commas(text: str) -> str:
    return re.sub(r",(\s*[}\]])", r"\1", text)
