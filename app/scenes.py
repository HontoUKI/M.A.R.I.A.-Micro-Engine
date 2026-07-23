"""Server-side scene state: a live SceneRuntime per (session, scene), persisted.

Like `SessionStore` for one-on-one chats, but for a whole scene — the
relationship *matrix* and the shared transcript are the durable state, saved to
`.local/scenes/<session>__<scene>/` and reloaded on the next run so a play
continues across restarts.
"""
from __future__ import annotations

import json
import os

from app.sessions import _safe
from engine.io.json_store import (
    ensure_parent_dir,
    load_json,
    save_json_atomic,
    save_text_atomic,
)
from engine.llm import OllamaClient
from engine.pack.models import CharacterPack
from engine.scene.matrix import RelationshipMatrix
from engine.scene.models import ScenePack
from engine.scene.runtime import SceneLine, SceneRuntime
from engine.state import DEFAULT_AXIS_MAX

_DEFAULT_ROOT = ".local/scenes"


class SceneStore:
    """(session_key, scene_name) → SceneRuntime, cached in memory and on disk."""

    def __init__(
        self,
        llm: OllamaClient,
        *,
        axis_max: float = DEFAULT_AXIS_MAX,
        root: str = _DEFAULT_ROOT,
    ) -> None:
        self._llm = llm
        self._axis_max = axis_max
        self._root = root
        self._runtimes: dict[tuple[str, str], SceneRuntime] = {}

    def _dir(self, session_key: str, scene: ScenePack) -> str:
        return os.path.join(self._root, f"{_safe(session_key)}__{scene.meta.name}")

    def runtime_for(
        self, session_key: str, scene: ScenePack, packs: dict[str, CharacterPack]
    ) -> SceneRuntime:
        """Return the live runtime, restoring persisted matrix + transcript."""
        key = (session_key, scene.meta.name)
        runtime = self._runtimes.get(key)
        if runtime is None:
            directory = self._dir(session_key, scene)
            matrix = self._load_matrix(directory, scene)
            transcript = self._load_transcript(directory)
            backdrop = self._load_text(os.path.join(directory, "backdrop.txt"))
            runtime = SceneRuntime(
                scene, packs, self._llm,
                matrix=matrix, axis_max=self._axis_max, transcript=transcript,
                backdrop=backdrop,
            )
            self._runtimes[key] = runtime
        return runtime

    def save(self, session_key: str, scene: ScenePack, runtime: SceneRuntime) -> None:
        directory = self._dir(session_key, scene)
        save_json_atomic(os.path.join(directory, "matrix.json"), runtime.matrix.to_dict())
        path = os.path.join(directory, "transcript.jsonl")
        ensure_parent_dir(path)
        save_text_atomic(
            path,
            "".join(
                json.dumps({"speaker": ln.speaker, "content": ln.content}, ensure_ascii=False)
                + "\n"
                for ln in runtime.transcript
            ),
        )
        if runtime.backdrop:
            save_text_atomic(os.path.join(directory, "backdrop.txt"), runtime.backdrop)

    def transcript(self, session_key: str, scene: ScenePack) -> list[dict]:
        directory = self._dir(session_key, scene)
        return [{"speaker": ln.speaker, "content": ln.content}
                for ln in self._load_transcript(directory)]

    def matrix(self, session_key: str, scene: ScenePack) -> dict[str, dict[str, float]]:
        directory = self._dir(session_key, scene)
        stored = load_json(os.path.join(directory, "matrix.json"), None)
        if isinstance(stored, dict):
            return stored
        # Not started yet: return the scene's seeded starting matrix.
        return RelationshipMatrix.from_scene(scene, axis_max=self._axis_max).to_dict()

    def backdrop(self, session_key: str, scene: ScenePack) -> str:
        return self._load_text(os.path.join(self._dir(session_key, scene), "backdrop.txt"))

    def reset(self, session_key: str, scene: ScenePack) -> None:
        """Forget the scene — drop the cached runtime and its persisted files."""
        self._runtimes.pop((session_key, scene.meta.name), None)
        directory = self._dir(session_key, scene)
        for name in ("matrix.json", "transcript.jsonl", "backdrop.txt"):
            try:
                os.remove(os.path.join(directory, name))
            except OSError:
                pass

    # --------------------------------------------------------------- disk

    def _load_text(self, path: str) -> str:
        if not os.path.isfile(path):
            return ""
        with open(path, encoding="utf-8") as fh:
            return fh.read()

    def _load_matrix(self, directory: str, scene: ScenePack) -> RelationshipMatrix | None:
        stored = load_json(os.path.join(directory, "matrix.json"), None)
        if not isinstance(stored, dict):
            return None
        values = {
            (src, tgt): v
            for key, v in stored.items()
            if isinstance(v, dict) and "->" in key
            for src, tgt in [key.split("->", 1)]
        }
        return RelationshipMatrix.from_scene(scene, axis_max=self._axis_max, values=values)

    def _load_transcript(self, directory: str) -> list[SceneLine]:
        path = os.path.join(directory, "transcript.jsonl")
        if not os.path.isfile(path):
            return []
        lines: list[SceneLine] = []
        with open(path, encoding="utf-8") as fh:
            for raw in fh:
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    entry = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                if isinstance(entry, dict) and "speaker" in entry and "content" in entry:
                    lines.append(SceneLine(entry["speaker"], entry["content"]))
        return lines
