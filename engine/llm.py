"""LLM backends.

The engine needs exactly two backend calls: `chat` (voicing and moment-tag
classification) and `embed` (vector memory). Two interchangeable backends
implement them:

- `OllamaClient` — a local Ollama server (default).
- `OpenAIClient` — the OpenAI API (or any OpenAI-compatible endpoint), using
  an API key. Pick it with `LLM_BACKEND=openai`.

Both track cumulative token usage and share the same HTTP plumbing. The
session is injectable so tests never touch a real server.
"""
from __future__ import annotations

from typing import Any

import requests

from engine.logging_config import get_logger

_log = get_logger("llm")


class LLMError(RuntimeError):
    """Raised when the LLM backend fails or returns an unusable payload."""


class _HttpLLM:
    """Shared HTTP transport and token accounting for the backends."""

    def __init__(
        self,
        base_url: str,
        *,
        timeout_s: float,
        session: Any,
        headers: dict[str, str] | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout_s = timeout_s
        self._headers = headers or {}
        self._session = session if session is not None else requests.Session()
        # Running token totals across this client's lifetime. The runtime reads
        # deltas of this to report per-turn usage.
        self._usage = {"prompt_tokens": 0, "completion_tokens": 0, "calls": 0}

    def usage_snapshot(self) -> dict[str, int]:
        """A copy of the cumulative token counters, with a derived total."""
        snap = dict(self._usage)
        snap["total_tokens"] = snap["prompt_tokens"] + snap["completion_tokens"]
        return snap

    def _add_usage(self, model: str, prompt: int, completion: int) -> None:
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

    def _post(self, path: str, payload: dict[str, Any]) -> Any:
        url = f"{self._base_url}{path}"
        kwargs: dict[str, Any] = {"json": payload, "timeout": self._timeout_s}
        if self._headers:
            kwargs["headers"] = self._headers
        try:
            response = self._session.post(url, **kwargs)
        except requests.RequestException as exc:
            raise LLMError(f"LLM backend unreachable at {url}") from exc
        if response.status_code != 200:
            raise LLMError(f"LLM backend returned HTTP {response.status_code} for {path}")
        try:
            return response.json()
        except ValueError as exc:
            raise LLMError("LLM backend returned a non-JSON payload") from exc


class OllamaClient(_HttpLLM):
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
        super().__init__(base_url, timeout_s=timeout_s, session=session)
        self._chat_model = chat_model
        self._embed_model = embed_model
        # Default sampling options applied to every chat call; a per-call
        # `options` dict overrides these key by key.
        self._default_options: dict[str, Any] = {}
        if temperature is not None:
            self._default_options["temperature"] = float(temperature)
        if num_ctx is not None:
            self._default_options["num_ctx"] = int(num_ctx)

    def chat(
        self,
        messages: list[dict[str, str]],
        *,
        model: str | None = None,
        fmt: str | dict[str, Any] | None = None,
        options: dict[str, Any] | None = None,
    ) -> str:
        """Non-streaming chat call; returns the assistant message content.

        `fmt` maps to Ollama's `format` field ("json" or a JSON schema) and is
        how constrained decoding for the tag classifier is enforced.
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
        prompt = int(data.get("prompt_eval_count") or 0)
        completion = int(data.get("eval_count") or 0)
        self._add_usage(payload["model"], prompt, completion)
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

    def caption(self, image_b64: str, prompt: str, *, model: str | None = None) -> str:
        """Describe an image (base64 JPEG/PNG) with a vision-capable model.

        Used to turn an uploaded scene backdrop into pinned text. Requires the
        chosen model to be multimodal (e.g. gemma3 in Ollama)."""
        payload: dict[str, Any] = {
            "model": model or self._chat_model,
            "messages": [{"role": "user", "content": prompt, "images": [image_b64]}],
            "stream": False,
        }
        data = self._post("/api/chat", payload)
        try:
            content = data["message"]["content"]
        except (KeyError, TypeError) as exc:
            raise LLMError(f"unexpected caption payload shape: {type(data).__name__}") from exc
        if not isinstance(content, str):
            raise LLMError("caption content is not a string")
        self._add_usage(
            payload["model"], int(data.get("prompt_eval_count") or 0),
            int(data.get("eval_count") or 0),
        )
        return content.strip()


class OpenAIClient(_HttpLLM):
    """The OpenAI API (or an OpenAI-compatible endpoint), keyed by an API key.

    The key is server-side only; it goes in the Authorization header to the
    upstream and never crosses this engine's own API boundary.
    """

    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = "https://api.openai.com/v1",
        chat_model: str = "gpt-4o-mini",
        embed_model: str = "text-embedding-3-small",
        timeout_s: float = 120.0,
        temperature: float | None = None,
        session: Any = None,
    ) -> None:
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        super().__init__(base_url, timeout_s=timeout_s, session=session, headers=headers)
        self._chat_model = chat_model
        self._embed_model = embed_model
        self._temperature = temperature

    def chat(
        self,
        messages: list[dict[str, str]],
        *,
        model: str | None = None,
        fmt: str | dict[str, Any] | None = None,
        options: dict[str, Any] | None = None,
    ) -> str:
        """Non-streaming chat completion; returns the assistant message content.

        A `fmt` JSON schema (from the tag classifier) is translated into
        OpenAI's structured-output `response_format`, so the same constrained
        decoding works on either backend.
        """
        payload: dict[str, Any] = {
            "model": model or self._chat_model,
            "messages": list(messages),
        }
        temperature = (options or {}).get("temperature", self._temperature)
        if temperature is not None:
            payload["temperature"] = float(temperature)
        if isinstance(fmt, dict):
            payload["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": "structured_output",
                    "strict": True,
                    "schema": {**fmt, "additionalProperties": False},
                },
            }
        elif fmt == "json":
            payload["response_format"] = {"type": "json_object"}

        data = self._post("/chat/completions", payload)
        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMError(f"unexpected chat payload shape: {type(data).__name__}") from exc
        if not isinstance(content, str):
            raise LLMError("chat content is not a string")
        usage = data.get("usage") or {}
        prompt = int(usage.get("prompt_tokens") or 0)
        completion = int(usage.get("completion_tokens") or 0)
        self._add_usage(payload["model"], prompt, completion)
        return content

    def embed(self, text: str, *, model: str | None = None) -> list[float]:
        """Return the embedding vector for a single input text."""
        payload = {"model": model or self._embed_model, "input": text}
        data = self._post("/embeddings", payload)
        try:
            vector = data["data"][0]["embedding"]
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMError(f"unexpected embed payload shape: {type(data).__name__}") from exc
        return [float(x) for x in vector]
