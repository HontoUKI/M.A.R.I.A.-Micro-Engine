"""Atomic JSON persistence contracts.

Verifies that:
- save_json_atomic writes valid JSON and creates parents;
- load_json returns the default on missing/empty/corrupt files;
- a failed save never corrupts the existing file (exception propagates,
  the original stays intact);
- temp files never linger, on success or on failure;
- the default is never a shared mutable object between calls.
"""
from __future__ import annotations

import json
import os

import pytest

from engine.io import json_store
from engine.io.json_store import (
    ensure_parent_dir,
    load_json,
    save_json_atomic,
    save_text_atomic,
)


def _tmp_files(directory):
    return [name for name in os.listdir(directory) if name.startswith(".tmp_")]


# ---------------------------------------------------------------- happy path


def test_save_json_atomic_writes_valid_json(tmp_path):
    target = tmp_path / "state.json"
    payload = {"affection": 25.5, "trust": 20.0, "bond": 1.0}

    save_json_atomic(str(target), payload)

    assert target.exists()
    with open(target, encoding="utf-8") as f:
        loaded = json.load(f)
    assert loaded == payload


def test_save_json_atomic_creates_parent_dir(tmp_path):
    target = tmp_path / "deep" / "nested" / "state.json"
    save_json_atomic(str(target), {"a": 1})
    assert target.exists()


def test_save_json_atomic_preserves_unicode_by_default(tmp_path):
    target = tmp_path / "unicode.json"
    save_json_atomic(str(target), {"name": "Café"})
    raw = target.read_text(encoding="utf-8")
    # ensure_ascii=False — non-ASCII stays as-is, not \uXXXX escapes.
    assert "Café" in raw
    assert "\\u" not in raw


def test_save_json_atomic_compact_indent_none(tmp_path):
    target = tmp_path / "compact.json"
    save_json_atomic(str(target), [1, 2, 3], indent=None)
    raw = target.read_text(encoding="utf-8")
    assert "\n" not in raw


def test_save_json_atomic_does_not_leave_tmp_files(tmp_path):
    target = tmp_path / "state.json"
    save_json_atomic(str(target), {"a": 1})
    save_json_atomic(str(target), {"a": 2})
    assert _tmp_files(str(tmp_path)) == []


# ---------------------------------------------------------------- load_json


def test_load_json_returns_default_when_missing(tmp_path):
    missing = tmp_path / "nope.json"
    assert load_json(str(missing), default={"x": 1}) == {"x": 1}
    assert load_json(str(missing), default=[]) == []


def test_load_json_returns_default_when_empty(tmp_path):
    empty = tmp_path / "empty.json"
    empty.write_text("", encoding="utf-8")
    assert load_json(str(empty), default={"x": 1}) == {"x": 1}


def test_load_json_returns_default_when_corrupt(tmp_path):
    corrupt = tmp_path / "broken.json"
    corrupt.write_text("{not valid json", encoding="utf-8")
    assert load_json(str(corrupt), default={"x": 1}) == {"x": 1}


def test_load_json_returns_independent_default_each_call(tmp_path):
    """A shared mutable default would let one caller poison all others."""
    missing = tmp_path / "nope.json"
    a = load_json(str(missing), default={"x": 1})
    b = load_json(str(missing), default={"x": 1})
    a["x"] = 999
    assert b["x"] == 1


def test_load_json_returns_actual_data_when_present(tmp_path):
    target = tmp_path / "state.json"
    save_json_atomic(str(target), {"a": [1, 2, 3]})
    assert load_json(str(target), default={}) == {"a": [1, 2, 3]}


# ---------------------------------------------------------------- failure safety


def test_failed_save_does_not_corrupt_existing_file(tmp_path, monkeypatch):
    target = tmp_path / "state.json"
    save_json_atomic(str(target), {"version": 1, "good": True})
    original = target.read_bytes()

    def boom(*_a, **_k):
        raise OSError("simulated disk failure")

    monkeypatch.setattr(json_store.os, "replace", boom)

    with pytest.raises(OSError):
        save_json_atomic(str(target), {"version": 2, "good": False})

    assert target.read_bytes() == original
    assert _tmp_files(str(tmp_path)) == []


def test_failed_save_during_serialization_cleans_tmp(tmp_path):
    target = tmp_path / "state.json"
    save_json_atomic(str(target), {"ok": True})
    original = target.read_bytes()

    class Unserializable:
        pass

    with pytest.raises(TypeError):
        save_json_atomic(str(target), {"bad": Unserializable()})

    assert target.read_bytes() == original
    assert _tmp_files(str(tmp_path)) == []


# ---------------------------------------------------------------- ensure_parent_dir


def test_ensure_parent_dir_creates_missing_dirs(tmp_path):
    target = tmp_path / "a" / "b" / "c" / "file.json"
    ensure_parent_dir(str(target))
    assert (tmp_path / "a" / "b" / "c").is_dir()


def test_ensure_parent_dir_is_idempotent(tmp_path):
    target = tmp_path / "x.json"
    ensure_parent_dir(str(target))
    ensure_parent_dir(str(target))


# ---------------------------------------------------------------- save_text_atomic


def test_save_text_atomic_writes_jsonl(tmp_path):
    target = tmp_path / "log.jsonl"
    content = '{"a": 1}\n{"b": 2}\n'
    save_text_atomic(str(target), content)
    assert target.read_text(encoding="utf-8") == content
    assert _tmp_files(str(tmp_path)) == []


def test_save_text_atomic_failed_save_cleans_tmp(tmp_path, monkeypatch):
    target = tmp_path / "log.jsonl"
    save_text_atomic(str(target), "old\n")
    original = target.read_bytes()

    monkeypatch.setattr(
        json_store.os,
        "replace",
        lambda *_a, **_k: (_ for _ in ()).throw(OSError("nope")),
    )

    with pytest.raises(OSError):
        save_text_atomic(str(target), "new\n")

    assert target.read_bytes() == original
    assert _tmp_files(str(tmp_path)) == []
