"""Session-local execution facts, retained for five actual model turns."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from engine.hands import plainly


@dataclass
class ActionHistory:
    """Repeated polling cannot renew a fact; only a new revision can."""

    turn: int = 0
    stream: str | None = None
    seen: dict[str, int] = field(default_factory=dict)
    cells: dict[str, tuple[dict[str, Any], int]] = field(default_factory=dict)

    def begin_turn(self) -> None:
        """Advance once per response, not once per lookup or state request."""
        self.turn += 1
        self.cells = {key: cell for key, cell in self.cells.items() if self.turn - cell[1] < 5}

    def observe(self, feed: dict[str, Any]) -> None:
        """Keep each wire revision once and clear facts on a new router stream."""
        stream = feed.get("stream")
        if stream != self.stream:
            self.stream = stream
            self.seen.clear()
            self.cells.clear()
        present = {str(row["id"]) for row in feed.get("records") or []}
        self.seen = {key: revision for key, revision in self.seen.items() if key in present}
        for row in feed.get("records") or []:
            key = str(row["id"])
            revision = int(row.get("revision", 0))
            if revision <= self.seen.get(key, -1):
                continue
            self.seen[key] = revision
            self.cells[key] = (row, self.turn)

    def render(
        self,
        ammunition: list[dict[str, Any]] | None = None,
        effects: list[dict[str, Any]] | None = None,
        equipment: str | None = None,
    ) -> str:
        """Render measured changes and outcomes, preserving distinct retries.

        With the router's ``equipment`` block, it comes first: each slot, what is in it and
        what she carries that fits, ammunition stock included. Only the ammunition changes
        stay here then, because the stock is already in that block.
        """
        watched = {str(item["item"]).removeprefix("minecraft:"): item for item in ammunition or []}

        def owner(item):
            item = str(item).removeprefix("minecraft:")
            if item in watched:
                return item
            base = item.split("[")[0]
            return base if base in watched else None

        lines = []
        ordered = sorted(self.cells.values(), key=lambda cell: cell[0].get("sequence", 0))
        if equipment:
            lines.append("Equipment (what is on you, and what you carry that fits each slot):")
            lines.append(equipment)
            lines.append("")
        def changes(item):
            return [
                f"  {delta['change']:+g}, "
                f"reason: {delta.get('reason') or 'unknown'}; "
                f"actor: {row.get('actor') or 'unknown'}; action: #{row['id']}; "
                f"observed {self.turn - observed} turns ago"
                + (f"; routine: {row['routine']}" if row.get("routine") else "")
                for row, observed in ordered
                for delta in row.get("changes") or []
                if owner(delta["item"]) == item
            ]

        if watched and equipment:
            moved = {item: changes(item) for item in watched}
            moved = {item: rows for item, rows in moved.items() if rows}
            if moved:
                lines.append("Ammunition changes (last five turns):")
                for item, rows in moved.items():
                    lines += [f"{item}:", *rows]
                lines.append("")
        elif watched:
            lines.append("Ammunition / consumables (current stock; changes last five turns):")
            for item, stock in watched.items():
                lines.append(
                    f"{item}: remaining {stock['remaining']}"
                    + ("; LOCKED — explicit unlock required" if stock.get("locked") else "")
                    + (
                        f"; locked units {stock['locked_remaining']}"
                        if stock.get("locked_remaining") and not stock.get("locked")
                        else ""
                    )
                )
                lines += changes(item)
            lines.append("")
        if effects is not None:
            lines.append("Under effects right now:")
            if not effects:
                lines.append("none")
            for effect in effects:
                duration = (
                    "infinite"
                    if effect.get("infinite")
                    else f"~{effect['seconds_left_estimate']}s"
                    if "seconds_left_estimate" in effect
                    else "duration unknown"
                )
                lines.append(
                    f"{effect.get('name') or 'unknown'}: level {effect.get('level', '?')}; "
                    + duration
                )
            lines.append("")
        if not ordered:
            return "\n".join(lines + ["Recent actions: none observed in the last five turns."])
        lines.append("Recent actions (oldest first; each observation lasts five turns):")
        for row, observed in ordered:
            goal = row.get("goal") or {}
            title = str(goal.get("verb") or "action")
            if goal.get("object") is not None:
                title += " " + plainly(goal["object"])
            outcome = row.get("outcome") or "in progress/unconfirmed"
            if row.get("already"):
                outcome = "already true — nothing done"
            lines.append(
                f"#{row['id']} {title} — {outcome}; "
                f"actor: {row.get('actor') or 'unknown'}; "
                f"observed {self.turn - observed} turns ago"
            )
            confirmation = row.get("confirmation") or {}
            if confirmation:
                lines.append(
                    "completion_basis: " + str(confirmation.get("completion_basis") or "none yet")
                )
                stages = confirmation.get("stages") or []
                for stage in stages:
                    lines.append(str(stage.get("kind")) + ": " + plainly(stage.get("detail") or {}))
                if not any(stage.get("kind") == "effect_confirmed" for stage in stages):
                    lines.append(
                        "effect: unconfirmed; a sent packet or server reply "
                        "does not prove the game effect"
                    )
            if row.get("parent"):
                lines.append(f"parent: {row['parent']}")
            for delta in row.get("changes") or []:
                if owner(delta["item"]) is not None:
                    continue
                reason = delta.get("reason") or "unknown"
                lines.append(f"{delta['change']:+g} {delta['item']}, reason: {reason}")
            if row.get("world"):
                lines.append("world: " + plainly(row["world"]))
            if row.get("why"):
                lines.append("refusal: " + plainly(row["why"]))
            if row.get("summary"):
                lines.append("result: " + str(row["summary"]))
        return "\n".join(lines)
