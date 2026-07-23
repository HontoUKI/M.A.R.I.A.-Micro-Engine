"""Relationship matrix: directed, asymmetric per-pair feelings."""
from __future__ import annotations

import pytest

from engine.pack.models import DeltaVector
from engine.scene.matrix import RelationshipMatrix
from engine.scene.models import USER_ID, ScenePack


def _delta(aff=0.0, tru=0.0, bond=0.0) -> DeltaVector:
    return DeltaVector(affection=aff, trust=tru, bond=bond)


def test_edges_cover_actor_to_every_other_participant():
    m = RelationshipMatrix(["megumin", "kaguya"])
    edges = set(m.edges())
    assert ("megumin", "kaguya") in edges
    assert ("kaguya", "megumin") in edges
    assert ("megumin", USER_ID) in edges
    assert ("kaguya", USER_ID) in edges


def test_no_user_sourced_edges():
    m = RelationshipMatrix(["megumin", "kaguya"])
    assert not any(src == USER_ID for src, _ in m.edges())


def test_no_self_edges():
    m = RelationshipMatrix(["megumin", "kaguya"])
    assert not any(src == tgt for src, tgt in m.edges())


def test_apply_moves_only_the_named_edge_asymmetric():
    m = RelationshipMatrix(["megumin", "kaguya"])
    m.apply("megumin", "kaguya", _delta(aff=10, tru=6))
    # Megumin's feeling toward Kaguya moved...
    assert m.feeling("megumin", "kaguya").affection == 10
    # ...but Kaguya's toward Megumin did not. That is the whole point.
    assert m.feeling("kaguya", "megumin").affection == 0


def test_seeds_open_a_relationship_mid_story():
    m = RelationshipMatrix(
        ["megumin", "kaguya"],
        seeds={("megumin", "kaguya"): (28.0, 18.0, 4.0)},
    )
    feel = m.feeling("megumin", "kaguya")
    assert (feel.affection, feel.trust, feel.bond) == (28, 18, 4)
    # The reverse edge is untouched by a one-directional seed.
    assert m.feeling("kaguya", "megumin").affection == 0


def test_apply_clamps_to_axis_bounds():
    m = RelationshipMatrix(["a", "b"], axis_max=50)
    m.apply("a", "b", _delta(aff=999))
    assert m.feeling("a", "b").affection == 50
    m.apply("a", "b", _delta(aff=-999))
    assert m.feeling("a", "b").affection == 0


def test_unknown_edge_raises_helpful_error():
    m = RelationshipMatrix(["megumin", "kaguya"])
    with pytest.raises(KeyError, match="no edge"):
        m.apply(USER_ID, "megumin", _delta(aff=5))  # user is never a source
    with pytest.raises(KeyError):
        m.feeling("megumin", "ghost")


def _scene(**over) -> ScenePack:
    data = {
        "spec_version": 1,
        "meta": {
            "name": "s", "display_name": "S", "version": "0.1.0",
            "license": "x", "author": "y",
        },
        "cast": ["megumin", "kaguya"],
        "relationships": [
            {"from": "megumin", "to": "kaguya", "affection": 28, "trust": 18, "bond": 4},
            {"from": "kaguya", "to": "user", "trust": 10},
        ],
    }
    data.update(over)
    return ScenePack.model_validate(data)


def test_from_scene_applies_seeds_and_covers_cast():
    m = RelationshipMatrix.from_scene(_scene())
    assert m.feeling("megumin", "kaguya").affection == 28
    assert m.feeling("kaguya", USER_ID).trust == 10
    # Unseeded edges start at zero.
    assert m.feeling("kaguya", "megumin").affection == 0


def test_from_scene_ignores_user_sourced_seed():
    scene = _scene(relationships=[{"from": "user", "to": "megumin", "affection": 40}])
    m = RelationshipMatrix.from_scene(scene)
    # No user-sourced edge exists to carry that seed.
    assert not any(src == USER_ID for src, _ in m.edges())


def test_to_dict_snapshots_every_edge():
    m = RelationshipMatrix(["megumin", "kaguya"])
    snap = m.to_dict()
    assert "megumin->kaguya" in snap
    assert set(snap["megumin->kaguya"]) == {"affection", "trust", "bond"}


def test_persisted_values_restore_current_standing():
    m = RelationshipMatrix(
        ["megumin", "kaguya"],
        values={("megumin", "kaguya"): {"affection": 42, "trust": 30, "bond": 7}},
    )
    assert m.feeling("megumin", "kaguya").affection == 42


def test_reset_source_wipes_only_that_actors_outgoing_edges():
    m = RelationshipMatrix(
        ["daniel", "aria"],
        seeds={("daniel", "aria"): (20.0, 15.0, 4.0), ("aria", "daniel"): (8.0, 12.0, 0.0)},
    )
    # Grow both directions.
    m.apply("daniel", "aria", _delta(aff=10, tru=5))
    m.apply("aria", "daniel", _delta(aff=20, tru=10, bond=2))
    # Aria's update wipes only HER feelings, back to her seed baseline.
    m.reset_source("aria")
    aria = m.feeling("aria", "daniel")
    assert (aria.affection, aria.trust, aria.bond) == (8, 12, 0)  # back to seed
    # Daniel still remembers everything he felt — untouched.
    dan = m.feeling("daniel", "aria")
    assert dan.affection == 30 and dan.trust == 20
