"""Frontmatter split: --- delimited yaml -> (metadata, body) (design 1.2)."""

from __future__ import annotations

from typing import Any

from yaml import YAMLError, safe_load


def parse_markdown(content: str) -> tuple[dict[str, Any], str]:
    content = content.strip()
    if not content.startswith("---"):
        return {}, content
    parts = content.split("---", 2)
    if len(parts) < 3:
        raise ValueError("unterminated frontmatter, missing the closing '---'")
    _, meta, body = parts
    try:
        loaded = safe_load(meta)
    except YAMLError as e:
        # meta keeps the file's line numbering (its first line is the blank
        # after the opening ---), so the mark points at the real line
        mark = getattr(e, "problem_mark", None)
        where = (
            f"line {mark.line + 1}, column {mark.column + 1}"
            if mark
            else "unknown line"
        )
        problem = getattr(e, "problem", None) or str(e)
        raise ValueError(f"frontmatter {where}: {problem}") from e
    return loaded or {}, body.strip().replace("\\", "/")
