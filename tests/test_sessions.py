"""Session persistence: relationship state and transcripts survive restarts."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass

from app.sessions import SessionStore
from engine.state import Axes
from tests._packs import make_pack


@dataclass
class _FakeResult:
    reply: str
    tag: str
    stage: str | None
    axes: Axes


def test_new_session_starts_from_pack_baseline(tmp_path):
    store = SessionStore(root=str(tmp_path / "s"))
    kernel = store.kernel_for("alice", make_pack())
    # make_pack starts at 20 / 10 / 0.
    assert kernel.to_dict() == {"affection": 20.0, "trust": 10.0, "bond": 0.0}


def test_state_persists_and_reloads_across_store_instances(tmp_path):
    root = str(tmp_path / "s")
    pack = make_pack()

    store = SessionStore(root=root)
    kernel = store.kernel_for("alice", pack)
    kernel.to_dict()  # touch
    kernel._values["affection"] = 55.0  # simulate a turn moving the axis
    store.record_turn(
        "alice", pack, kernel,
        user_message="hi",
        result=_FakeResult("hey", "warmth", "reserved", Axes(55.0, 10.0, 0.0)),
    )

    # A brand-new store over the same directory resumes the relationship.
    reopened = SessionStore(root=root)
    assert reopened.kernel_for("alice", pack).to_dict()["affection"] == 55.0


def test_transcript_is_appended(tmp_path):
    root = str(tmp_path / "s")
    pack = make_pack()
    store = SessionStore(root=root)
    kernel = store.kernel_for("bob", pack)
    for msg in ("first", "second"):
        store.record_turn(
            "bob", pack, kernel,
            user_message=msg,
            result=_FakeResult("ok", "neutral", None, Axes(20.0, 10.0, 0.0)),
        )
    path = tmp_path / "s" / "bob__aria" / "transcript.jsonl"
    lines = path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["user"] == "first"


def test_sessions_are_isolated_by_key_and_pack(tmp_path):
    store = SessionStore(root=str(tmp_path / "s"))
    pack = make_pack()
    a = store.kernel_for("alice", pack)
    b = store.kernel_for("bob", pack)
    a._values["affection"] = 99.0
    assert b.to_dict()["affection"] == 20.0


def _write_transcript(store, session, pack, entries):
    directory = store._dir(session, pack)
    os.makedirs(directory, exist_ok=True)
    with open(os.path.join(directory, "transcript.jsonl"), "w", encoding="utf-8") as fh:
        for entry in entries:
            fh.write(json.dumps(entry) + "\n")


def _sample_entries():
    return [
        {"ts": "2026-07-01T10:00:00", "user": "u1", "reply": "r1"},
        {"ts": "2026-07-01T11:00:00", "user": "u2", "reply": "r2"},
        {"ts": "2026-07-02T09:00:00", "user": "u3", "reply": "r3"},
    ]


def test_transcript_days_and_read_by_day(tmp_path):
    store = SessionStore(root=str(tmp_path / "s"))
    pack = make_pack()
    _write_transcript(store, "a", pack, _sample_entries())
    assert store.transcript_days("a", pack) == ["2026-07-01", "2026-07-02"]
    day1 = store.read_transcript("a", pack, "2026-07-01")
    assert [e["user"] for e in day1] == ["u1", "u2"]
    assert len(store.read_transcript("a", pack)) == 3


def test_clear_one_day_leaves_the_rest(tmp_path):
    store = SessionStore(root=str(tmp_path / "s"))
    pack = make_pack()
    _write_transcript(store, "a", pack, _sample_entries())
    assert store.clear_transcript("a", pack, "2026-07-01") == 2
    assert store.transcript_days("a", pack) == ["2026-07-02"]


def test_clear_all_history(tmp_path):
    store = SessionStore(root=str(tmp_path / "s"))
    pack = make_pack()
    _write_transcript(store, "a", pack, _sample_entries())
    assert store.clear_transcript("a", pack) == 3
    assert store.transcript_days("a", pack) == []


def test_reset_state_forgets_the_relationship(tmp_path):
    store = SessionStore(root=str(tmp_path / "s"))
    pack = make_pack()
    kernel = store.kernel_for("a", pack)
    kernel._values["affection"] = 90.0
    store.record_turn(
        "a", pack, kernel,
        user_message="x",
        result=_FakeResult("y", "warmth", "reserved", Axes(90.0, 10.0, 0.0)),
    )
    store.reset_state("a", pack)
    # A fresh lookup starts from the pack baseline again.
    assert store.kernel_for("a", pack).to_dict()["affection"] == 20.0


def test_unsafe_session_key_cannot_escape_the_root(tmp_path):
    root = tmp_path / "s"
    store = SessionStore(root=str(root))
    pack = make_pack()
    kernel = store.kernel_for("../../evil", pack)
    store.record_turn(
        "../../evil", pack, kernel,
        user_message="x",
        result=_FakeResult("y", "neutral", None, Axes(20.0, 10.0, 0.0)),
    )
    # Everything written stays under the root; no traversal outside it.
    written = list(root.rglob("state.json"))
    assert written
    for p in written:
        assert str(root.resolve()) in str(p.resolve())
