"""Character pack loader — parses and hardens a pack directory.

A pack is untrusted, executable-as-prompt data. The loader is the security
boundary: it uses a safe YAML parser, enforces hard size limits, refuses
sprite paths that escape the pack, and scans prompt text for system-override
patterns *before* handing a validated `CharacterPack` to the engine.

Order of checks (fail fast, cheapest first):
    1. locate pack.yaml, enforce file-size ceiling;
    2. safe-parse YAML;
    3. spec_version gate;
    4. pydantic shape/balance validation;
    5. content limits + injection scan on prompt text;
    6. sprite path-traversal + existence + size checks.
"""
from __future__ import annotations

import os
import re
from typing import Any

import yaml
from pydantic import ValidationError

from engine.pack.errors import (
    PackNotFoundError,
    PackSecurityError,
    PackValidationError,
    PackVersionError,
)
from engine.pack.models import CharacterPack

SUPPORTED_SPEC_VERSION = 1

PACK_FILENAME = "pack.yaml"
SPRITES_DIRNAME = "sprites"

# Hard limits (mirror CHARACTER_PACK_SPEC.md §4).
MAX_YAML_BYTES = 256 * 1024
MAX_IDENTITY_CHARS = 4000
MAX_BLOCK_CHARS = 2000
MAX_INVARIANT_CHARS = 1000
MAX_SPRITES = 64
MAX_SPRITE_BYTES = 4 * 1024 * 1024

_ALLOWED_SPRITE_EXT = (".png", ".jpg", ".jpeg", ".webp")

# Prompt-injection / system-override markers. Defense-in-depth: a curated
# gallery still gets human review, but these block the obvious attacks in
# unverified/forked packs.
_INJECTION_PATTERNS = tuple(
    re.compile(p, re.IGNORECASE)
    for p in (
        r"ignore\s+(all\s+)?(previous|prior|above)\s+instructions",
        r"disregard\s+(all\s+)?(previous|prior|above)",
        r"you\s+are\s+now\b",
        r"system\s*prompt\s*[:=]",
        r"</?\s*system\s*>",
        r"\bBEGIN\s+SYSTEM\b",
        r"forget\s+(everything|all\s+previous)",
        r"reveal\s+your\s+(system\s+)?prompt",
    )
)


def load_pack(pack_dir: str) -> CharacterPack:
    """Load, validate and harden a character pack directory.

    Raises a `PackError` subclass on any failure; never returns a partially
    valid pack.
    """
    pack_path = os.path.join(pack_dir, PACK_FILENAME)
    if not os.path.isfile(pack_path):
        raise PackNotFoundError(f"no {PACK_FILENAME} in {pack_dir!r}")

    size = os.path.getsize(pack_path)
    if size > MAX_YAML_BYTES:
        raise PackSecurityError(
            f"{PACK_FILENAME} is {size} bytes; limit is {MAX_YAML_BYTES}"
        )

    raw = _safe_parse(pack_path)
    _spec_version_gate(raw)
    pack = _validate_shape(raw)
    _enforce_content_limits(pack)
    _check_sprites(pack, pack_dir)
    return pack


def _safe_parse(pack_path: str) -> dict[str, Any]:
    with open(pack_path, encoding="utf-8") as fh:
        text = fh.read()
    try:
        # safe_load: no arbitrary object construction, no custom tags.
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise PackValidationError(f"pack.yaml is not valid YAML: {exc}") from exc
    if not isinstance(data, dict):
        raise PackValidationError("pack.yaml must be a mapping at the top level")
    return data


def _spec_version_gate(raw: dict[str, Any]) -> None:
    version = raw.get("spec_version")
    if version is None:
        raise PackValidationError("pack.yaml is missing 'spec_version'")
    if version != SUPPORTED_SPEC_VERSION:
        raise PackVersionError(
            f"pack targets spec_version {version!r}; this engine supports "
            f"{SUPPORTED_SPEC_VERSION}"
        )


def _validate_shape(raw: dict[str, Any]) -> CharacterPack:
    try:
        return CharacterPack.model_validate(raw)
    except ValidationError as exc:
        raise PackValidationError(f"pack failed schema validation: {exc}") from exc


def _enforce_content_limits(pack: CharacterPack) -> None:
    if len(pack.identity) > MAX_IDENTITY_CHARS:
        raise PackSecurityError(
            f"identity is {len(pack.identity)} chars; limit is {MAX_IDENTITY_CHARS}"
        )
    _scan_injection("identity", pack.identity)

    for tag_id, block in pack.blocks.items():
        if len(block) > MAX_BLOCK_CHARS:
            raise PackSecurityError(
                f"block {tag_id!r} is {len(block)} chars; limit is {MAX_BLOCK_CHARS}"
            )
        _scan_injection(f"block[{tag_id}]", block)

    for idx, rule in enumerate(pack.invariants):
        if len(rule) > MAX_INVARIANT_CHARS:
            raise PackSecurityError(
                f"invariant #{idx} is {len(rule)} chars; limit is {MAX_INVARIANT_CHARS}"
            )
        _scan_injection(f"invariant[{idx}]", rule)

    for stage, block in pack.stages.items():
        if len(block) > MAX_BLOCK_CHARS:
            raise PackSecurityError(
                f"stage {stage!r} block is {len(block)} chars; limit is {MAX_BLOCK_CHARS}"
            )
        _scan_injection(f"stage[{stage}]", block)


def _scan_injection(where: str, text: str) -> None:
    for pattern in _INJECTION_PATTERNS:
        if pattern.search(text):
            raise PackSecurityError(
                f"{where} contains a prompt-injection pattern: {pattern.pattern!r}"
            )


def _check_sprites(pack: CharacterPack, pack_dir: str) -> None:
    if len(pack.sprites) > MAX_SPRITES:
        raise PackSecurityError(
            f"{len(pack.sprites)} sprites declared; limit is {MAX_SPRITES}"
        )
    sprites_root = os.path.realpath(os.path.join(pack_dir, SPRITES_DIRNAME))
    for state, filename in pack.sprites.items():
        _check_one_sprite(state, filename, sprites_root)


def _check_one_sprite(state: str, filename: str, sprites_root: str) -> None:
    # Bare filename only: no separators, no parent refs, no absolute paths.
    if (
        not filename
        or filename != os.path.basename(filename)
        or os.path.isabs(filename)
        or ".." in filename
    ):
        raise PackSecurityError(
            f"sprite for {state!r} must be a bare filename, got {filename!r}"
        )
    if not filename.lower().endswith(_ALLOWED_SPRITE_EXT):
        raise PackSecurityError(
            f"sprite {filename!r} has an unsupported extension"
        )

    resolved = os.path.realpath(os.path.join(sprites_root, filename))
    # Defense in depth against symlink escapes: the resolved path must stay
    # under sprites/.
    if os.path.commonpath([sprites_root, resolved]) != sprites_root:
        raise PackSecurityError(f"sprite {filename!r} escapes the sprites directory")
    if not os.path.isfile(resolved):
        raise PackValidationError(f"sprite file {filename!r} for {state!r} not found")
    if os.path.getsize(resolved) > MAX_SPRITE_BYTES:
        raise PackSecurityError(
            f"sprite {filename!r} exceeds {MAX_SPRITE_BYTES} bytes"
        )
