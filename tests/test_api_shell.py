"""OpenAI-compatible shell contracts.

Pins the health endpoint, the honest no-pack fallback and the error shape
OpenAI clients expect.
"""
from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app
from engine import __version__

client = TestClient(app)


def test_healthz_reports_ok_version_and_axis_max():
    response = client.get("/healthz")
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["version"] == __version__
    assert body["axis_max"] == 100


def test_models_list_is_openai_shaped_and_empty():
    response = client.get("/v1/models")
    assert response.status_code == 200
    body = response.json()
    assert body["object"] == "list"
    assert body["data"] == []


def test_chat_without_pack_returns_openai_model_not_found():
    response = client.post(
        "/v1/chat/completions",
        json={
            "model": "some-character",
            "messages": [{"role": "user", "content": "hi"}],
        },
    )
    assert response.status_code == 404
    error = response.json()["error"]
    assert error["code"] == "model_not_found"
    assert error["param"] == "model"
    assert "some-character" in error["message"]


def test_chat_ignores_unknown_openai_fields():
    """Drop-in compatibility: unknown client fields must not 422."""
    response = client.post(
        "/v1/chat/completions",
        json={
            "model": "some-character",
            "messages": [{"role": "user", "content": "hi"}],
            "presence_penalty": 0.5,
            "tools": [],
            "n": 1,
        },
    )
    # Reaches the handler (and its honest 404), not a validation error.
    assert response.status_code == 404


def test_chat_requires_model_and_messages():
    response = client.post("/v1/chat/completions", json={"model": "x"})
    assert response.status_code == 422
    response = client.post(
        "/v1/chat/completions",
        json={"model": "x", "messages": []},
    )
    assert response.status_code == 422
