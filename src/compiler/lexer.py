"""Token lexer: body lines -> token lines (design 1.6 / 2.1)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from .conditions import CondError, parse_condition_str
from .effects import EffectError, parse_effect
from .patterns import (
    BACKGROUND_COLOUR_PATTERN,
    BACKGROUND_EFFECTS_PATTERN,
    COLOUR_PATTERN,
    EFFECT_LINE_PREFIXES,
    EFFECT_PATTERN,
    ELSE_PATTERN,
    ENDIF_PATTERN,
    IF_PATTERN,
    MESSAGE_LINE_PATTERN,
    MESSAGE_TITLE_PATTERN,
    MESSAGE_UNSENT_PATTERN,
    PACE_PATTERN,
    PAUSE_PATTERN,
    POV_PATTERN,
    SFX_PATTERN,
    WEATHER_PATTERN,
)

# ---------------------------------------------------------------------------
# token lexer: body lines -> token lines (design 1.6 / 2.1)
# ---------------------------------------------------------------------------


@dataclass
class LexResult:
    lines: list[list[dict]]
    block_error: str | None = None


def _mk(kind: str, value: str) -> dict:
    return {"t": "mk", "k": kind, "v": value}


def _find_spans(
    text: str, pattern: re.Pattern[str], kind: str, group: int | None = None
) -> list[tuple[int, int, dict]]:
    spans = []
    for match in pattern.finditer(text):
        start, end = match.span()
        value = match.group(group) if group is not None else match.group(0).lstrip("/")
        spans.append((start, end, _mk(kind, value)))
    return spans


def lex_content(text: str) -> list[dict]:
    """split a line's text into lit / var / if / alt tokens (design 1.6)"""
    tokens: list[dict] = []
    scan = 0  # where the next construct is looked for
    emitted = 0  # text before this point has been emitted already
    while True:
        open_at = text.find("{", scan)
        if open_at == -1:
            break
        close_at = text.find("}", open_at + 1)
        if close_at == -1:
            break
        inner = text[open_at + 1 : close_at]
        parsed = _lex_brace(inner)
        if parsed is None:
            # not a construct we know: literal brace, keep scanning past it
            # (the text before it is still pending, design 1.6)
            scan = open_at + 1
            continue
        if text[emitted:open_at]:
            tokens.append({"t": "lit", "v": text[emitted:open_at]})
        tokens.append(parsed)
        emitted = scan = close_at + 1
    if text[emitted:]:
        tokens.append({"t": "lit", "v": text[emitted:]})
    return tokens


def _lex_brace(inner: str) -> dict | None:
    """{name} var, {cond: a|b} inline if, {a|b} seq, {&a|b} cycle, {~a|b} shuffle"""
    if not inner:
        return None
    if re.fullmatch(r"\w+", inner):
        return {"t": "var", "name": inner}
    if inner[0] in {"&", "~"}:
        mode = "cycle" if inner[0] == "&" else "shuffle"
        branches = inner[1:].split("|")
        if len(branches) < 2:
            return None
        return {
            "t": "alt",
            "mode": mode,
            "branches": [[lex_content(b)] for b in branches],
        }
    colon = inner.find(":")
    pipe = inner.find("|")
    if colon != -1 and pipe != -1 and colon < pipe:
        # inline if: colon before a pipe (design 1.6)
        head, tail = inner[:colon], inner[colon + 1 :]
        branches = tail.split("|")
        try:
            cond = parse_condition_str(head)
            if len(branches) > 2:
                cond = {
                    "op": "bad",
                    "raw": head,
                    "why": "inline if takes at most then|else",
                }
        except CondError as e:
            cond = {"op": "bad", "raw": head, "why": str(e)}
        then = [lex_content(branches[0])] if branches[0] else []
        els = [lex_content(branches[1])] if len(branches) > 1 and branches[1] else []
        return {"t": "if", "cond": cond, "then": then, "else": els}
    if "|" in inner:
        branches = inner.split("|")
        if len(branches) >= 2:
            return {
                "t": "alt",
                "mode": "seq",
                "branches": [[lex_content(b)] for b in branches],
            }
    return None


