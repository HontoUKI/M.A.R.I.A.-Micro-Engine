"""Server-side session state for the OpenAI-compatible surface.

OpenAI's chat contract is stateless — the client resends the conversation each
call — but a character's relationship axes are inherently stateful, and this
engine is built for a *long, continuous* correspondence that stays in
character. So each session's relationship state (and a transcript) is persisted
to disk, keyed by (session, pack name), and reloaded on the next run.

The session key comes from the request's `user` field (OpenAI's own
per-end-user identifier); absent that, all traffic shares a "default" session.
"""
from __future__ import annotations

import json
import os
from datetime import datetime

from engine.io.json_store import ensure_parent_dir, load_json, save_json_atomic
from engine.pack import CharacterPack
from engine.state import DEFAULT_AXIS_MAX, StateKernel

_AXES = ("affection", "trust", "bond")
_DEFAULT_ROOT = ".local/sessions"


def _safe(name: str) -> str:
    """Filesystem-safe token from an arbitrary session key (no traversal)."""
    cleaned = "".join(c if (c.isalnum() or c in "-_") else "_" for c in name)
    return cleaned[:64] or "default"


class SessionStore:
    """(session_key, pack_name) → StateKernel, cached in memory and on disk."""

    def __init__(self, *, axis_max: float = DEFAULT_AXIS_MAX, root: str = _DEFAULT_ROOT) -> None:
        self._axis_max = axis_max
        self._root = root
        self._kernels: dict[tuple[str, str], StateKernel] = {}

    def _dir(self, session_key: str, pack: CharacterPack) -> str:
        return os.path.join(self._root, f"{_safe(session_key)}__{pack.meta.name}")

    def kernel_for(self, session_key: str, pack: CharacterPack) -> StateKernel:
        """Return the session's kernel, restoring persisted axes when present."""
        key = (session_key, pack.meta.name)
        kernel = self._kernels.get(key)
        if kernel is None:
            values = load_json(os.path.join(self._dir(session_key, pack), "state.json"), None)
            if isinstance(values, dict) and all(axis in values for axis in _AXES):
                kernel = StateKernel.restore(pack, values, axis_max=self._axis_max)
            else:
                kernel = StateKernel.from_pack(pack, axis_max=self._axis_max)
            self._kernels[key] = kernel
        return kernel

    def record_turn(
        self,
        session_key: str,
        pack: CharacterPack,
        kernel: StateKernel,
        *,
        user_message: str,
        result,
    ) -> None:
        """Persist the post-turn axes and append the exchange to the transcript."""
        directory = self._dir(session_key, pack)
        save_json_atomic(os.path.join(directory, "state.json"), kernel.to_dict())

        entry = {
            "ts": datetime.now().astimezone().isoformat(timespec="seconds"),
            "user": user_message,
            "reply": result.reply,
            "tag": result.tag,
            "stage": result.stage,
            "axes": result.axes.as_dict(),
        }
        transcript = os.path.join(directory, "transcript.jsonl")
        ensure_parent_dir(transcript)
        with open(transcript, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def __len__(self) -> int:
        return len(self._kernels)
