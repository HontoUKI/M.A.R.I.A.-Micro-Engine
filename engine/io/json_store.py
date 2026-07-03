"""Atomic JSON persistence helpers.

Replaces unsafe `open(path, "w") + json.dump(...)` patterns: if the process
dies mid-write, the target file is left as either the old version or the new
one in full — never empty or truncated.

Atomicity guarantee:
    `os.replace(tmp, target)` is atomic on POSIX/NTFS only within a single
    volume (filesystem). The temp file is therefore always created in the
    same directory as the target. Cross-device writes are out of scope by
    design.

API:
    load_json(path, default)        — safe read; default on missing/empty/corrupt
    save_json_atomic(path, data, *, indent=2, ensure_ascii=False)
                                    — atomic write via tmp + replace
    save_text_atomic(path, text)    — same guarantee for plain text / JSONL
    ensure_parent_dir(path)         — mkdir -p for the parent directory

No business logic here, only I/O. Each module keeps defining its own JSON
schema. Ported from the public M.A.R.I.A. Core snapshot.
"""
from __future__ import annotations

import json
import os
import tempfile
from typing import Any


def ensure_parent_dir(path: str) -> None:
    """Create the parent directory when it does not exist."""
    parent = os.path.dirname(os.path.abspath(path))
    if parent:
        os.makedirs(parent, exist_ok=True)


def load_json(path: str, default: Any) -> Any:
    """Safe JSON read.

    Returns `default` (through `_clone_default` so the caller cannot mutate
    a shared object) when:
        - the file does not exist;
        - the file is empty (size == 0);
        - the JSON is corrupt (json.JSONDecodeError);
        - an I/O error occurs (PermissionError, OSError).

    `default` is usually `{}` or `[]`. Passing a pre-built object is fine —
    a shallow copy is returned for mutable types.
    """
    try:
        if not os.path.exists(path):
            return _clone_default(default)
        if os.path.getsize(path) == 0:
            return _clone_default(default)
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError, ValueError):
        return _clone_default(default)


def save_json_atomic(
    path: str,
    data: Any,
    *,
    indent: int | None = 2,
    ensure_ascii: bool = False,
    sort_keys: bool = False,
) -> None:
    """Atomic JSON write.

    Steps:
        1. ensure_parent_dir(path)
        2. mkstemp in the same directory (required for os.replace atomicity)
        3. json.dump → flush → os.fsync (data on disk, not in page cache)
        4. os.replace(tmp, path) — atomic swap
        5. on ANY error the temp file is removed, the original is untouched

    `indent=None` — for compact files (large vector payloads).
    `indent=2` — default, for human-readable state files.
    """
    ensure_parent_dir(path)
    parent = os.path.dirname(os.path.abspath(path))
    fd, tmp_path = tempfile.mkstemp(prefix=".tmp_", suffix=".json", dir=parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(
                data,
                f,
                indent=indent,
                ensure_ascii=ensure_ascii,
                sort_keys=sort_keys,
            )
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, path)
    except Exception:
        # Leave no litter next to state files; the original stays untouched.
        try:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
        except OSError:
            pass
        raise


def save_text_atomic(path: str, text: str) -> None:
    """Atomic write for arbitrary text (JSONL logs and similar)."""
    ensure_parent_dir(path)
    parent = os.path.dirname(os.path.abspath(path))
    fd, tmp_path = tempfile.mkstemp(prefix=".tmp_", suffix=".txt", dir=parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, path)
    except Exception:
        try:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
        except OSError:
            pass
        raise


def _clone_default(default: Any) -> Any:
    """Never hand the caller a reference to a shared mutable default."""
    if isinstance(default, dict):
        return dict(default)
    if isinstance(default, list):
        return list(default)
    return default
