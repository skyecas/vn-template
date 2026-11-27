"""Reporting helpers shared by the pipeline and the check runner (design 4.1)."""

from __future__ import annotations

import sys
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from .ir import NodeIR, VariantIR

DEBUG = {"-d", "-debug", "-DEBUG"}.intersection(sys.argv)


def debug(msg: str) -> None:
    if DEBUG:
        print(f" - {msg}")


# ---------------------------------------------------------------------------
# reporting: same output shape as the v1 generator
# ---------------------------------------------------------------------------


def pretty_print_paths(
    value: Any, indent: int = 0, separators: list[str] | None = None, limit: int = 8
):
    """
    Nicely prints VariantIR(s) or nested paths with custom separators per depth.
    """
    if separators is None:
        separators = [", ", "; ", " - "]

    def format_paths(val: Any, depth: int = 0) -> str:
        sep = separators[depth] if depth < len(separators) else separators[-1]

        if isinstance(val, VariantIR):
            return val.filepath.name
        elif isinstance(val, list):
            return sep.join(sorted({format_paths(v, depth + 1) for v in val}))
        else:
            return str(val)

    # a check can return hundreds of hits; printing them all produced a single
    # multi-thousand character line that was impossible to read
    extra = 0
    if isinstance(value, list) and len(value) > limit:
        extra = len(value) - limit
        value = value[:limit]

    formatted = format_paths(value)
    if extra:
        formatted += f", ... and {extra} more"
    print(" " * indent + f" - {formatted}")


def success(text: str) -> None:
    print(f"✅ {text}")


def warning(text: str) -> None:
    print(f"⚠️  {text}")


def failure(text: str) -> None:
    print(f"❌ {text}")


@dataclass
class StoryCheck:
    function: Callable[[dict[str, NodeIR]], list[Any]]
    check_type: str
    required: bool = True
    raise_on_empty: bool = False
