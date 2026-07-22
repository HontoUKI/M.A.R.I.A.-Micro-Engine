"""Character packs: the data that turns the generic engine into a character.

See `CHARACTER_PACK_SPEC.md` for the public contract.
"""

from engine.pack.errors import (
    PackError,
    PackNotFoundError,
    PackSecurityError,
    PackValidationError,
    PackVersionError,
)
from engine.pack.loader import SUPPORTED_SPEC_VERSION, load_pack
from engine.pack.models import (
    AxisConfig,
    CharacterPack,
    DeltaVector,
    GatedTag,
    MomentTag,
    PackMeta,
)

__all__ = [
    "SUPPORTED_SPEC_VERSION",
    "AxisConfig",
    "CharacterPack",
    "DeltaVector",
    "GatedTag",
    "MomentTag",
    "PackError",
    "PackMeta",
    "PackNotFoundError",
    "PackSecurityError",
    "PackValidationError",
    "PackVersionError",
    "load_pack",
]
