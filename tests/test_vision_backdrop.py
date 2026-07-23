"""Scene backdrop captioning: validation, runtime pinning, and the API."""
from __future__ import annotations

import base64
import json

import pytest
from fastapi.testclient import TestClient

from app.deps import get_service
from app.main import app
from app.service import EngineService
from engine.registry import PackRegistry
from engine.scene.models import ScenePack
from engine.scene.registry import SceneRegistry
from engine.vision import (
    BadImageError,
    VisionUnavailableError,
    caption_backdrop,
    validate_image_b64,
)
from tests._packs import make_pack

_PNG = base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"x" * 32).decode()


# ---------------------------------------------------------------- validation


def test_validate_accepts_plain_and_data_url():
    assert validate_image_b64(_PNG) == _PNG
    assert validate_image_b64("data:image/png;base64," + _PNG) == _PNG


def test_validate_rejects_garbage_and_empty():
    with pytest.raises(BadImageError):
        validate_image_b64("not base64!!!")
    with pytest.raises(BadImageError):
        validate_image_b64("")


# ---------------------------------------------------------------- captioner


class VisionLLM:
    def caption(self, image_b64, prompt, *, model=None):
        return "A candlelit stone hall, rain against tall windows."


class NoVisionLLM:
    pass


def test_caption_backdrop_uses_the_backend():
    out = caption_backdrop(VisionLLM(), _PNG)
    assert "candlelit" in out


def test_caption_backdrop_without_vision_raises():
    with pytest.raises(VisionUnavailableError):
        caption_backdrop(NoVisionLLM(), _PNG)


# ---------------------------------------------------------------- API


class SceneLLM(VisionLLM):
    def chat(self, messages, *, model=None, fmt=None, options=None):
        if fmt is None:
            return "..."
        if "speaker" in fmt.get("properties", {}):
            return json.dumps({"speaker": "aria"})
        return json.dumps({"tag": "neutral", "target": "user"})

    def embed(self, text, *, model=None):  # pragma: no cover
        return [0.0]


def _packs():
    return {
        "aria": make_pack(meta={"name": "aria", "display_name": "Aria", "version": "0.1.0",
                                "license": "x", "author": "y", "fallback_tag": "neutral"}),
        "bram": make_pack(meta={"name": "bram", "display_name": "Bram", "version": "0.1.0",
                                "license": "x", "author": "y", "fallback_tag": "neutral"}),
    }


def _scene():
    return ScenePack.model_validate({
        "spec_version": 1,
        "meta": {"name": "hall", "display_name": "Hall", "version": "0.1.0",
                 "license": "x", "author": "y"},
        "setting": "An empty room.",
        "cast": ["aria", "bram"],
    })


@pytest.fixture
def client_with():
    def _make(service):
        app.dependency_overrides[get_service] = lambda: service
        return TestClient(app)

    yield _make
    app.dependency_overrides.pop(get_service, None)


def _service(tmp_path, llm):
    return EngineService(
        registry=PackRegistry(_packs()),
        scene_registry=SceneRegistry({"hall": _scene()}),
        llm=llm,
        scenes_dir=str(tmp_path / "scenes"),
        sessions_dir=str(tmp_path / "sessions"),
    )


def test_backdrop_upload_captions_and_pins(client_with, tmp_path):
    client = client_with(_service(tmp_path, SceneLLM()))
    resp = client.post("/scenes/hall/backdrop", json={"user": "u1", "image": _PNG})
    assert resp.status_code == 200
    assert "candlelit" in resp.json()["backdrop"]
    # It persists and is read back.
    got = client.get("/scenes/hall/backdrop", params={"user": "u1"}).json()["backdrop"]
    assert "candlelit" in got


def test_backdrop_supersedes_the_authored_setting_in_the_prompt(client_with, tmp_path):
    captured = {}

    class Cap(SceneLLM):
        def chat(self, messages, *, model=None, fmt=None, options=None):
            if fmt is None:
                captured["system"] = messages[0]["content"]
            return super().chat(messages, model=model, fmt=fmt, options=options)

    svc = _service(tmp_path, Cap())
    client = client_with(svc)
    client.post("/scenes/hall/backdrop", json={"user": "u1", "image": _PNG})
    client.post("/scenes/hall/advance", json={"user": "u1", "message": "hi"})
    assert "candlelit" in captured["system"]  # backdrop caption pinned
    assert "An empty room." not in captured["system"]  # authored setting replaced


def test_backdrop_bad_image_is_400(client_with, tmp_path):
    client = client_with(_service(tmp_path, SceneLLM()))
    resp = client.post("/scenes/hall/backdrop", json={"image": "!!!not base64!!!"})
    assert resp.status_code == 400


def test_backdrop_without_vision_backend_is_501(client_with, tmp_path):
    class Plain:
        def chat(self, messages, *, model=None, fmt=None, options=None):
            return json.dumps({"tag": "neutral", "target": "user"}) if fmt else "hi"

        def embed(self, text, *, model=None):  # pragma: no cover
            return [0.0]

    client = client_with(_service(tmp_path, Plain()))
    resp = client.post("/scenes/hall/backdrop", json={"image": _PNG})
    assert resp.status_code == 501
