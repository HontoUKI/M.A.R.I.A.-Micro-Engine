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

from engine.io.json_store import (
    ensure_parent_dir,
    load_json,
    save_json_atomic,
    save_text_atomic,
)
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

    # ------------------------------------------------------------ history

    def _read_entries(self, directory: str) -> list[dict]:
        path = os.path.join(directory, "transcript.jsonl")
        if not os.path.isfile(path):
            return []
        out: list[dict] = []
        with open(path, encoding="utf-8") as fh:
            for raw in fh:
                line = raw.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(entry, dict):
                    out.append(entry)
        return out

    def transcript_days(self, session_key: str, pack: CharacterPack) -> list[str]:
        """Distinct dates (YYYY-MM-DD) that have transcript entries, oldest first."""
        days = {
            str(e.get("ts", ""))[:10]
            for e in self._read_entries(self._dir(session_key, pack))
        }
        return sorted(d for d in days if d)

    def read_transcript(
        self, session_key: str, pack: CharacterPack, day: str | None = None
    ) -> list[dict]:
        entries = self._read_entries(self._dir(session_key, pack))
        if day:
            entries = [e for e in entries if str(e.get("ts", "")).startswith(day)]
        return entries

    def clear_transcript(
        self, session_key: str, pack: CharacterPack, day: str | None = None
    ) -> int:
        """Delete the whole transcript, or just one day's entries. Returns the
        number of turns removed."""
        directory = self._dir(session_key, pack)
        path = os.path.join(directory, "transcript.jsonl")
        entries = self._read_entries(directory)
        if not entries:
            return 0
        if day is None:
            os.remove(path)
            return len(entries)
        kept = [e for e in entries if not str(e.get("ts", "")).startswith(day)]
        removed = len(entries) - len(kept)
        if not kept:
            os.remove(path)
        elif removed:
            save_text_atomic(
                path, "".join(json.dumps(e, ensure_ascii=False) + "\n" for e in kept)
            )
        return removed

    def reset_state(self, session_key: str, pack: CharacterPack) -> None:
        """Forget the relationship — drop the cached kernel and its state file."""
        self._kernels.pop((session_key, pack.meta.name), None)
        try:
            os.remove(os.path.join(self._dir(session_key, pack), "state.json"))
        except OSError:
            pass

    def __len__(self) -> int:
        return len(self._kernels)
