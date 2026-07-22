"""ScenePack error hierarchy — mirrors the character-pack errors so the API
layer can tell a version mismatch from a malicious scene from a broken one."""
from __future__ import annotations


class SceneError(Exception):
    """Base class for all ScenePack failures."""


class SceneNotFoundError(SceneError):
    """The scene directory or its `scene.yaml` does not exist."""


class SceneVersionError(SceneError):
    """The scene's `spec_version` is not supported by this engine."""


class SceneValidationError(SceneError):
    """The scene parsed but violates the schema or cross-reference rules."""


class SceneSecurityError(SceneError):
    """The scene tripped a hard safety limit (size, injection)."""
