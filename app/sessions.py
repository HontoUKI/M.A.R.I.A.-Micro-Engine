"""Server-side session state for the OpenAI-compatible surface.

OpenAI's chat contract is stateless — the client resends the conversation
each call — but a character's relationship axes are inherently stateful. The
bridge: the client's message list supplies the dialogue window, while the
engine keeps each character's evolving axes here, keyed by
(session, pack name).

The session key comes from the request's `user` field (OpenAI's own
per-end-user identifier); absent that, all traffic shares a "default"
session. State is in-process for v0.1; durable persistence is future work.
"""
from __future__ import annotations

from engine.pack import CharacterPack
from engine.state import DEFAULT_AXIS_MAX, StateKernel


class SessionStore:
    """In-memory map of (session_key, pack_name) → StateKernel."""

    def __init__(self, *, axis_max: float = DEFAULT_AXIS_MAX) -> None:
        self._axis_max = axis_max
        self._kernels: dict[tuple[str, str], StateKernel] = {}

    def kernel_for(self, session_key: str, pack: CharacterPack) -> StateKernel:
        """Return the session's kernel for this pack, creating it on first use."""
        key = (session_key, pack.meta.name)
        kernel = self._kernels.get(key)
        if kernel is None:
            kernel = StateKernel.from_pack(pack, axis_max=self._axis_max)
            self._kernels[key] = kernel
        return kernel

    def __len__(self) -> int:
        return len(self._kernels)
