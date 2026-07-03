"""Two-segment prompt assembly.

The engine's edge over a naive "re-inject a system prompt every turn" loop is
disciplined use of the context window. A turn's prompt is built in two
segments:

1. A **stable prefix** — the character pack's identity skeleton plus its
   pinned invariant rules. It is emitted once as the leading system message
   and never changes across a session, so the LLM backend can reuse its KV
   cache for it every turn.
2. A **dynamic tail** — the mood implied by the current state axes, the
   steering block selected for this turn, and any recalled memory. The tail
   rides *with* the user message and is never written back into dialogue
   history, so steering never accumulates or pollutes the window over time.

Between the two sit the prior dialogue turns (append-only, also cache-warm).

`PromptManager.build_messages` returns an OpenAI-style message list ready for
`OllamaClient.chat`. A hard token ceiling bounds the result: the identity,
the invariants, the current-turn steering and the actual user message are
load-bearing and always kept; recalled memory and then the oldest dialogue
turns are dropped first when the budget is tight.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field


@dataclass(frozen=True)
class DialogueTurn:
    """One prior message in the running conversation."""

    role: str
    content: str

    def __post_init__(self) -> None:
        if self.role not in ("user", "assistant"):
            raise ValueError(f"DialogueTurn.role must be 'user' or 'assistant', got {self.role!r}")


@dataclass(frozen=True)
class PromptInputs:
    """Everything a single turn's prompt is assembled from.

    All character-specific text arrives here as plain strings produced by the
    pack loader (Phase 2) — this module stays character-neutral and never
    reads a pack directly.

    Fields:
        identity:        stable pack identity skeleton (pinned prefix).
        invariants:      pinned rule block for the prefix (may be empty).
        state_summary:   mood/disposition implied by the current axes.
        steering_block:  block selected for this turn's moment tag/state.
        memory_recall:   retrieved memory snippets (disposable under budget).
        dialogue_window: prior turns, oldest first.
        user_message:    the new user input driving this turn.
    """

    identity: str
    user_message: str
    invariants: str = ""
    state_summary: str = ""
    steering_block: str = ""
    memory_recall: str = ""
    dialogue_window: tuple[DialogueTurn, ...] = ()


def _estimate_tokens(text: str) -> int:
    """Cheap, deterministic token estimate (~4 chars per token).

    A rough heuristic on purpose: the engine must not depend on a live
    tokenizer, and the ceiling only needs to be stable and monotonic, not
    exact. Callers can inject their own estimator.
    """
    return (len(text) + 3) // 4


@dataclass
class PromptManager:
    """Assembles the two-segment prompt under a hard token ceiling.

    Args:
        max_tokens:    hard ceiling for the assembled prompt.
        estimate_tokens: token-count estimator; injectable for tests.
        section_label: whether to label tail sections. Labels help weaker
                       models tell steering from user text; disable for
                       terse packs.
    """

    max_tokens: int = 2048
    estimate_tokens: Callable[[str], int] = field(default=_estimate_tokens)
    section_label: bool = True

    def build_messages(self, inputs: PromptInputs) -> list[dict[str, str]]:
        """Build the OpenAI-style message list for one turn."""
        system = self._build_prefix(inputs)
        system_cost = self.estimate_tokens(system)

        # The tail (steering + state + user message) is load-bearing and
        # always kept whole; measure it without recalled memory first.
        core_tail = self._build_tail(inputs, include_memory=False)
        core_tail_cost = self.estimate_tokens(core_tail)

        fixed_cost = system_cost + core_tail_cost
        remaining = self.max_tokens - fixed_cost

        # Recalled memory is the first thing to sacrifice when space is tight.
        include_memory = bool(inputs.memory_recall) and remaining >= self.estimate_tokens(
            inputs.memory_recall
        )
        if include_memory:
            remaining -= self.estimate_tokens(inputs.memory_recall)

        window = self._fit_window(inputs.dialogue_window, remaining)
        tail = self._build_tail(inputs, include_memory=include_memory)

        messages: list[dict[str, str]] = [{"role": "system", "content": system}]
        messages.extend({"role": t.role, "content": t.content} for t in window)
        messages.append({"role": "user", "content": tail})
        return messages

    # ------------------------------------------------------------------ prefix

    def _build_prefix(self, inputs: PromptInputs) -> str:
        parts = [inputs.identity.strip()]
        if inputs.invariants.strip():
            parts.append(inputs.invariants.strip())
        return "\n\n".join(p for p in parts if p)

    # -------------------------------------------------------------------- tail

    def _build_tail(self, inputs: PromptInputs, *, include_memory: bool) -> str:
        sections: list[tuple[str, str]] = []
        if inputs.state_summary.strip():
            sections.append(("State", inputs.state_summary.strip()))
        if inputs.steering_block.strip():
            sections.append(("Guidance", inputs.steering_block.strip()))
        if include_memory and inputs.memory_recall.strip():
            sections.append(("Recalled", inputs.memory_recall.strip()))
        sections.append(("Message", inputs.user_message.strip()))

        if not self.section_label:
            return "\n\n".join(body for _, body in sections)
        return "\n\n".join(f"[{label}]\n{body}" for label, body in sections)

    # ------------------------------------------------------------------ window

    def _fit_window(
        self, window: tuple[DialogueTurn, ...], budget: int
    ) -> tuple[DialogueTurn, ...]:
        """Keep the newest turns that fit; drop oldest first.

        Returns turns in chronological order. A negative budget keeps none.
        """
        if budget <= 0:
            return ()
        kept: list[DialogueTurn] = []
        used = 0
        for turn in reversed(window):
            cost = self.estimate_tokens(turn.content)
            if used + cost > budget:
                break
            kept.append(turn)
            used += cost
        kept.reverse()
        return tuple(kept)
