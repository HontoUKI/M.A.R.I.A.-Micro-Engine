"""OpenAI backend contracts, against a deterministic stub session."""
from __future__ import annotations

import pytest
import requests

from engine.llm import LLMError, OpenAIClient


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
    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error
        self.calls = []

    def post(self, url, json=None, timeout=None, headers=None):
        self.calls.append({"url": url, "json": json, "timeout": timeout, "headers": headers})
        if self.error is not None:
            raise self.error
        return self.response


def _client(session, **kwargs):
    return OpenAIClient(
        "sk-test",
        base_url="https://api.test/v1",
        chat_model="gpt-4o-mini",
        embed_model="text-embedding-3-small",
        timeout_s=5.0,
        session=session,
        **kwargs,
    )


def _chat_ok(content="hi", prompt=5, completion=3):
    return StubResponse(
        payload={
            "choices": [{"message": {"content": content}}],
            "usage": {"prompt_tokens": prompt, "completion_tokens": completion},
        }
    )


# ---------------------------------------------------------------- chat


def test_chat_sends_bearer_key_and_targets_chat_completions():
    session = StubSession(response=_chat_ok("hello"))
    out = _client(session).chat([{"role": "user", "content": "hi"}])
    assert out == "hello"
    call = session.calls[0]
    assert call["url"] == "https://api.test/v1/chat/completions"
    assert call["headers"]["Authorization"] == "Bearer sk-test"
    assert call["json"]["model"] == "gpt-4o-mini"


def test_fmt_schema_becomes_openai_response_format():
    session = StubSession(response=_chat_ok())
    schema = {"type": "object", "properties": {"tag": {"type": "string", "enum": ["a", "b"]}}}
    _client(session).chat([{"role": "user", "content": "hi"}], fmt=schema)
    rf = session.calls[0]["json"]["response_format"]
    assert rf["type"] == "json_schema"
    assert rf["json_schema"]["strict"] is True
    assert rf["json_schema"]["schema"]["additionalProperties"] is False


def test_temperature_default_and_per_call_override():
    session = StubSession(response=_chat_ok())
    client = _client(session, temperature=0.7)
    client.chat([{"role": "user", "content": "hi"}])
    assert session.calls[0]["json"]["temperature"] == 0.7
    client.chat([{"role": "user", "content": "hi"}], options={"temperature": 0.0})
    assert session.calls[1]["json"]["temperature"] == 0.0


def test_usage_is_read_from_the_response():
    session = StubSession(response=_chat_ok(prompt=12, completion=8))
    client = _client(session)
    client.chat([{"role": "user", "content": "hi"}])
    snap = client.usage_snapshot()
    assert snap["prompt_tokens"] == 12
    assert snap["completion_tokens"] == 8
    assert snap["total_tokens"] == 20


def test_unexpected_chat_shape_raises():
    session = StubSession(response=StubResponse(payload={"nope": True}))
    with pytest.raises(LLMError):
        _client(session).chat([{"role": "user", "content": "hi"}])


def test_http_error_raises_llm_error():
    session = StubSession(response=StubResponse(status_code=401))
    with pytest.raises(LLMError):
        _client(session).chat([{"role": "user", "content": "hi"}])


def test_unreachable_backend_raises_llm_error():
    session = StubSession(error=requests.ConnectionError("refused"))
    with pytest.raises(LLMError):
        _client(session).chat([{"role": "user", "content": "hi"}])


# ---------------------------------------------------------------- embed


def test_embed_parses_data_embedding():
    session = StubSession(response=StubResponse(payload={"data": [{"embedding": [1, 2.5, 3]}]}))
    assert _client(session).embed("text") == [1.0, 2.5, 3.0]
    assert session.calls[0]["url"] == "https://api.test/v1/embeddings"
