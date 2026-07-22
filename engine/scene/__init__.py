"""ScenePacks: the "production" layer that casts Character Packs into a scene.

A ScenePack composes several character packs, pins a shared setting, seeds the
relationship matrix and can grant scenario-only tags. See
`docs/DESIGN_v0.2_SCENES.md` for the design and the eventual public contract.
"""

from engine.scene.errors import (
    SceneError,
    SceneNotFoundError,
    SceneSecurityError,
    SceneValidationError,
    SceneVersionError,
)
from engine.scene.loader import SUPPORTED_SPEC_VERSION, load_scene
from engine.scene.models import (
    USER_ID,
    RelationshipSeed,
    ScenarioTag,
    SceneMeta,
    ScenePack,
)

__all__ = [
    "SUPPORTED_SPEC_VERSION",
    "USER_ID",
    "RelationshipSeed",
    "SceneError",
    "SceneMeta",
    "SceneNotFoundError",
    "ScenePack",
    "SceneSecurityError",
    "SceneValidationError",
    "SceneVersionError",
    "ScenarioTag",
    "load_scene",
]
