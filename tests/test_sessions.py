"""Session persistence: relationship state and transcripts survive restarts."""
from __future__ import annotations

import json
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
