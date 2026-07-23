"""Scene backdrop captioning.

Turns an uploaded image into a short text description that is pinned into a
scene as its set — read once, then only the words travel into context (cheap,
consistent, and privacy-preserving: the pixels never reach the character prompt).
Optional and Ollama-only: it needs a multimodal model (e.g. gemma3).
"""
from __future__ import annotations

import base64
import binascii

# Written for a vision model: describe the *place*, not any people, so the cast
# can reference the backdrop without it inventing extra characters.
BACKDROP_PROMPT = (
    "You are describing a location to use as the backdrop of a scene. In 2 to 4 "
    "vivid but concise sentences, describe the setting, atmosphere, lighting and "
    "notable objects in this image. Describe only the place and mood — do NOT "
    "describe or invent any people or characters. Write it as a stage setting the "
    "actors can refer to."
)

MAX_IMAGE_BYTES = 8 * 1024 * 1024


class VisionUnavailableError(Exception):
    """The configured backend cannot caption images (no vision support)."""


class BadImageError(Exception):
    """The supplied image data is not valid base64 or is too large."""


def validate_image_b64(image_b64: str) -> str:
    """Sanity-check base64 image data (valid, within the size cap). Returns the
    cleaned base64 string (any data: URL prefix stripped)."""
    if not isinstance(image_b64, str) or not image_b64.strip():
        raise BadImageError("no image data")
    data = image_b64.strip()
    if data.startswith("data:"):
        # data:image/png;base64,XXXX -> XXXX
        _, _, data = data.partition(",")
    try:
        raw = base64.b64decode(data, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise BadImageError("image is not valid base64") from exc
    if len(raw) > MAX_IMAGE_BYTES:
        raise BadImageError(f"image is {len(raw)} bytes; limit is {MAX_IMAGE_BYTES}")
    return data


def caption_backdrop(llm, image_b64: str, *, model: str | None = None) -> str:
    """Caption an image as a scene backdrop. Raises VisionUnavailableError when
    the backend has no `caption`, BadImageError on bad data."""
    caption = getattr(llm, "caption", None)
    if not callable(caption):
        raise VisionUnavailableError(
            "the configured LLM backend does not support image captioning"
        )
    clean = validate_image_b64(image_b64)
    return caption(clean, BACKDROP_PROMPT, model=model or None)
