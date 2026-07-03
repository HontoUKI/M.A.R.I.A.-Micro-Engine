"""Vector store contracts, exercised with hand-written embeddings.

No embedding model is invoked — vectors are passed in directly so the store's
storage and cosine math are tested deterministically.
"""
from __future__ import annotations

import json

import pytest

from engine.memory import MemoryHit, VectorStore


def _store(tmp_path, **kwargs) -> VectorStore:
    return VectorStore(str(tmp_path / "mem"), **kwargs)


# ---------------------------------------------------------------- add / count


def test_add_persists_entry_and_increments_count(tmp_path):
    store = _store(tmp_path)
    assert store.count() == 0
    row = store.add("hello there", [1.0, 0.0, 0.0])
    assert store.count() == 1
    assert row["text"] == "hello there"
    assert row["id"] == "vec_000000"


def test_add_rejects_empty_or_non_1d_vector(tmp_path):
    store = _store(tmp_path)
    with pytest.raises(ValueError):
        store.add("x", [])
    with pytest.raises(ValueError):
        store.add("x", [[1.0, 2.0]])  # type: ignore[list-item]


def test_store_survives_across_instances(tmp_path):
    _store(tmp_path).add("persisted", [0.0, 1.0, 0.0])
    # A fresh instance over the same dir sees the data.
    reopened = _store(tmp_path)
    assert reopened.count() == 1


# ---------------------------------------------------------------- search


def test_search_returns_nearest_by_cosine(tmp_path):
    store = _store(tmp_path)
    store.add("east", [1.0, 0.0, 0.0])
    store.add("north", [0.0, 1.0, 0.0])
    store.add("up", [0.0, 0.0, 1.0])

    hits = store.search([0.9, 0.1, 0.0], top_k=1)
    assert len(hits) == 1
    assert hits[0].text == "east"
    assert isinstance(hits[0], MemoryHit)


def test_search_orders_by_descending_similarity(tmp_path):
    store = _store(tmp_path)
    store.add("close", [1.0, 0.1, 0.0])
    store.add("far", [0.0, 0.0, 1.0])
    hits = store.search([1.0, 0.0, 0.0], top_k=2)
    assert [h.text for h in hits] == ["close", "far"]
    assert hits[0].score >= hits[1].score


def test_search_respects_top_k(tmp_path):
    store = _store(tmp_path)
    for i in range(5):
        store.add(f"e{i}", [float(i), 1.0, 0.0])
    assert len(store.search([1.0, 1.0, 0.0], top_k=2)) == 2


def test_search_threshold_filters_low_similarity(tmp_path):
    store = _store(tmp_path)
    store.add("aligned", [1.0, 0.0, 0.0])
    store.add("orthogonal", [0.0, 1.0, 0.0])
    hits = store.search([1.0, 0.0, 0.0], top_k=5, threshold=0.5)
    assert [h.text for h in hits] == ["aligned"]


def test_search_empty_store_returns_empty(tmp_path):
    assert _store(tmp_path).search([1.0, 0.0]) == []


def test_search_dimension_mismatch_returns_empty(tmp_path):
    store = _store(tmp_path)
    store.add("three-dim", [1.0, 0.0, 0.0])
    assert store.search([1.0, 0.0]) == []


# ---------------------------------------------------------------- cap


def test_max_entries_drops_oldest(tmp_path):
    store = _store(tmp_path, max_entries=2)
    store.add("first", [1.0, 0.0, 0.0])
    store.add("second", [0.0, 1.0, 0.0])
    store.add("third", [0.0, 0.0, 1.0])
    assert store.count() == 2
    texts = {h.text for h in store.search([1.0, 1.0, 1.0], top_k=5)}
    assert texts == {"second", "third"}


def test_max_entries_must_be_positive(tmp_path):
    with pytest.raises(ValueError):
        _store(tmp_path, max_entries=0)


# ---------------------------------------------------------------- layout / reset


def test_entries_file_never_stores_raw_vector(tmp_path):
    store = _store(tmp_path)
    store.add("snippet", [1.0, 2.0, 3.0])
    with open(str(tmp_path / "mem" / "entries.jsonl"), encoding="utf-8") as fh:
        row = json.loads(fh.readline())
    assert "text" in row
    assert "embedding" not in row
    assert "vector" not in row


def test_reset_clears_store(tmp_path):
    store = _store(tmp_path)
    store.add("gone", [1.0, 0.0])
    store.reset()
    assert store.count() == 0
    assert store.search([1.0, 0.0]) == []


def test_dimension_change_resets_store(tmp_path):
    store = _store(tmp_path)
    store.add("old-dim", [1.0, 0.0, 0.0])
    store.add("new-dim", [1.0, 0.0])  # different dim → store resets to this
    assert store.count() == 1
    hits = store.search([1.0, 0.0])
    assert [h.text for h in hits] == ["new-dim"]
