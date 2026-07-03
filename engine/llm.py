"""Minimal Ollama client.

The engine needs exactly two backend calls: `chat` (voicing and moment-tag
classification) and `embed` (vector memory). The HTTP session is injectable
so tests never touch a real server — pytest runs against deterministic stubs.
"""
from __future__ import annotations

from typing import Any

import requests

from engine.logging_config import get_logger

_log = get_logger("llm")


class LLMError(RuntimeError):
    """Raised when the LLM backend fails or returns an unusable payload."""


class OllamaClient:
    """Thin wrapper around the Ollama HTTP API."""

    def __init__(
        self,
        base_url: str,
        chat_model: str,
        embed_model: str,
        *,
        timeout_s: float = 120.0,
        temperature: float | None = None,
        num_ctx: int | None = None,
        session: Any = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._chat_model = chat_model
        self._embed_model = embed_model
        self._timeout_s = timeout_s
        # Default Ollama sampling options applied to every chat call; a
        # per-call `options` dict overrides these key by key.
        self._default_options: dict[str, Any] = {}
        if temperature is not None:
            self._default_options["temperature"] = float(temperature)
        if num_ctx is not None:
            self._default_options["num_ctx"] = int(num_ctx)
        self._session = session if session is not None else requests.Session()
        # Running token totals across this client's lifetime. The runtime reads
        # deltas of this to report per-turn usage.
        self._usage = {"prompt_tokens": 0, "completion_tokens": 0, "calls": 0}

    def usage_snapshot(self) -> dict[str, int]:
        """A copy of the cumulative token counters, with a derived total."""
        snap = dict(self._usage)
        snap["total_tokens"] = snap["prompt_tokens"] + snap["completion_tokens"]
        return snap

    def _record_usage(self, model: str, data: Any) -> None:
        prompt = int(data.get("prompt_eval_count") or 0) if isinstance(data, dict) else 0
        completion = int(data.get("eval_count") or 0) if isinstance(data, dict) else 0
        self._usage["prompt_tokens"] += prompt
        self._usage["completion_tokens"] += completion
        self._usage["calls"] += 1
        _log.info(
            "chat tokens: prompt=%d completion=%d total=%d (model=%s)",
            prompt,
            completion,
            prompt + completion,
            model,
        )

    def chat(
        self,
        messages: list[dict[str, str]],
        *,
        model: str | None = None,
        fmt: str | dict[str, Any] | None = None,
        options: dict[str, Any] | None = None,
    ) -> str:
        """Non-streaming chat call; returns the assistant message content.

        `fmt` maps to Ollama's `format` field ("json" or a JSON schema) and
        is how constrained decoding for the tag classifier is enforced.
        """
        payload: dict[str, Any] = {
            "model": model or self._chat_model,
            "messages": list(messages),
            "stream": False,
        }
        if fmt is not None:
            payload["format"] = fmt
        merged_options = {**self._default_options, **(options or {})}
        if merged_options:
            payload["options"] = merged_options
        data = self._post("/api/chat", payload)
        try:
            content = data["message"]["content"]
        except (KeyError, TypeError) as exc:
            raise LLMError(f"unexpected chat payload shape: {type(data).__name__}") from exc
        if not isinstance(content, str):
            raise LLMError("chat content is not a string")
        self._record_usage(payload["model"], data)
        return content

    def embed(self, text: str, *, model: str | None = None) -> list[float]:
        """Return the embedding vector for a single input text."""
        payload = {"model": model or self._embed_model, "input": text}
        data = self._post("/api/embed", payload)
        try:
            vector = data["embeddings"][0]
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMError(f"unexpected embed payload shape: {type(data).__name__}") from exc
        return [float(x) for x in vector]

    def _post(self, path: str, payload: dict[str, Any]) -> Any:
        url = f"{self._base_url}{path}"
        try:
            response = self._session.post(url, json=payload, timeout=self._timeout_s)
        except requests.RequestException as exc:
            raise LLMError(f"LLM backend unreachable at {url}") from exc
        if response.status_code != 200:
            raise LLMError(f"LLM backend returned HTTP {response.status_code} for {path}")
        try:
            return response.json()
        except ValueError as exc:
            raise LLMError("LLM backend returned a non-JSON payload") from exc
