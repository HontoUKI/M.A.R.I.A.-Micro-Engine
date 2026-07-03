"""Ollama client contracts, exercised against a deterministic stub session.

No test in this repository is allowed to call a live LLM server.
"""
from __future__ import annotations

import pytest
import requests

from engine.llm import LLMError, OllamaClient


class StubResponse:
    def __init__(self, status_code=200, payload=None, invalid_json=False):
        self.status_code = status_code
        self._payload = payload
        self._invalid_json = invalid_json

    def json(self):
        if self._invalid_json:
            raise ValueError("not json")
        return self._payload


class StubSession:
    """Records calls; returns queued responses or raises a queued error."""

    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error
        self.calls = []

    def post(self, url, json=None, timeout=None):
        self.calls.append({"url": url, "json": json, "timeout": timeout})
        if self.error is not None:
            raise self.error
        return self.response


def _client(session):
    return OllamaClient(
        "http://stub:11434",
        "chat-model",
        "embed-model",
        timeout_s=5.0,
        session=session,
    )


# ---------------------------------------------------------------- chat


def test_chat_returns_message_content_and_targets_chat_endpoint():
    session = StubSession(
        response=StubResponse(payload={"message": {"content": "hello"}})
    )
    out = _client(session).chat([{"role": "user", "content": "hi"}])
    assert out == "hello"
    call = session.calls[0]
    assert call["url"] == "http://stub:11434/api/chat"
    assert call["json"]["model"] == "chat-model"
    assert call["json"]["stream"] is False


def test_chat_passes_format_for_constrained_decode():
    session = StubSession(
        response=StubResponse(payload={"message": {"content": "{}"}})
    )
    _client(session).chat([{"role": "user", "content": "hi"}], fmt="json")
    assert session.calls[0]["json"]["format"] == "json"


def test_default_options_are_sent_on_every_call():
    session = StubSession(response=StubResponse(payload={"message": {"content": "x"}}))
    client = OllamaClient("http://stub", "m", "e", temperature=0.3, num_ctx=4096, session=session)
    client.chat([{"role": "user", "content": "hi"}])
    opts = session.calls[0]["json"]["options"]
    assert opts["temperature"] == 0.3
    assert opts["num_ctx"] == 4096


def test_per_call_options_override_defaults():
    session = StubSession(response=StubResponse(payload={"message": {"content": "x"}}))
    client = OllamaClient("http://stub", "m", "e", temperature=0.9, session=session)
    client.chat([{"role": "user", "content": "hi"}], options={"temperature": 0.0})
    assert session.calls[0]["json"]["options"]["temperature"] == 0.0


def test_no_options_key_when_none_configured():
    session = StubSession(response=StubResponse(payload={"message": {"content": "x"}}))
    _client(session).chat([{"role": "user", "content": "hi"}])
    assert "options" not in session.calls[0]["json"]


def test_usage_snapshot_accumulates_tokens_across_calls():
    payload = {"message": {"content": "x"}, "prompt_eval_count": 11, "eval_count": 7}
    session = StubSession(response=StubResponse(payload=payload))
    client = _client(session)
    assert client.usage_snapshot()["total_tokens"] == 0
    client.chat([{"role": "user", "content": "hi"}])
    client.chat([{"role": "user", "content": "hi"}])
    snap = client.usage_snapshot()
    assert snap["prompt_tokens"] == 22
    assert snap["completion_tokens"] == 14
    assert snap["total_tokens"] == 36
    assert snap["calls"] == 2


def test_chat_model_override():
    session = StubSession(
        response=StubResponse(payload={"message": {"content": "x"}})
    )
    _client(session).chat([{"role": "user", "content": "hi"}], model="other")
    assert session.calls[0]["json"]["model"] == "other"


def test_chat_raises_on_unexpected_payload_shape():
    session = StubSession(response=StubResponse(payload={"nope": True}))
    with pytest.raises(LLMError):
        _client(session).chat([{"role": "user", "content": "hi"}])


def test_chat_raises_on_non_string_content():
    session = StubSession(
        response=StubResponse(payload={"message": {"content": 42}})
    )
    with pytest.raises(LLMError):
        _client(session).chat([{"role": "user", "content": "hi"}])


# ---------------------------------------------------------------- embed


def test_embed_returns_first_vector_as_floats():
    session = StubSession(
        response=StubResponse(payload={"embeddings": [[1, 2.5, 3]]})
    )
    vector = _client(session).embed("text")
    assert vector == [1.0, 2.5, 3.0]
    assert session.calls[0]["url"] == "http://stub:11434/api/embed"
    assert session.calls[0]["json"]["model"] == "embed-model"


def test_embed_raises_on_empty_embeddings():
    session = StubSession(response=StubResponse(payload={"embeddings": []}))
    with pytest.raises(LLMError):
        _client(session).embed("text")


# ---------------------------------------------------------------- transport failures


def test_unreachable_backend_raises_llm_error():
    session = StubSession(error=requests.ConnectionError("refused"))
    with pytest.raises(LLMError):
        _client(session).chat([{"role": "user", "content": "hi"}])


def test_http_error_status_raises_llm_error():
    session = StubSession(response=StubResponse(status_code=500))
    with pytest.raises(LLMError):
        _client(session).chat([{"role": "user", "content": "hi"}])


def test_non_json_payload_raises_llm_error():
    session = StubSession(response=StubResponse(invalid_json=True))
    with pytest.raises(LLMError):
        _client(session).embed("text")
