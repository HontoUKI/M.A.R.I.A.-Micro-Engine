"""Vector memory storage — a narrow, per-character semantic store.

Ported and trimmed from the public M.A.R.I.A. Core snapshot's v2 store. The
Micro-Engine keeps only the retrieval minimum: append an embedded snippet,
cosine-search the k nearest. Maria-specific machinery (worthiness scoring,
v1 migration, legacy aliases) is intentionally left out.

Each character pack owns its own store directory, laid out as three files:

- ``entries.jsonl``  — one metadata row per memory; never holds the raw
                       vector (those live in the npy matrix).
- ``embeddings.npy`` — float32 matrix of shape ``(N, dim)``, row-aligned
                       one-to-one with ``entries.jsonl``.
- ``index.json``     — small manifest (version, embedding model, count, dim).

The embeddings matrix is rewritten in full on every append. That is fine at
community scale (the store is capped) and keeps the format trivially portable
to a memory-mapped or FAISS backend later.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import numpy as np

_ENTRIES_FILE = "entries.jsonl"
_EMBEDDINGS_FILE = "embeddings.npy"
_INDEX_FILE = "index.json"

DEFAULT_MAX_ENTRIES = 512


@dataclass(frozen=True)
class MemoryHit:
    """One search result: a stored snippet and its similarity to the query."""

    text: str
    score: float
    id: str
    source: str
    created_at: str
    metadata: dict[str, Any] = field(default_factory=dict)


class VectorStore:
    """Append-and-search vector memory rooted at one directory.

    Args:
        base_dir:    directory holding the three store files.
        max_entries: hard cap on stored rows; the oldest are dropped on
                     append once the cap is exceeded. Keeps a long-running
                     character's memory bounded.
    """

    def __init__(self, base_dir: str, *, max_entries: int = DEFAULT_MAX_ENTRIES) -> None:
        if max_entries <= 0:
            raise ValueError("max_entries must be positive")
        self._dir = base_dir
        self._max_entries = max_entries

    # ---------------------------------------------------------------- paths

    @property
    def _entries_path(self) -> str:
        return os.path.join(self._dir, _ENTRIES_FILE)

    @property
    def _embeddings_path(self) -> str:
        return os.path.join(self._dir, _EMBEDDINGS_FILE)

    @property
    def _index_path(self) -> str:
        return os.path.join(self._dir, _INDEX_FILE)

    # ---------------------------------------------------------------- read

    def count(self) -> int:
        return len(self._load_entries())

    def _load_entries(self) -> list[dict[str, Any]]:
        """Stream-load entries.jsonl; skip corrupt lines rather than crash."""
        if not os.path.isfile(self._entries_path):
            return []
        out: list[dict[str, Any]] = []
        with open(self._entries_path, encoding="utf-8") as fh:
            for raw in fh:
                line = raw.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(row, dict):
                    out.append(row)
        return out

    def _load_embeddings(self) -> np.ndarray:
        if not os.path.isfile(self._embeddings_path):
            return np.zeros((0, 0), dtype=np.float32)
        try:
            arr = np.load(self._embeddings_path, allow_pickle=False)
        except (OSError, ValueError):
            return np.zeros((0, 0), dtype=np.float32)
        if arr.dtype != np.float32:
            arr = arr.astype(np.float32, copy=False)
        return arr

    # ---------------------------------------------------------------- write

    def add(
        self,
        text: str,
        embedding: list[float],
        *,
        source: str = "user",
        metadata: dict[str, Any] | None = None,
        embedding_model: str = "",
    ) -> dict[str, Any]:
        """Append one embedded snippet; returns the row written.

        Enforces `max_entries` by dropping the oldest rows so the newest
        snippet always lands. A dimension mismatch with the existing matrix
        resets the store to just this entry (defensive: only happens if the
        embedding model changed under a live store).
        """
        vector = np.asarray(embedding, dtype=np.float32)
        if vector.ndim != 1 or vector.size == 0:
            raise ValueError("embedding must be a non-empty 1-D vector")

        entries = self._load_entries()
        embeddings = self._load_embeddings()
        dim = int(vector.shape[0])

        row = {
            "id": f"vec_{len(entries):06d}",
            "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "text": text,
            "source": source,
            "metadata": dict(metadata) if metadata else {},
        }

        reset = embeddings.shape[0] == 0 or embeddings.shape[1] != dim
        if reset:
            entries = [row]
            matrix = vector.reshape(1, dim)
        else:
            entries.append(row)
            matrix = np.vstack([embeddings, vector.reshape(1, dim)])

        # Enforce the cap: keep the newest `max_entries` rows.
        if len(entries) > self._max_entries:
            entries = entries[-self._max_entries :]
            matrix = matrix[-self._max_entries :]

        self._rewrite(entries, matrix, embedding_model=embedding_model)
        return row

    def reset(self) -> None:
        """Remove all store files (test / re-seed helper)."""
        for path in (self._entries_path, self._embeddings_path, self._index_path):
            try:
                os.remove(path)
            except OSError:
                pass

    def _rewrite(
        self,
        entries: list[dict[str, Any]],
        matrix: np.ndarray,
        *,
        embedding_model: str,
    ) -> None:
        """Atomic full rewrite of all three store files."""
        os.makedirs(self._dir, exist_ok=True)

        # Re-key ids to match final row order so ids stay stable references.
        rekeyed = []
        for idx, row in enumerate(entries):
            row = dict(row)
            row["embedding_row"] = idx
            rekeyed.append(row)

        tmp_entries = self._entries_path + ".tmp"
        with open(tmp_entries, "w", encoding="utf-8") as fh:
            for row in rekeyed:
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")
        os.replace(tmp_entries, self._entries_path)

        self._save_npy(matrix)

        dim = int(matrix.shape[1]) if matrix.ndim == 2 and matrix.shape[0] else 0
        index = {
            "version": 1,
            "embedding_model": embedding_model,
            "count": int(matrix.shape[0]),
            "dim": dim,
        }
        tmp_index = self._index_path + ".tmp"
        with open(tmp_index, "w", encoding="utf-8") as fh:
            json.dump(index, fh, ensure_ascii=False, indent=2)
        os.replace(tmp_index, self._index_path)

    def _save_npy(self, matrix: np.ndarray) -> None:
        tmp = self._embeddings_path + ".tmp"
        np.save(tmp, matrix, allow_pickle=False)
        # np.save appends `.npy` when the path lacks it; our tmp does not.
        written = tmp if tmp.endswith(".npy") else tmp + ".npy"
        os.replace(written, self._embeddings_path)

    # ---------------------------------------------------------------- search

    def search(
        self,
        query_embedding: list[float],
        *,
        top_k: int = 3,
        threshold: float = 0.0,
    ) -> list[MemoryHit]:
        """Return up to `top_k` hits with cosine similarity >= threshold."""
        entries = self._load_entries()
        embeddings = self._load_embeddings()
        if embeddings.size == 0 or not entries:
            return []

        q = np.asarray(query_embedding, dtype=np.float32)
        if q.ndim != 1 or q.size == 0 or embeddings.shape[1] != q.shape[0]:
            return []

        eps = 1e-12
        e_norms = np.linalg.norm(embeddings, axis=1) + eps
        q_norm = float(np.linalg.norm(q)) + eps
        sims = (embeddings @ q) / (e_norms * q_norm)

        hits: list[MemoryHit] = []
        for idx, sim in enumerate(sims):
            score = float(sim)
            if score < threshold or idx >= len(entries):
                continue
            row = entries[idx]
            hits.append(
                MemoryHit(
                    text=str(row.get("text", "")),
                    score=score,
                    id=str(row.get("id", "")),
                    source=str(row.get("source", "")),
                    created_at=str(row.get("created_at", "")),
                    metadata=dict(row.get("metadata") or {}),
                )
            )
        hits.sort(key=lambda h: h.score, reverse=True)
        return hits[:top_k]
