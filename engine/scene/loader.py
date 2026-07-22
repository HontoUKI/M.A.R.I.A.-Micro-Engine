"""ScenePack loader — parses and hardens a scene directory.

Like the character-pack loader, a scene is untrusted, executable-as-prompt data,
so this is the security boundary: safe YAML parsing, size limits, and an
injection scan on the prompt-bearing text (setting + scenario blocks) before a
validated `ScenePack` is handed on.
"""
from __future__ import annotations

import os
from typing import Any

import yaml
from pydantic import ValidationError

# Reuse the character-pack injection patterns — same threat, same defense.
from engine.pack.loader import _INJECTION_PATTERNS
from engine.scene.errors import (
    SceneNotFoundError,
    SceneSecurityError,
    SceneValidationError,
    SceneVersionError,
)
from engine.scene.models import ScenePack

SUPPORTED_SPEC_VERSION = 1

SCENE_FILENAME = "scene.yaml"

# Hard limits (mirror the character-pack loader).
MAX_YAML_BYTES = 256 * 1024
MAX_SETTING_CHARS = 4000
MAX_BLOCK_CHARS = 2000
MAX_DESCRIPTION_CHARS = 1000


def load_scene(scene_dir: str) -> ScenePack:
    """Load, validate and harden a scene directory.

    Raises a `SceneError` subclass on any failure; never returns a partially
    valid scene.
    """
    scene_path = os.path.join(scene_dir, SCENE_FILENAME)
    if not os.path.isfile(scene_path):
        raise SceneNotFoundError(f"no {SCENE_FILENAME} in {scene_dir!r}")

    size = os.path.getsize(scene_path)
    if size > MAX_YAML_BYTES:
        raise SceneSecurityError(
            f"{SCENE_FILENAME} is {size} bytes; limit is {MAX_YAML_BYTES}"
        )

    raw = _safe_parse(scene_path)
    _spec_version_gate(raw)
    scene = _validate_shape(raw)
    _enforce_content_limits(scene)
    return scene


def _safe_parse(scene_path: str) -> dict[str, Any]:
    with open(scene_path, encoding="utf-8") as fh:
        text = fh.read()
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise SceneValidationError(f"scene.yaml is not valid YAML: {exc}") from exc
    if not isinstance(data, dict):
        raise SceneValidationError("scene.yaml must be a mapping at the top level")
    return data


def _spec_version_gate(raw: dict[str, Any]) -> None:
    version = raw.get("spec_version")
    if version is None:
        raise SceneValidationError("scene.yaml is missing 'spec_version'")
    if version != SUPPORTED_SPEC_VERSION:
        raise SceneVersionError(
            f"scene targets spec_version {version!r}; this engine supports "
            f"{SUPPORTED_SPEC_VERSION}"
        )


def _validate_shape(raw: dict[str, Any]) -> ScenePack:
    try:
        return ScenePack.model_validate(raw)
    except ValidationError as exc:
        raise SceneValidationError(f"scene failed schema validation: {exc}") from exc


def _enforce_content_limits(scene: ScenePack) -> None:
    if len(scene.setting) > MAX_SETTING_CHARS:
        raise SceneSecurityError(
            f"setting is {len(scene.setting)} chars; limit is {MAX_SETTING_CHARS}"
        )
    _scan_injection("setting", scene.setting)

    for actor, tags in scene.scenario_tags.items():
        for tag in tags:
            if len(tag.description) > MAX_DESCRIPTION_CHARS:
                raise SceneSecurityError(
                    f"scenario tag {actor}/{tag.id} description is "
                    f"{len(tag.description)} chars; limit is {MAX_DESCRIPTION_CHARS}"
                )
            if len(tag.block) > MAX_BLOCK_CHARS:
                raise SceneSecurityError(
                    f"scenario tag {actor}/{tag.id} block is {len(tag.block)} "
                    f"chars; limit is {MAX_BLOCK_CHARS}"
                )
            _scan_injection(f"scenario[{actor}/{tag.id}].description", tag.description)
            _scan_injection(f"scenario[{actor}/{tag.id}].block", tag.block)


def _scan_injection(where: str, text: str) -> None:
    for pattern in _INJECTION_PATTERNS:
        if pattern.search(text):
            raise SceneSecurityError(
                f"{where} contains a prompt-injection pattern: {pattern.pattern!r}"
            )
