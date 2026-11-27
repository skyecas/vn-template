"""Typed IR: every node carries (file, line) (design 3.2)."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

# ---------------------------------------------------------------------------
# IR (design 3.2): every IR node carries (file, line)
# ---------------------------------------------------------------------------


@dataclass
class ChoiceIR:
    label: str
    target: str | None
    file: Path
    line: int = 1
    cond: dict | None = None
    effects: list[dict] = field(default_factory=list)
    once: bool = False
    chance: int = 100
    fallback: bool = False
    call: bool = False
    return_: bool = False


@dataclass
class VariantIR:
    """one story file; the unit every check reports on"""

    filepath: Path
    pathname: str
    line: int
    src: list[tuple[int, str]]  # expanded body lines, for the regex-based checks
    lines: list[list[dict]] = field(default_factory=list)  # lexed token lines
    block_error: str | None = None
    choices: list[ChoiceIR] = field(default_factory=list)
    effects: list[dict] = field(default_factory=list)
    unknown_keys: list[str] = field(default_factory=list)
    expand_errors: list[tuple[str, str]] = field(default_factory=list)
    revisit: bool = True
    pace: str | None = None
    colour: str | None = None
    effect: str | None = None
    pov: str | None = None
    messagepov: str | None = None
    messagetitle: str | None = None
    background: str | None = None
    weather: str | None = None
    image: str | None = None
    music: str | None = None

    @property
    def text(self) -> str:
        """the raw body, exactly what the old regex checks walked"""
        return "\n".join(text for _, text in self.src)


@dataclass
class NodeIR:
    id: str
    filepath: Path
    line: int = 1
    variants: list[VariantIR] = field(default_factory=list)
    is_start: bool = False
    is_end: bool = False
    title: str | None = None
    chapter: str | None = None
    next: str | None = None
    next_if: dict | None = None

    @property
    def revisit(self) -> bool:
        return all(variant.revisit for variant in self.variants)


# frontmatter key -> emitted variant attribute (v1 names kept for the renderer)
PRESENTATION_KEYS = {
    "pace": "pace",
    "colour": "colour",
    "effect": "effect",
    "pov": "pov",
    "message-pov": "messagepov",
    "message-title": "messagetitle",
    "background": "background",
    "weather": "weather",
    "image": "image",
    "music": "music",
}


def all_nodes(parts: dict[str, NodeIR]) -> list[VariantIR]:
    nodes = []
    for path in parts.values():
        nodes.extend(path.variants)
    return nodes
