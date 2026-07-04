"""End-to-end API tests for a live chat turn with a loaded pack.

The engine service is injected with a stub LLM via FastAPI dependency
overrides, so a full turn runs without any real backend.
"""
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from app.deps import get_service
from app.main import app
from app.service import EngineService
from engine.llm import LLMError
from engine.registry import PackRegistry
from tests._packs import make_pack


class FakeLLM:
    def __init__(self, *, tag="warmth", reply="Hello there.", voice_error=False):
        self.tag = tag
        self.reply = reply
        self.voice_error = voice_error

    def chat(self, messages, *, model=None, fmt=None, options=None):
        if fmt is not None:
            return json.dumps({"tag": self.tag})
        if self.voice_error:
            raise LLMError("backend down")
        return self.reply

    def embed(self, text, *, model=None):  # pragma: no cover - memory off here
        return [0.0, 0.0, 0.0]


def _service(**llm_kwargs) -> EngineService:
    pack = make_pack()
    registry = PackRegistry({pack.meta.name: pack})
    return EngineService(registry=registry, llm=FakeLLM(**llm_kwargs))


@pytest.fixture
def client_with(monkeypatch):
    def _make(service: EngineService) -> TestClient:
        app.dependency_overrides[get_service] = lambda: service
        return TestClient(app)

    yield _make
    app.dependency_overrides.pop(get_service, None)


# ---------------------------------------------------------------- models


def test_models_lists_loaded_pack(client_with):
    client = client_with(_service())
    body = client.get("/v1/models").json()
    assert [m["id"] for m in body["data"]] == ["aria"]


# ---------------------------------------------------------------- chat


def test_chat_returns_openai_completion_with_reply(client_with):
    client = client_with(_service(reply="So kind of you."))
    resp = client.post(
        "/v1/chat/completions",
        json={"model": "aria", "messages": [{"role": "user", "content": "you're lovely"}]},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["object"] == "chat.completion"
    assert body["model"] == "aria"
    assert body["choices"][0]["message"]["content"] == "So kind of you."
    assert body["choices"][0]["message"]["role"] == "assistant"
    # OpenAI-shaped usage is always present (zero when the stub reports none).
    assert set(body["usage"]) >= {"prompt_tokens", "completion_tokens", "total_tokens"}


def test_chat_exposes_engine_extension(client_with):
    client = client_with(_service(tag="warmth"))
    body = client.post(
        "/v1/chat/completions",
        json={"model": "aria", "messages": [{"role": "user", "content": "hi"}]},
    ).json()
    ext = body["x_micro_engine"]
    assert ext["tag"] == "warmth"
    # warmth delta over 20/10/0 baseline.
    assert ext["axes"]["affection"] == 25
    assert ext["sprite"] is None
    # The explainable-change signals are always present (stage is null when the
    # pack declares none).
    assert ext["stage"] is None
    assert ext["stage_changed"] is False


def test_unknown_model_returns_404(client_with):
    client = client_with(_service())
    resp = client.post(
        "/v1/chat/completions",
        json={"model": "ghost", "messages": [{"role": "user", "content": "hi"}]},
    )
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "model_not_found"


def test_conversation_not_ending_in_user_returns_400(client_with):
    client = client_with(_service())
    resp = client.post(
        "/v1/chat/completions",
        json={
            "model": "aria",
            "messages": [{"role": "assistant", "content": "I spoke last"}],
        },
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "empty_conversation"


def test_backend_failure_returns_503(client_with):
    client = client_with(_service(voice_error=True))
    resp = client.post(
        "/v1/chat/completions",
        json={"model": "aria", "messages": [{"role": "user", "content": "hi"}]},
    )
    assert resp.status_code == 503
    assert resp.json()["error"]["code"] == "llm_unavailable"


# ---------------------------------------------------------------- session state


def test_session_state_accumulates_across_turns(client_with):
    client = client_with(_service(tag="warmth"))
    payload = {
        "model": "aria",
        "messages": [{"role": "user", "content": "you're great"}],
        "user": "alice",
    }
    first = client.post("/v1/chat/completions", json=payload).json()
    second = client.post("/v1/chat/completions", json=payload).json()
    assert first["x_micro_engine"]["axes"]["affection"] == 25  # 20 + 5
    assert second["x_micro_engine"]["axes"]["affection"] == 30  # + 5 again


def test_history_days_transcript_and_clear(client_with):
    client = client_with(_service(tag="warmth"))
    payload = {
        "model": "aria",
        "messages": [{"role": "user", "content": "hi there"}],
        "user": "alice",
    }
    client.post("/v1/chat/completions", json=payload)

    days = client.get("/sessions/aria/days", params={"user": "alice"}).json()["days"]
    assert len(days) == 1

    turns = client.get("/sessions/aria/transcript", params={"user": "alice"}).json()["turns"]
    assert turns[0]["user"] == "hi there"

    cleared = client.request("DELETE", "/sessions/aria/transcript", params={"user": "alice"})
    assert cleared.json()["cleared"] == 1
    assert client.get("/sessions/aria/days", params={"user": "alice"}).json()["days"] == []


def test_reset_relationship_endpoint(client_with):
    client = client_with(_service(tag="warmth"))
    payload = {
        "model": "aria",
        "messages": [{"role": "user", "content": "you're great"}],
        "user": "bob",
    }
    client.post("/v1/chat/completions", json=payload)
    second = client.post("/v1/chat/completions", json=payload).json()
    assert second["x_micro_engine"]["axes"]["affection"] == 30  # 20 + 5 + 5

    client.post("/sessions/aria/reset", params={"user": "bob"})
    after = client.post("/v1/chat/completions", json=payload).json()
    assert after["x_micro_engine"]["axes"]["affection"] == 25  # baseline + one turn


def test_history_endpoints_404_for_unknown_model(client_with):
    client = client_with(_service())
    assert client.get("/sessions/ghost/days").status_code == 404
    assert client.post("/sessions/ghost/reset").status_code == 404


def test_sessions_are_isolated_by_user(client_with):
    service = _service(tag="warmth")
    client = client_with(service)
    base = {"model": "aria", "messages": [{"role": "user", "content": "you're great"}]}

    client.post("/v1/chat/completions", json={**base, "user": "alice"})
    client.post("/v1/chat/completions", json={**base, "user": "alice"})
    bob = client.post("/v1/chat/completions", json={**base, "user": "bob"}).json()

    # Bob's first turn is unaffected by alice's two turns.
    assert bob["x_micro_engine"]["axes"]["affection"] == 25
