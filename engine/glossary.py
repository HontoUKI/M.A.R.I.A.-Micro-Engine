"""Session-local reference notes, with a bounded lifetime measured in her turns."""
from __future__ import annotations

import re
from dataclasses import dataclass, field

LOOKUP = re.compile(r"<lookup>\s*([^<]*?)\s*</lookup>", re.IGNORECASE)


@dataclass
class GlossaryNotes:
    """Three cells, each expiring ten turns after its last read."""

    turn: int = 0
    cells: dict[str, tuple[str, str, int]] = field(default_factory=dict)

    def begin_turn(self) -> None:
        self.turn += 1
        self.cells = {k: v for k, v in self.cells.items() if self.turn - v[2] < 10}

    def remember(self, article: dict) -> None:
        """Index is ephemeral; a repeated read refreshes its cell."""
        if article.get("index"):
            return
        name = str(article["name"])
        key = name.casefold()
        if key not in self.cells and len(self.cells) == 3:
            oldest = min(self.cells, key=lambda k: self.cells[k][2])
            del self.cells[oldest]
        self.cells[key] = (name, str(article["text"])[:2000], self.turn)

    def render(self) -> str:
        """Render every live cell and its remaining lifetime."""
        if not self.cells:
            return ""
        lines = ["Your notes from the glossary:"]
        for name, text, read in self.cells.values():
            age = self.turn - read
            lines.append(f"{name} (read {age} turns ago, gone in {10 - age}):\n{text}")
        return "\n".join(lines)
