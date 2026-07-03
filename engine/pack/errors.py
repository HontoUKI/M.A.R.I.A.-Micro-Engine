"""Character pack error hierarchy.

Every failure mode is a distinct, catchable type so the API layer can map
them to the right response (a version mismatch is a different client story
than a malicious pack).
"""
from __future__ import annotations


class PackError(Exception):
    """Base class for all character pack failures."""


class PackNotFoundError(PackError):
    """The pack directory or its `pack.yaml` does not exist."""


class PackVersionError(PackError):
    """The pack's `spec_version` is not supported by this engine."""


class PackValidationError(PackError):
    """The pack parsed but violates the schema or balance rules."""


class PackSecurityError(PackError):
    """The pack tripped a hard safety limit (size, traversal, injection)."""
