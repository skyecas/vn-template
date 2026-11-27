"""Build-time expansion: {{includes}}/{{macros}} and // comments (design 1.8)."""

from __future__ import annotations

import re
import shlex
from pathlib import Path

from .frontmatter import parse_markdown

# ---------------------------------------------------------------------------
# includes and macros (design 1.8): {{path}} splices at build, // strips
# ---------------------------------------------------------------------------

INCLUDE_PATTERN = re.compile(r"^\{\{\s*([^\s}]+)(.*?)\}\}$")
MACRO_DEPTH_LIMIT = 16


def expand_body(
    body_lines: list[tuple[int, str]],
    filepath: Path,
    stack: tuple[Path, ...] = (),
    depth: int = 0,
) -> tuple[list[tuple[int, str]], list[Path], list[tuple[str, str]]]:
    """splice {{include/macro}} lines and drop // comments (design 1.6, 1.8)

    Returns (origin lines, one origin file per line, expansion errors as
    (kind, message) pairs). A failed line stays literal so later checks still
    see text to report on; the error itself fails the build.
    """
    out_lines: list[tuple[int, str]] = []
    out_origins: list[Path] = []
    errors: list[tuple[str, str]] = []

    for line_no, raw in body_lines:
        if raw.strip().startswith("//"):
            continue  # comments never reach story.json (design 1.6)
        match = INCLUDE_PATTERN.match(raw.strip())
        if not match:
            out_lines.append((line_no, raw))
            out_origins.append(filepath)
            continue

        ref, args_text = match.group(1), match.group(2).strip()
        where = f"{filepath}:{line_no}"
        shown = raw.strip()
        target = Path("story") / (ref if ref.endswith(".md") else f"{ref}.md")
        if not ref.startswith("_") or not target.is_file():
            errors.append(
                (
                    "include_missing",
                    f"{where}: {shown} is not an existing '_' file under story/",
                )
            )
            out_lines.append((line_no, raw))
            out_origins.append(filepath)
            continue
        if target in stack:
            errors.append(("macro_recursion", f"{where}: {shown} expands in a cycle"))
            out_lines.append((line_no, raw))
            out_origins.append(filepath)
            continue
        if depth >= MACRO_DEPTH_LIMIT:
            errors.append(
                (
                    "macro_recursion",
                    f"{where}: {shown} nests past depth {MACRO_DEPTH_LIMIT}",
                )
            )
            out_lines.append((line_no, raw))
            out_origins.append(filepath)
            continue

        try:
            metadata, inc_body = parse_markdown(target.read_text("utf-8"))
        except (ValueError, OSError) as e:
            errors.append(("include_missing", f"{where}: {target}: {e}"))
            out_lines.append((line_no, raw))
            out_origins.append(filepath)
            continue

        params = metadata.get("params") or []
        if not isinstance(params, list):
            params = [params]
        params = [str(param) for param in params]
        try:
            args = shlex.split(args_text) if args_text else []
        except ValueError as e:
            errors.append(("macro_params", f"{where}: {shown}: {e}"))
            args = []
        if len(args) != len(params):
            errors.append(
                (
                    "macro_params",
                    f"{where}: {shown} takes {len(params)} argument(s), got {len(args)}",
                )
            )

        # bind declared params, then expand whatever the body still points at
        text = inc_body
        for name, value in zip(params, args, strict=False):
            text = text.replace("{" + name + "}", value)
        inner, inner_origins, inner_errors = expand_body(
            list(enumerate(text.splitlines(), 1)),
            target,
            stack + (target,),
            depth + 1,
        )
        out_lines += inner
        out_origins += inner_origins
        errors += inner_errors

    return out_lines, out_origins, errors