def lex_line(text: str) -> list[dict] | None:
    """one source line -> tokens; None for an empty line"""
    stripped = text.strip()
    if not stripped:
        return None

    # exclusive line markers (design 1.6): the whole line is the marker
    if match := PAUSE_PATTERN.match(stripped):
        return [_mk("pause", match.group(0)[1:].split(" ", 1)[1])]
    if match := BACKGROUND_EFFECTS_PATTERN.match(stripped):
        body = match.group(0)[1:]
        return [
            _mk(
                "focus" if body.lower().startswith("focus") else "effectReset",
                body.split(" ", 1)[1],
            )
        ]
    if match := BACKGROUND_COLOUR_PATTERN.match(stripped):
        return [_mk("background", match.group(1))]
    if match := WEATHER_PATTERN.match(stripped):
        return [_mk("weather", match.group(1))]
    if match := SFX_PATTERN.match(stripped):
        return [_mk("sfx", match.group(1))]
    if match := MESSAGE_TITLE_PATTERN.match(stripped):
        return [_mk("messageTitle", match.group(1))]

    # effect lines (design 1.6): /set, /clear and /roll run at entry
    for prefix in EFFECT_LINE_PREFIXES:
        if stripped.lower().startswith(prefix):
            if prefix == "/set ":
                body = stripped[len(prefix) :]
            else:
                body = f"{prefix[1:]}{stripped[len(prefix) :]}"
            try:
                effect = parse_effect(body)
            except EffectError as e:
                raise ValueError(str(e)) from e
            return [{"t": "fx", **effect}]

    # text lines: known markers anywhere (placement is the checks' business)
    spans: list[tuple[int, int, dict]] = []
    spans += _find_spans(stripped, COLOUR_PATTERN, "colour")
    spans += _find_spans(stripped, PACE_PATTERN, "pace")
    spans += _find_spans(stripped, EFFECT_PATTERN, "effect")
    spans += _find_spans(stripped, POV_PATTERN, "pov", group=1)
    spans += _find_spans(stripped, MESSAGE_UNSENT_PATTERN, "messageUnsent", group=0)
    spans += _find_spans(stripped, MESSAGE_LINE_PATTERN, "message", group=0)
    spans.sort(key=lambda span: span[0])

    # drop overlapping spans (later categories win only if they start later
    # and do not overlap an accepted span; the categories do not overlap)
    accepted: list[tuple[int, int, dict]] = []
    cursor = -1
    for span in spans:
        if span[0] >= cursor:
            accepted.append(span)
            cursor = span[1]

    tokens: list[dict] = []
    cursor = 0
    for start, end, token in accepted:
        if start > cursor:
            tokens += lex_content(stripped[cursor:start])
        # markers keep the shape the renderer expects (value minus leading /)
        if token["k"] in {"message", "messageUnsent"}:
            token["v"] = token["v"].split(" ", 1)[1]
        tokens.append(token)
        cursor = end
    if cursor < len(stripped):
        tokens += lex_content(stripped[cursor:])
    return tokens or None


def lex_body(
    body_lines: list[tuple[int, str]],
    node_file: Path | None = None,
    origins: list[Path] | None = None,
) -> LexResult:
    """whole body: /if blocks nest into if tokens, everything else in order

    line numbers are the origin lines of whichever file each line came from
    (design 1.8), so a bad line inside an include names that file
    """
    lines: list[list[dict]] = []
    stack: list[dict] = []
    error: str | None = None

    def current() -> list[list[dict]]:
        return (
            stack[-1]["else"]
            if stack and stack[-1]["seen_else"]
            else (stack[-1]["then"] if stack else lines)
        )

    for index, (line_no, raw) in enumerate(body_lines):
        stripped = raw.strip()
        if match := IF_PATTERN.match(stripped):
            try:
                cond = parse_condition_str(match.group(1))
            except CondError as e:
                cond = {"op": "bad", "raw": match.group(1), "why": str(e)}
            stack.append(
                {
                    "cond": cond,
                    "then": [],
                    "else": [],
                    "seen_else": False,
                    "line": line_no,
                }
            )
            continue
        if ELSE_PATTERN.match(stripped):
            if not stack:
                error = error or f"/else on line {line_no} with no open /if"
            elif stack[-1]["seen_else"]:
                error = error or f"second /else on line {line_no}"
            else:
                stack[-1]["seen_else"] = True
            continue
        if ENDIF_PATTERN.match(stripped):
            if not stack:
                error = error or f"/endif on line {line_no} with no open /if"
            else:
                frame = stack.pop()
                token = {
                    "t": "if",
                    "cond": frame["cond"],
                    "then": frame["then"],
                    "else": frame["else"],
                }
                current().append([token])
            continue
        try:
            tokens = lex_line(raw)
        except ValueError as e:
            origin = origins[index] if origins else None
            if node_file and origin and origin != node_file:
                # the line was spliced in from elsewhere: name the real file
                # and line, and where it was included from (design 1.8)
                raise ValueError(f"{origin}:{line_no} (via {node_file}): {e}") from e
            raise ValueError(f"line {line_no}: {e}") from e
        if tokens:
            current().append(tokens)

    while stack:
        error = error or "an /if is never closed with /endif"
        frame = stack.pop()
        token = {
            "t": "if",
            "cond": frame["cond"],
            "then": frame["then"],
            "else": frame["else"],
        }
        current().append([token])
    return LexResult(lines=lines, block_error=error)
