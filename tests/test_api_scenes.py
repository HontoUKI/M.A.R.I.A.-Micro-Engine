"""End-to-end API tests for the v0.2 scene surface, against a stub LLM."""
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from app.deps import get_service
from app.main import app
from app.service import EngineService
from engine.registry import PackRegistry
from engine.scene.models import USER_ID, ScenePack
from engine.scene.registry import SceneRegistry
from tests._packs import make_pack


class SceneLLM:
    def __init__(self, *, speaker="aria", tag="warmth", target=USER_ID, reply="Hi."):
        self.speaker, self.tag, self.target, self.reply = speaker, tag, target, reply

    def chat(self, messages, *, model=None, fmt=None, options=None):
        if fmt is None:
            return self.reply
        if "speaker" in fmt.get("properties", {}):
            return json.dumps({"speaker": self.speaker})
        return json.dumps({"tag": self.tag, "target": self.target})

    def embed(self, text, *, model=None):  # pragma: no cover
        return [0.0]


def _packs():
    return {
        "aria": make_pack(meta={
            "name": "aria", "display_name": "Aria", "version": "0.1.0",
            "license": "x", "author": "y", "fallback_tag": "neutral", "description": "calm",
        }),
        "bram": make_pack(meta={
            "name": "bram", "display_name": "Bram", "version": "0.1.0",
            "license": "x", "author": "y", "fallback_tag": "neutral", "description": "gruff",
        }),
    }


def _scene(**over) -> ScenePack:
    data = {
        "spec_version": 1,
        "meta": {"name": "cafe", "display_name": "Cafe", "version": "0.1.0",
                 "license": "x", "author": "y"},
        "setting": "A quiet cafe.",
        "cast": ["aria", "bram"],
    }
    data.update(over)
    return ScenePack.model_validate(data)


def _service(tmp_path, llm=None, packs=None, scene=None) -> EngineService:
    return EngineService(
        registry=PackRegistry(packs or _packs()),
        scene_registry=SceneRegistry({"cafe": scene or _scene()}),
        llm=llm or SceneLLM(),
        scenes_dir=str(tmp_path / "scenes"),
        sessions_dir=str(tmp_path / "sessions"),
    )


@pytest.fixture
def client_with():
    def _make(service: EngineService) -> TestClient:
        app.dependency_overrides[get_service] = lambda: service
        return TestClient(app)

    yield _make
    app.dependency_overrides.pop(get_service, None)


def test_list_scenes(client_with, tmp_path):
    client = client_with(_service(tmp_path))
    body = client.get("/scenes").json()
    assert body["data"][0]["id"] == "cafe"
    assert body["data"][0]["cast"] == ["aria", "bram"]
    assert body["data"][0]["mode"] == "group_chat"


def test_advance_returns_speaker_reply_and_feelings(client_with, tmp_path):
    client = client_with(_service(tmp_path, llm=SceneLLM(speaker="aria", reply="Welcome!")))
    resp = client.post("/scenes/cafe/advance", json={"user": "u1", "message": "hi all"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["speaker"] == "aria"
    assert body["reply"] == "Welcome!"
    assert body["feeling"]["affection"] == 5  # warmth on aria->user
    # Bram witnessed (recorded even if his reaction is neutral).
    assert [w["actor"] for w in body["witnessed"]] == ["bram"]


def test_scene_state_persists_across_turns(client_with, tmp_path):
    client = client_with(_service(tmp_path, llm=SceneLLM(speaker="aria", target=USER_ID)))
    client.post("/scenes/cafe/advance", json={"user": "u1", "message": "you're great"})
    client.post("/scenes/cafe/advance", json={"user": "u1", "message": "still great"})
    edges = client.get("/scenes/cafe/matrix", params={"user": "u1"}).json()["edges"]
    assert edges["aria->user"]["affection"] == 10  # 5 + 5 over two turns

    lines = client.get("/scenes/cafe/transcript", params={"user": "u1"}).json()["lines"]
    assert lines[0] == {"speaker": USER_ID, "content": "you're great"}
    assert len(lines) == 4  # two user lines + two aria replies


def test_play_mode_run_returns_a_sequence_of_turns(client_with, tmp_path):
    scene = _scene(mode="play")
    client = client_with(_service(tmp_path, scene=scene,
                                  llm=SceneLLM(speaker="aria", tag="neutral", target="bram")))
    resp = client.post(
        "/scenes/cafe/run", json={"user": "u1", "cue": "a dragon appears", "max_turns": 3}
    )
    assert resp.status_code == 200
    turns = resp.json()["turns"]
    assert len(turns) == 3
    assert all(t["target"] != USER_ID for t in turns)  # actors address each other


def test_run_budget_is_capped(client_with, tmp_path):
    scene = _scene(mode="play")
    client = client_with(_service(tmp_path, scene=scene,
                                  llm=SceneLLM(speaker="aria", target="bram")))
    turns = client.post("/scenes/cafe/run", json={"max_turns": 999}).json()["turns"]
    assert len(turns) == 8  # _MAX_SCENE_RUN_TURNS


def test_run_on_unknown_scene_404(client_with, tmp_path):
    client = client_with(_service(tmp_path))
    assert client.post("/scenes/ghost/run", json={"cue": "x"}).status_code == 404


def test_unknown_scene_404(client_with, tmp_path):
    client = client_with(_service(tmp_path))
    assert client.post("/scenes/ghost/advance", json={"message": "hi"}).status_code == 404
    assert client.get("/scenes/ghost/transcript").status_code == 404


def test_scene_with_missing_cast_pack_is_409(client_with, tmp_path):
    # Registry has only aria; the cafe scene also needs bram.
    svc = _service(tmp_path, packs={"aria": _packs()["aria"]})
    client = client_with(svc)
    resp = client.post("/scenes/cafe/advance", json={"message": "hi"})
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "scene_unavailable"


def test_bad_explicit_speaker_is_400(client_with, tmp_path):
    client = client_with(_service(tmp_path))
    resp = client.post("/scenes/cafe/advance", json={"message": "hi", "speaker": "ghost"})
    assert resp.status_code == 400


def test_reset_scene_clears_matrix_and_transcript(client_with, tmp_path):
    client = client_with(_service(tmp_path, llm=SceneLLM(speaker="aria")))
    client.post("/scenes/cafe/advance", json={"user": "u1", "message": "you're great"})
    client.post("/scenes/cafe/reset", params={"user": "u1"})
    lines = client.get("/scenes/cafe/transcript", params={"user": "u1"}).json()["lines"]
    assert lines == []
    edges = client.get("/scenes/cafe/matrix", params={"user": "u1"}).json()["edges"]
    assert edges["aria->user"]["affection"] == 0  # back to the (unseeded) baseline
