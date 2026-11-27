"""v2 compiler: story/*.md -> IR -> validated story.json (version 2).

Pipeline: load + YAML frontmatter (line spans kept) -> lex body lines into
tokens -> build typed IR -> validate IR (all checks live here) -> emit.
Design contract: docs/design.md.
"""

from __future__ import annotations

import itertools
import re
import shlex
import sys
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from json import dumps
from pathlib import Path
from typing import Any

from yaml import YAMLError, safe_load

SPEEDS = "fastest|faster|fast|slowest|slower|slow"
PACE_PATTERN = re.compile(rf"/({SPEEDS}|pace \d+\s?(ms|s))", re.IGNORECASE)
META_PACE_PATTERN = re.compile(rf"^({SPEEDS}|\d+\s?(ms|s))$", re.IGNORECASE)
DEBUG = {"-d", "-debug", "-DEBUG"}.intersection(sys.argv)

NAMED_COLOURS = Path("src/named_colours").read_text().lower().splitlines()
HEX_COLOURS = r"#(?:[0-9a-f]{3}){1,2}"
COLOUR_PATTERN = re.compile(
    rf"/({'|'.join(NAMED_COLOURS)}|reset|colour {HEX_COLOURS})", re.IGNORECASE
)
META_COLOUR_PATTERN = re.compile(
    rf"^({'|'.join(NAMED_COLOURS)}|reset|{HEX_COLOURS})$", re.IGNORECASE
)
BACKGROUND_COLOUR_PATTERN = re.compile(
    rf"^/background ({'|'.join(NAMED_COLOURS)}|reset|{HEX_COLOURS})$", re.IGNORECASE
)

EFFECT_PATTERN = re.compile(r"/(bounce|blink|glow|wave)", re.IGNORECASE)
META_EFFECT_PATTERN = re.compile(rf"^{EFFECT_PATTERN.pattern[1:]}$", re.IGNORECASE)

POV_PATTERN = re.compile(r"/pov (\w+)", re.IGNORECASE)
META_POV_PATTERN = re.compile(r"^\w+$")

MESSAGE_PATTERN = re.compile(r"/message(-unsent)? \w+", re.IGNORECASE)
MESSAGE_UNSENT_PATTERN = re.compile(r"/message-unsent \w+", re.IGNORECASE)
MESSAGE_LINE_PATTERN = re.compile(r"/message \w+", re.IGNORECASE)
META_MESSAGE_PATTERN = re.compile(r"^\w+$")

MESSAGE_TITLE_PATTERN = re.compile(r"^/message-title ([^/]+)$", re.IGNORECASE)
META_MESSAGE_TITLE_PATTERN = re.compile(r"^.+$")

PAUSE_PATTERN = re.compile(r"^/pause \d+\s?(?:ms|s)$", re.IGNORECASE)

BACKGROUND_EFFECTS_PATTERN = re.compile(
    r"^/(" + r"focus (?:\d+(\.\d+)?\%|reset)|effect reset" + ")",
    re.IGNORECASE,
)

WEATHER_TYPES = "rain|snow|fog|fireflies|sunny|clear|none"
WEATHER_PATTERN = re.compile(rf"^/({WEATHER_TYPES})$", re.IGNORECASE)
META_WEATHER_PATTERN = re.compile(rf"^({WEATHER_TYPES})$", re.IGNORECASE)

SFX_PATTERN = re.compile(r"^/sfx ([\w.-]+)$", re.IGNORECASE)

# line-only structural markers for /if blocks
IF_PATTERN = re.compile(r"^/if\s+(.+)$", re.IGNORECASE)
ELSE_PATTERN = re.compile(r"^/else$", re.IGNORECASE)
ENDIF_PATTERN = re.compile(r"^/endif$", re.IGNORECASE)

# line-only effect markers (design 1.6): the whole line is one effect
EFFECT_LINE_PREFIXES = ("/set ", "/clear ", "/roll ")
EFFECT_LINE_STRIP = re.compile(
    r"^/(?:set .+|clear [\w-]+|roll [\w-]+ \d+d\d+(?:[+-]\d+)?)$",
    re.IGNORECASE,
)

# values that mean "turn it off" rather than naming a file
CLEAR_VALUES = {"none", "reset", "clear"}

# frontmatter keys, per docs/design.md 1.2/1.3; keys outside these lists are
# the unknown_keys build error. P1/P2 features add theirs when they land.
NODE_KEYS = {
    "start",
    "end",
    "revisit",
    "title",
    "chapter",
    "sets",
    "clear",
    "vars",
    "next",
    "if",
    "pace",
    "colour",
    "effect",
    "pov",
    "message-pov",
    "message-title",
    "background",
    "weather",
    "image",
    "music",
    "choices",
    "choices_from",
}
CHOICE_KEYS = {"label", "to", "if", "effects", "once", "chance", "fallback"}


def debug(msg: str) -> None:
    if DEBUG:
        print(f" - {msg}")


# ---------------------------------------------------------------------------
# condition grammar (design 1.4): one parser, four levels, AST out
# ---------------------------------------------------------------------------


class CondError(ValueError):
    """a condition string that does not parse"""


_COND_TOKEN = re.compile(
    r"""\s*(?:
        (?P<lparen>\()
      | (?P<rparen>\))
      | (?P<cmp>==|!=|>=|<=|>|<)
      | (?P<str>"[^"]*"|'[^']*')
      | (?P<num>-?\d+(?:\.\d+)?)
      | (?P<ident>[A-Za-z_][\w-]*)
    )""",
    re.VERBOSE,
)
_CMP_TOKEN = re.compile(r"^(>=|<=|==|!=|>|<)$")


def _cond_tokens(text: str) -> list[tuple[str, str]]:
    tokens: list[tuple[str, str]] = []
    pos = 0
    while pos < len(text):
        match = _COND_TOKEN.match(text, pos)
        if not match:
            if text[pos:].strip() == "":
                break
            raise CondError(f"unexpected token {text[pos:]!r} in {text!r}")
        pos = match.end()
        kind = match.lastgroup or ""
        value = match.group(kind)
        if kind == "ident" and value.lower() in {"and", "or", "not"}:
            kind = value.lower()
        tokens.append((kind, value))
    return tokens


class _CondParser:
    def __init__(self, text: str) -> None:
        self.text = text
        self.tokens = _cond_tokens(text)
        self.pos = 0

    def peek(self) -> tuple[str, str] | None:
        return self.tokens[self.pos] if self.pos < len(self.tokens) else None

    def take(self) -> tuple[str, str]:
        token = self.peek()
        if token is None:
            raise CondError(f"unexpected end of condition {self.text!r}")
        self.pos += 1
        return token

    def expect(self, kind: str) -> str:
        token = self.take()
        if token[0] != kind:
            raise CondError(f"expected {kind}, got {token[1]!r} in {self.text!r}")
        return token[1]

    def parse(self) -> dict:
        if not self.tokens:
            raise CondError("empty condition")
        ast = self.parse_or()
        if (rest := self.peek()) is not None:
            raise CondError(f"trailing {rest[1]!r} in {self.text!r}")
        return ast

    def parse_or(self) -> dict:
        args = [self.parse_and()]
        while (token := self.peek()) and token[0] == "or":
            self.take()
            args.append(self.parse_and())
        return args[0] if len(args) == 1 else {"op": "or", "args": args}

    def parse_and(self) -> dict:
        args = [self.parse_not()]
        while (token := self.peek()) and token[0] == "and":
            self.take()
            args.append(self.parse_not())
        return args[0] if len(args) == 1 else {"op": "and", "args": args}

    def parse_not(self) -> dict:
        if (token := self.peek()) and token[0] == "not":
            self.take()
            return {"op": "not", "arg": self.parse_not()}
        return self.parse_primary()

    def parse_primary(self) -> dict:
        token = self.peek()
        if token is None:
            raise CondError(f"unexpected end of condition {self.text!r}")
        if token[0] == "lparen":
            self.take()
            ast = self.parse_or()
            self.expect("rparen")
            return ast
        if token[0] in {"num", "str"} or (
            token[0] == "ident" and token[1] in {"visited", "visits"}
        ):
            return self.parse_comparison_or_truth()
        if token[0] == "ident":
            return self.parse_comparison_or_truth()
        raise CondError(f"unexpected {token[1]!r} in {self.text!r}")

    def parse_comparison_or_truth(self) -> dict:
        lhs = self.parse_term()
        token = self.peek()
        if token and token[0] == "cmp":
            op = self.take()[1]
            rhs = self.parse_term()
            return {"op": "cmp", "lhs": lhs, "cmp": op, "rhs": rhs}
        # a bare name is a truthiness check; everything else needs a comparison
        if isinstance(lhs, str):
            return {"op": "truth", "name": lhs}
        raise CondError(f"{self.text!r} needs a comparison operator")

    def parse_term(self) -> Any:
        kind, value = self.take()
        if kind == "num":
            return float(value) if "." in value else int(value)
        if kind == "str":
            return {"str": value[1:-1]}
        if kind == "ident" and value in {"visited", "visits"}:
            self.expect("lparen")
            name = self.expect("ident")
            self.expect("rparen")
            visits: dict = {"op": "visits", "id": name}
            if value == "visited":
                return {"op": "cmp", "lhs": visits, "cmp": ">=", "rhs": 1}
            return visits
        if kind == "ident":
            return value
        raise CondError(f"unexpected {value!r} in {self.text!r}")


def parse_condition_str(text: str) -> dict:
    """level 4: one full expression -> CondAST (design 1.4)"""
    return _CondParser(text).parse()


def _cond_and(args: list[dict]) -> dict:
    if len(args) == 1:
        return args[0]
    return {"op": "and", "args": args}


def parse_condition(raw: Any) -> dict | None:
    """all four frontmatter levels; None means "no condition"."""
    if raw is None:
        return None
    if isinstance(raw, str):
        if not raw.strip():
            return None
        try:
            return parse_condition_str(raw)
        except CondError as e:
            return {"op": "bad", "raw": raw, "why": str(e)}
    if isinstance(raw, list):
        if not raw:
            return None
        args = []
        for entry in raw:
            if not isinstance(entry, str):
                return {
                    "op": "bad",
                    "raw": repr(entry),
                    "why": "level 1/2 entries must be strings",
                }
            try:
                args.append(parse_condition_str(entry))
            except CondError as e:
                return {"op": "bad", "raw": entry, "why": str(e)}
        return _cond_and(args)
    if isinstance(raw, dict):
        return parse_condition_map(raw)
    return {
        "op": "bad",
        "raw": repr(raw),
        "why": "condition must be a string, list or group map",
    }


_LEVEL3_KEY = re.compile(
    r"^(all|any|none)$|^(at_least|at_most|exactly) (\d+)$|^between (\d+) and (\d+)$"
)


def parse_condition_map(raw: dict) -> dict:
    """level 3: structured count groups, all groups ANDed (design 1.4)"""
    if not raw:
        return {"op": "bad", "raw": "{}", "why": "empty condition map"}
    groups = []
    for key, entries in raw.items():
        if not isinstance(key, str) or not _LEVEL3_KEY.match(key):
            return {
                "op": "bad",
                "raw": repr(key),
                "why": f"unknown group {key!r} (level 4 string for deeper structure)",
            }
        if not isinstance(entries, list) or not entries:
            return {
                "op": "bad",
                "raw": repr(key),
                "why": f"group {key!r} needs a list of expressions",
            }
        args = []
        for entry in entries:
            if not isinstance(entry, str):
                return {
                    "op": "bad",
                    "raw": repr(entry),
                    "why": "no nesting inside groups; use a level 4 string",
                }
            try:
                args.append(parse_condition_str(entry))
            except CondError as e:
                return {"op": "bad", "raw": entry, "why": str(e)}
        bound = _LEVEL3_KEY.match(key)
        if bound.group(1) == "all":
            minimum, maximum = len(args), len(args)
        elif bound.group(1) == "any":
            minimum, maximum = 1, None
        elif bound.group(1) == "none":
            minimum, maximum = 0, 0
        elif bound.group(2) == "at_least":
            minimum, maximum = int(bound.group(3)), None
        elif bound.group(2) == "at_most":
            minimum, maximum = 0, int(bound.group(3))
        elif bound.group(2) == "exactly":
            minimum = maximum = int(bound.group(3))
        else:  # between N and M
            minimum, maximum = int(bound.group(4)), int(bound.group(5))
        groups.append({"op": "count", "min": minimum, "max": maximum, "args": args})
    return _cond_and(groups)


def walk_cond(cond: dict | None) -> dict:
    """yield every cond node in an AST (for checks)"""
    if not cond:
        return
    yield cond
    for key in ("args", "arg"):
        child = cond.get(key)
        if isinstance(child, dict):
            yield from walk_cond(child)
        elif isinstance(child, list):
            for item in child:
                if isinstance(item, dict):
                    yield from walk_cond(item)


def cond_names(cond: dict | None) -> set[str]:
    """every variable name a condition reads"""
    names: set[str] = set()
    for node in walk_cond(cond):
        op = node.get("op")
        if op in {"truth"}:
            names.add(node.get("name", ""))
        elif op == "visits":
            names.add(node.get("id", ""))
        elif op == "cmp":
            for side in (node.get("lhs"), node.get("rhs")):
                if isinstance(side, str):
                    names.add(side)
                elif isinstance(side, dict) and side.get("op") == "visits":
                    names.add(side.get("id", ""))
    return names - {""}


def cond_is_comparison(cond: dict | None) -> bool:
    """whether a condition reads names through comparisons (vs truth checks)"""
    for node in walk_cond(cond):
        if node.get("op") == "cmp":
            return True
    return False


# ---------------------------------------------------------------------------
# effect grammar (design 1.5): one parser, three spellings
# ---------------------------------------------------------------------------

_EFFECT_CLEAR = re.compile(r"^clear\s+([\w-]+)$")
_EFFECT_ROLL = re.compile(r"^roll\s+([\w-]+)\s+(\d+)d(\d+)([+-]\d+)?$")
_EFFECT_UNLOCK = re.compile(r"^unlock\s+([\w-]+)$")
_EFFECT_ASSIGN = re.compile(r"^([\w-]+)\s*=\s*(.+)$")
_EFFECT_ADD = re.compile(r"^([\w-]+)\s*([+-]\s*\d+(?:\.\d+)?)$")
_EFFECT_SET = re.compile(r"^([\w-]+)$")


class EffectError(ValueError):
    """an effect string that does not parse"""


def parse_effect(text: str) -> dict:
    raw = text.strip()
    if match := _EFFECT_CLEAR.match(raw):
        return {"op": "clear", "name": match.group(1)}
    if match := _EFFECT_ROLL.match(raw):
        dice = [int(match.group(2)), int(match.group(3)), int(match.group(4) or 0)]
        return {"op": "roll", "var": match.group(1), "dice": dice}
    if match := _EFFECT_UNLOCK.match(raw):
        return {"op": "unlock", "id": match.group(1)}
    if match := _EFFECT_ASSIGN.match(raw):
        return {
            "op": "assign",
            "name": match.group(1),
            "val": _effect_value(match.group(2)),
        }
    if match := _EFFECT_ADD.match(raw):
        val = float(match.group(2).replace(" ", ""))
        return {
            "op": "add",
            "name": match.group(1),
            "val": int(val) if val.is_integer() else val,
        }
    if match := _EFFECT_SET.match(raw):
        return {"op": "set", "name": match.group(1)}
    raise EffectError(f"cannot parse effect {text!r}")


def _effect_value(text: str) -> Any:
    value = text.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        return value[1:-1]
    if value.lower() in {"true", "false"}:
        return value.lower() == "true"
    try:
        number = float(value)
        return int(number) if number.is_integer() else number
    except ValueError:
        return value


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


# ---------------------------------------------------------------------------
# IR (design 3.2): every IR node carries (file, line)
# ---------------------------------------------------------------------------


@dataclass
class ChoiceIR:
    label: str
    target: str
    file: Path
    line: int = 1
    cond: dict | None = None
    effects: list[dict] = field(default_factory=list)
    once: bool = False
    chance: int = 100
    fallback: bool = False


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


def parse_choices(raw: Any, filepath: Path, unknown: list[str]) -> list[ChoiceIR]:
    """choices is a list of {label, to, if, effects, once, chance, fallback}"""
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise TypeError(
            "choices must be a list of '- label: ... / to: ...' entries, "
            "not a label: target mapping"
        )

    choices = []
    for i, entry in enumerate(raw):
        if not isinstance(entry, dict):
            raise TypeError(f"choice {i + 1} must be a mapping with label and to")

        label = entry.get("label")
        target = entry.get("to")
        if not label or not target:
            raise ValueError(f"choice {i + 1} needs both a label and a to")
        for key in entry:
            if key not in CHOICE_KEYS:
                unknown.append(f"choice {i + 1} key {key!r}")

        effects_raw = entry.get("effects") or []
        if isinstance(effects_raw, str):
            effects_raw = [effects_raw]
        if not isinstance(effects_raw, list):
            raise TypeError(f"choice {i + 1} effects must be a list")
        effects = []
        for effect_text in effects_raw:
            if not isinstance(effect_text, str):
                raise TypeError(f"choice {i + 1} effect entries must be strings")
            try:
                effects.append(parse_effect(effect_text))
            except EffectError as e:
                raise ValueError(f"{filepath}: choice {i + 1} {e}") from e

        chance = entry.get("chance", 100)
        if (
            not isinstance(chance, int)
            or isinstance(chance, bool)
            or not 0 <= chance <= 100
        ):
            raise ValueError(f"choice {i + 1} chance must be an int 0-100")

        choices.append(
            ChoiceIR(
                label=str(label),
                target=str(target),
                file=filepath,
                cond=parse_condition(entry.get("if")),
                effects=effects,
                once=bool(entry.get("once", False)),
                chance=chance,
                fallback=bool(entry.get("fallback", False)),
            )
        )

    labels = [choice.label for choice in choices]
    if len(labels) != len(set(labels)):
        raise ValueError("choices must have unique labels")

    return choices


def load_choices_from(
    ref: str,
    filepath: Path,
    unknown: list[str],
    seen: frozenset[str] = frozenset(),
) -> list[ChoiceIR]:
    """merge a shared file's frontmatter choices (design 1.8)"""
    if ref in seen:
        raise ValueError(f"{filepath}: choices_from cycle via {ref}")
    if not ref.startswith("_"):
        raise ValueError(
            f"{filepath}: choices_from must point at a '_' file, got {ref!r}"
        )
    target = Path("story") / f"{ref}.md"
    if not target.is_file():
        raise ValueError(f"{filepath}: choices_from file not found: {ref}")

    try:
        metadata, _body = parse_markdown(target.read_text("utf-8"))
    except ValueError as e:
        raise ValueError(f"{target}: {e}") from e
    if metadata.get("choices") is None:
        raise ValueError(f"{filepath}: choices_from file has no choices: {ref}")

    merged = parse_choices(metadata.get("choices"), target, unknown)
    chained = metadata.get("choices_from")
    if chained is not None:
        merged += load_choices_from(str(chained), target, unknown, seen | {ref})
    return merged


def parse_front_effects(metadata: dict[str, Any], filepath: Path) -> list[dict]:
    """sets/clear/vars frontmatter -> one effects list (design 1.2/1.5)"""
    effects: list[dict] = []

    raw_sets = metadata.get("sets") or []
    if isinstance(raw_sets, str):
        raw_sets = [raw_sets]
    if not isinstance(raw_sets, list) or not all(
        isinstance(flag, str) for flag in raw_sets
    ):
        raise ValueError(f"{filepath}: sets must be a name or list of names")
    for name in raw_sets:
        try:
            effects.append(parse_effect(name))
        except EffectError as e:
            raise ValueError(f"{filepath}: sets: {e}") from e

    raw_clear = metadata.get("clear") or []
    if isinstance(raw_clear, str):
        raw_clear = [raw_clear]
    if not isinstance(raw_clear, list) or not all(
        isinstance(flag, str) for flag in raw_clear
    ):
        raise ValueError(f"{filepath}: clear must be a name or list of names")
    for name in raw_clear:
        try:
            effects.append(parse_effect(f"clear {name}"))
        except EffectError as e:
            raise ValueError(f"{filepath}: clear: {e}") from e

    raw_vars = metadata.get("vars") or {}
    if not isinstance(raw_vars, dict) or not all(isinstance(k, str) for k in raw_vars):
        raise ValueError(f"{filepath}: vars must be a mapping of name: value")
    for vname, vvalue in raw_vars.items():
        if isinstance(vvalue, bool) or not isinstance(vvalue, (int, float, str)):
            raise TypeError(
                f"{filepath}: vars.{vname} must be a number, a string "
                f'or a "+n"/"-n" string'
            )
        if isinstance(vvalue, (int, float)):
            effects.append({"op": "assign", "name": vname, "val": vvalue})
        elif re.fullmatch(r"[+-]\s*\d+(?:\.\d+)?", vvalue.strip()):
            val = float(vvalue.replace(" ", ""))
            effects.append(
                {
                    "op": "add",
                    "name": vname,
                    "val": int(val) if val.is_integer() else val,
                }
            )
        else:
            effects.append({"op": "assign", "name": vname, "val": vvalue})
    return effects


def find_parts() -> dict[str, NodeIR]:
    parts: dict[str, NodeIR] = {}
    base = Path("story")
    for f in base.glob("**/*.md"):
        rel = f.relative_to(base)
        if any(name.startswith("_") for name in rel.parts):
            continue  # shared macro/include files are not nodes (design 1.1)
        pathname = rel.parts[-2] if len(rel.parts) > 1 else f.stem

        try:
            metadata, body = parse_markdown(f.read_text("utf-8"))
        except ValueError as e:
            raise ValueError(f"{f}: {e}") from e

        unknown = [f"node key {key!r}" for key in metadata if key not in NODE_KEYS]
        try:
            choices = parse_choices(metadata.get("choices"), f, unknown)
            if metadata.get("choices_from") is not None:
                choices += load_choices_from(str(metadata["choices_from"]), f, unknown)
                labels = [choice.label for choice in choices]
                if len(labels) != len(set(labels)):
                    raise ValueError(
                        "choices must have unique labels (incl. choices_from)"
                    )
            effects = parse_front_effects(metadata, f)
        except (ValueError, TypeError) as e:
            raise ValueError(f"{f}: {e}") from e

        body_lines = list(enumerate(body.splitlines(), 1))
        expanded, origins, expand_errors = expand_body(body_lines, f)
        try:
            lexed = lex_body(expanded, node_file=f, origins=origins)
        except ValueError as e:
            message = str(e)
            if not message.startswith("story/"):
                message = f"{f}: {message}"
            raise ValueError(message) from e
        variant = VariantIR(
            filepath=f,
            pathname=pathname,
            line=1,
            src=expanded,
            lines=lexed.lines,
            block_error=lexed.block_error,
            choices=choices,
            effects=effects,
            unknown_keys=unknown,
            expand_errors=expand_errors,
            revisit=bool(metadata.get("revisit", True)),
        )
        for key, attr in PRESENTATION_KEYS.items():
            setattr(variant, attr, metadata.get(key))

        node = parts.get(pathname)
        if node is None:
            node = NodeIR(id=pathname, filepath=f)
            parts[pathname] = node
        node.variants.append(variant)
        node.is_start = node.is_start or bool(metadata.get("start", False))
        node.is_end = node.is_end or bool(metadata.get("end", False))
        if node.title is None and metadata.get("title"):
            node.title = str(metadata["title"])
        if node.chapter is None and metadata.get("chapter"):
            node.chapter = str(metadata["chapter"])
        if node.next is None and metadata.get("next"):
            node.next = str(metadata["next"])
        if node.next_if is None and metadata.get("if") is not None:
            node.next_if = parse_condition(metadata.get("if"))
        debug(f"added {f.name} to {pathname}")

    return parts


# ---------------------------------------------------------------------------
# condition gathering for checks: walk token lines for every cond AST
# ---------------------------------------------------------------------------


def iter_conds(lines: list) -> Iterator[dict]:
    """every cond in a token line-list: block ifs, inline ifs, alt branches"""
    for line in lines:
        for token in line:
            if token["t"] == "if":
                yield token["cond"]
                yield from iter_conds(token["then"])
                yield from iter_conds(token["else"])
            elif token["t"] == "alt":
                for branch in token["branches"]:
                    yield from iter_conds(branch)


def variant_conds(variant: VariantIR) -> Iterator[dict]:
    """every cond a variant reads: choice gates plus /if and {cond:} sites"""
    for choice in variant.choices:
        if choice.cond:
            yield choice.cond
    yield from iter_conds(variant.lines)


def iter_fx(lines: list) -> Iterator[dict]:
    """every line-level fx token: block ifs, inline ifs, alt branches"""
    for line in lines:
        for token in line:
            if token["t"] == "fx":
                yield token
            elif token["t"] == "if":
                yield from iter_fx(token["then"])
                yield from iter_fx(token["else"])
            elif token["t"] == "alt":
                for branch in token["branches"]:
                    yield from iter_fx(branch)


def iter_var_names(lines: list) -> Iterator[str]:
    """every {name} substitution site in a token line-list"""
    for line in lines:
        for token in line:
            if token["t"] == "var":
                yield token["name"]
            elif token["t"] == "if":
                yield from iter_var_names(token["then"])
                yield from iter_var_names(token["else"])
            elif token["t"] == "alt":
                for branch in token["branches"]:
                    yield from iter_var_names(branch)


def _effect_writes(parts: dict[str, NodeIR]) -> set[str]:
    """every name any effect writes (design: flags and vars unified)"""
    names: set[str] = set()
    for path in parts.values():
        for part in path.variants:
            for effect in [
                *part.effects,
                *(e for c in part.choices for e in c.effects),
                *iter_fx(part.lines),
            ]:
                if "name" in effect:
                    names.add(effect["name"])
                elif effect.get("op") == "roll":
                    names.add(effect["var"])
    return names


def _truth_reads(cond: dict | None) -> set[str]:
    """names read for truthiness (the old unknown_flags domain)"""
    return {
        node.get("name", "") for node in walk_cond(cond) if node.get("op") == "truth"
    } - {""}


def _cmp_reads(cond: dict | None) -> set[str]:
    """names read through comparisons (the old unknown_vars domain)"""
    names: set[str] = set()
    for node in walk_cond(cond):
        if node.get("op") != "cmp":
            continue
        for side in (node.get("lhs"), node.get("rhs")):
            if isinstance(side, str):
                names.add(side)
    return names


# ---------------------------------------------------------------------------
# checks (design 4.1): 44 migrated + unknown_keys + count_range = 46
# ---------------------------------------------------------------------------

# strips a whole conditional marker so unknown_markers does not flag it
CONDITIONAL_STRIP_PATTERN = re.compile(r"^/(?:if\s+.+|else|endif)$", re.IGNORECASE)


def all_nodes(parts: dict[str, NodeIR]) -> list[VariantIR]:
    nodes = []
    for path in parts.values():
        nodes.extend(path.variants)
    return nodes


def starting_nodes(parts: dict[str, NodeIR]) -> list[VariantIR]:
    nodes = []
    for path in parts.values():
        if path.is_start:
            nodes.extend(path.variants)
    return nodes


def ending_nodes(parts: dict[str, NodeIR]) -> list[VariantIR]:
    nodes = []
    for path in parts.values():
        if path.is_end:
            nodes.extend(path.variants)
    return nodes


def start_end_nodes(parts: dict[str, NodeIR]) -> list[VariantIR]:
    nodes = []
    for path in parts.values():
        if path.is_end and path.is_start:
            nodes.extend(path.variants)
    return nodes


def empty_nodes(parts: dict[str, NodeIR]) -> list[VariantIR]:
    nodes = []
    for path in parts.values():
        for part in path.variants:
            if not part.text:
                nodes.append(part)
    return nodes


def duplicate_nodes(parts: dict[str, NodeIR]) -> list[VariantIR]:
    text = []
    nodes = []
    for path in parts.values():
        for part in path.variants:
            if part.text in text:
                nodes.append(part)
            else:
                text.append(part.text)
    return nodes


def invalid_links(parts: dict[str, NodeIR]) -> list[VariantIR]:
    nodes = []
    for path in parts.values():
        if path.is_end:
            continue

        broken_next = bool(path.next) and path.next not in parts
        for part in path.variants:
            bad = broken_next
            if broken_next:
                debug(f"{part.pathname}: next {path.next} was not in {parts.keys()}")
            for choice in part.choices:
                if choice.target not in parts:
                    debug(f"{part.pathname}: {choice.target} was not in {parts.keys()}")
                    bad = True
                    break
            if bad:
                nodes.append(part)
    return nodes


def dead_ends(parts: dict[str, NodeIR]) -> list[VariantIR]:
    nodes = []
    for path in parts.values():
        # a next: fall-through is a continuation, not a dead end
        if not path.is_end and not path.next:
            for part in path.variants:
                if not part.choices:
                    nodes.append(part)
    return nodes


def fully_conditional(parts: dict[str, NodeIR]) -> list[VariantIR]:
    """every choice needs a flag, so a player missing all of them is stuck"""
    nodes = []
    for path in parts.values():
        if path.is_end or (path.next and not path.next_if):
            continue
        for part in path.variants:
            if part.choices and all(choice.cond for choice in part.choices):
                nodes.append(part)
    return nodes


def _all_reads(cond: dict | None) -> set[str]:
    """every var/flag name a condition reads, truth or comparison"""
    return _truth_reads(cond) | _cmp_reads(cond)


def unknown_names(parts: dict[str, NodeIR]) -> list[VariantIR]:
    """conditions and {vars} reading a name no effect ever writes (design 4.1)"""
    writes = _effect_writes(parts)
    nodes = []
    for path in parts.values():
        node_reads = _all_reads(path.next_if)
        for part in path.variants:
            needed = set(node_reads)
            for cond in variant_conds(part):
                needed |= _all_reads(cond)
            needed |= set(iter_var_names(part.lines))
            if needed - writes:
                nodes.append(part)
                debug(
                    f"{part.pathname}: unknown names: "
                    + ", ".join(sorted(needed - writes))
                )
    return nodes


def _part_writes(part: VariantIR) -> set[str]:
    """names one variant's effects write (frontmatter, choices, line fx)"""
    names: set[str] = set()
    for effect in [
        *part.effects,
        *(e for c in part.choices for e in c.effects),
        *iter_fx(part.lines),
    ]:
        if "name" in effect:
            names.add(effect["name"])
        elif effect.get("op") == "roll":
            names.add(effect["var"])
    return names


def set_but_never_read(parts: dict[str, NodeIR]) -> list[VariantIR]:
    """names effects write but no condition or {var} ever reads (design 4.1)"""
    reads: set[str] = set()
    for path in parts.values():
        reads |= _all_reads(path.next_if)
        for part in path.variants:
            for cond in variant_conds(part):
                reads |= _all_reads(cond)
            reads |= set(iter_var_names(part.lines))

    nodes = []
    for path in parts.values():
        for part in path.variants:
            dead = _part_writes(part) - reads
            if dead:
                nodes.append(part)
                debug(
                    f"{part.pathname}: set but never read: " + ", ".join(sorted(dead))
                )
    return nodes


def _cond_numeric(cond: dict | None) -> bool:
    """whether a cond reads through comparisons or visits(): flag domain only"""
    return any(node.get("op") in {"cmp", "visits"} for node in walk_cond(cond))


def _eval_flag_cond(cond: dict, assignment: dict[str, bool]) -> bool:
    """concrete eval over a flag assignment (names absent are stuck false)"""
    op = cond.get("op")
    if op == "truth":
        return assignment.get(cond.get("name", ""), False)
    if op == "not":
        return not _eval_flag_cond(cond.get("arg") or {}, assignment)
    if op == "and":
        return all(_eval_flag_cond(arg, assignment) for arg in cond.get("args", []))
    if op == "or":
        return any(_eval_flag_cond(arg, assignment) for arg in cond.get("args", []))
    if op == "count":
        hits = sum(
            1 for arg in cond.get("args", []) if _eval_flag_cond(arg, assignment)
        )
        high = cond.get("max")
        return hits >= cond.get("min", 0) and (high is None or hits <= high)
    return True  # bad/numeric conds never disprove satisfiability


def _cond_satisfiable(cond: dict | None, maybe: set[str]) -> bool:
    """can the cond ever be true? names outside maybe are stuck false"""
    if not cond:
        return True
    if _cond_numeric(cond):
        return True  # number domain: unknown_names owns unread names
    names = sorted(_truth_reads(cond) & maybe)
    if len(names) > 8:
        return True  # bail out of big conjunctions rather than guess
    for bits in itertools.product((False, True), repeat=len(names)):
        if _eval_flag_cond(cond, dict(zip(names, bits))):
            return True
    return False


def _set_sites(parts: dict[str, NodeIR]) -> list[tuple[str, list[dict]]]:
    """(name, guard conds) per write site; empty guards = unconditional"""
    sites: list[tuple[str, list[dict]]] = []

    def take(effect: dict, guards: list[dict]) -> None:
        if "name" in effect:
            sites.append((effect["name"], guards))
        elif effect.get("op") == "roll":
            sites.append((effect["var"], guards))

    def walk(lines: list, guards: list[dict]) -> None:
        for line in lines:
            for token in line:
                if token["t"] == "fx":
                    take(token, guards)
                elif token["t"] == "if":
                    walk(token["then"], guards + [token["cond"]])
                    walk(
                        token["else"],
                        guards + [{"op": "not", "arg": token["cond"]}],
                    )
                elif token["t"] == "alt":
                    for branch in token["branches"]:
                        walk(branch, guards)

    for path in parts.values():
        for part in path.variants:
            for effect in part.effects:
                take(effect, [])
            walk(part.lines, [])
            for choice in part.choices:
                for effect in choice.effects:
                    take(effect, [choice.cond] if choice.cond else [])
    return sites


def _settable_names(parts: dict[str, NodeIR]) -> set[str]:
    """names that can actually become true: monotone fixpoint over guards"""
    maybe: set[str] = set()
    sites = _set_sites(parts)
    changed = True
    while changed:
        changed = False
        for name, guards in sites:
            if name in maybe:
                continue
            if all(_cond_satisfiable(guard, maybe) for guard in guards):
                maybe.add(name)
                changed = True
    return maybe


def satisfiability(parts: dict[str, NodeIR]) -> list[VariantIR]:
    """never-true conditions in the flag domain (design 4.1)"""
    writes = _effect_writes(parts)
    maybe = _settable_names(parts)
    nodes = []
    for path in parts.values():
        node_conds = [path.next_if] if path.next_if else []
        for part in path.variants:
            problem = None
            for cond in [*node_conds, *variant_conds(part)]:
                reads = _truth_reads(cond)
                if not reads or not reads <= writes:
                    continue  # no flag reads, or unknown_names' domain
                if not _cond_satisfiable(cond, maybe):
                    problem = "condition can never be true: " + ", ".join(sorted(reads))
                    break
            if problem:
                nodes.append(part)
                debug(f"{part.pathname}: {problem}")
    return nodes


def chance_only_exit(parts: dict[str, NodeIR]) -> list[VariantIR]:
    """chance on the only statically visible exit (design 4.1)"""
    nodes = []
    for path in parts.values():
        if path.is_end or (path.next and not path.next_if):
            continue  # endings and unconditional next never need a choice
        for part in path.variants:
            if not part.choices:
                continue
            cond_free = [choice for choice in part.choices if choice.cond is None]
            if (
                len(cond_free) == 1
                and cond_free[0].chance < 100
                and not any(choice.fallback for choice in part.choices)
            ):
                nodes.append(part)
                debug(
                    f"{part.pathname}: chance {cond_free[0].chance} on the only "
                    f"visible exit {cond_free[0].label!r}"
                )
    return nodes


def condition_syntax(parts: dict[str, NodeIR]) -> list[VariantIR]:
    """conditions that are not valid at their site (design 1.4)"""
    nodes = []
    for path in parts.values():
        node_conds = [path.next_if] if path.next_if else []
        for part in path.variants:
            for cond in [*node_conds, *variant_conds(part)]:
                bad = next((n for n in walk_cond(cond) if n.get("op") == "bad"), None)
                if bad:
                    nodes.append(part)
                    debug(
                        f"{part.pathname}: condition {bad.get('raw')!r}: "
                        f"{bad.get('why')}"
                    )
                    break
    return nodes


def conditional_blocks(parts: dict[str, NodeIR]) -> list[VariantIR]:
    """/if, /else and /endif must nest correctly within each part"""
    nodes = []
    for path in parts.values():
        for part in path.variants:
            if part.block_error:
                nodes.append(part)
                debug(f"{part.pathname}: {part.block_error}")
    return nodes


def continuing_ends(parts: dict[str, NodeIR]) -> list[VariantIR]:
    nodes = []
    for path in parts.values():
        if path.is_end:
            for part in path.variants:
                if part.choices:
                    nodes.append(part)
    return nodes


def revisit_variants(parts: dict[str, NodeIR]) -> list[VariantIR]:
    nodes = []
    for path in parts.values():
        for part in path.variants:
            if path.revisit and not part.revisit:
                nodes.append(part)
    return nodes


def noncontinuing_variants(parts: dict[str, NodeIR]) -> list[VariantIR]:
    nodes = []
    for path in parts.values():
        variant_choices = any(len(part.choices) > 0 for part in path.variants)
        for part in path.variants:
            if variant_choices and not part.choices:
                nodes.append(part)
    return nodes


def single_choice(parts: dict[str, NodeIR]) -> list[VariantIR]:
    nodes = []
    for path in parts.values():
        if not path.is_end:
            for part in path.variants:
                if len(part.choices) == 1:
                    nodes.append(part)
    # a story where every continuing part has exactly one choice is a linear
    # narrative on purpose; warning about each chapter is just noise
    continuing = [
        part for path in parts.values() if not path.is_end for part in path.variants
    ]
    if continuing and len(nodes) == len(continuing):
        return []
    return nodes


def duplicate_choices(parts: dict[str, NodeIR]) -> list[VariantIR]:
    nodes = []
    for path in parts.values():
        if not path.is_end:
            for part in path.variants:
                if len(part.choices) != len({choice.target for choice in part.choices}):
                    nodes.append(part)
    return nodes


def unreachable_nodes(parts: dict[str, NodeIR]) -> list[VariantIR]:
    stack = starting_nodes(parts)
    every_node = all_nodes(parts)
    if not stack:
        return every_node

    visited: set[str] = set()
    while stack:
        node = stack.pop()
        if node.pathname in visited:
            continue

        visited.add(node.pathname)
        path = parts[node.pathname]
        if path.is_end:
            continue

        for choice in node.choices:
            if choice.target in parts:
                stack.extend(parts[choice.target].variants)
        # next is a structural edge too (design 1.2): a node only reachable
        # through a continuation is still reachable
        if path.next and path.next in parts:
            stack.extend(parts[path.next].variants)
    return [node for node in every_node if node.pathname not in visited]


def looping_nodes(parts: dict[str, NodeIR]) -> list[list[VariantIR]]:
    loops: list[list[VariantIR]] = []
    # dense menus make the walkable paths explode combinatorially; stop after
    # a generous budget so validation always finishes (small stories finish
    # long before the cap, so their output is unaffected)
    budget = 50_000

    def depth_search(node: VariantIR, ancestors: list[VariantIR] | None = None) -> None:
        nonlocal budget
        if budget <= 0:
            return
        budget -= 1
        ancestors = ancestors or []
        ancestor_names = [ancestor.pathname for ancestor in ancestors]
        if node.pathname in ancestor_names:
            loops.append(ancestors + [node])
            return

        if parts[node.pathname].is_end:
            return

        # we've visited too many nodes without looping, how?
        if len(ancestors) > 2 * len(parts):
            return

        for choice in node.choices:
            if choice.target in parts:
                # skip if we're not revisitin
                if not parts[choice.target].revisit and choice.target in ancestor_names:
                    continue

                for variant in parts[choice.target].variants:
                    depth_search(variant, ancestors + [node])

    for node in starting_nodes(parts):
        depth_search(node)

    def canonical_looping(
        loop: list[VariantIR],
    ) -> tuple[list[VariantIR], list[str]]:
        names = [part.pathname for part in loop]
        # the loop closes on itself, trim everything before the first repeat
        start = names.index(names[-1])

        loop = loop[start:]
        names = names[start:]

        # rotate so every entry point of the same loop collapses to one form
        rotations = [tuple(names[i:] + names[:i]) for i in range(len(names))]
        best = rotations.index(min(rotations))
        return loop[best:] + loop[:best], names[best:] + names[:best]

    unique: list[list[VariantIR]] = []
    unique_name: list[list[str]] = []
    for loop in loops:
        this_loop, this_name = canonical_looping(loop)
        if this_name not in unique_name:
            unique.append(this_loop)
            unique_name.append(this_name)

    return unique


def _nodes_reaching_end(parts: dict[str, NodeIR]) -> set[str]:
    """every node that can reach an ending, via one reverse breadth-first pass"""
    cached = getattr(_nodes_reaching_end, "_cache", None)
    if cached is not None and cached[0] is parts:
        return cached[1]

    reverse: dict[str, list[str]] = {name: [] for name in parts}
    for name, part in parts.items():
        for variant in part.variants:
            for choice in variant.choices:
                if choice.target in parts:
                    reverse[choice.target].append(name)

    reachable = {name for name, part in parts.items() if part.is_end}
    stack = list(reachable)
    while stack:
        for pred in reverse[stack.pop()]:
            if pred not in reachable:
                reachable.add(pred)
                stack.append(pred)

    _nodes_reaching_end._cache = (parts, reachable)
    return reachable


def can_escape_loop(parts: dict[str, NodeIR], loop: list[VariantIR]) -> bool:
    """can the story reach an ending without going back around this loop"""
    # walking every path from every loop node re-exploded on dense graphs;
    # reachability is direction-independent, so one reverse pass answers all
    # of the loops at once
    reaching = _nodes_reaching_end(parts)
    return any(node.pathname in reaching for node in loop)


def escapable_looping_nodes(
    parts: dict[str, NodeIR],
) -> list[list[VariantIR]]:
    return [loop for loop in looping_nodes(parts) if can_escape_loop(parts, loop)]


def inescapable_looping_nodes(
    parts: dict[str, NodeIR],
) -> list[list[VariantIR]]:
    return [loop for loop in looping_nodes(parts) if not can_escape_loop(parts, loop)]


def abnormal_paths(parts: dict[str, NodeIR]) -> list[list[VariantIR]]:
    all_paths: list[list[VariantIR]] = []
    visited_paths: set[tuple[str]] = set()
    # same budget idea as looping_nodes: generous enough that small stories
    # enumerate completely, finite so a dense graph cannot hang the build
    budget = 50_000

    def traverse(node: VariantIR, path: list[VariantIR] | None = None):
        nonlocal budget
        if budget <= 0:
            return
        budget -= 1
        path = path or []
        new_path = path + [node]
        pathnames = tuple(p.pathname for p in new_path)

        # the path found is way too long.
        if len(path) > 5 * len(parts):
            return

        if pathnames in visited_paths:
            return
        visited_paths.add(pathnames)

        this_part = parts[node.pathname]

        has_valid_choices = any(
            any(choice.target in parts for choice in variant.choices)
            for variant in this_part.variants
        )

        if this_part.is_end or not has_valid_choices:
            all_paths.append(new_path)
            return

        for variant in this_part.variants:
            for choice in variant.choices:
                if choice.target not in parts:
                    continue

                # skip if we're not revisitin
                if choice.target in pathnames and not parts[choice.target].revisit:
                    continue

                for next_variant in parts[choice.target].variants:
                    traverse(next_variant, new_path)

    for start in starting_nodes(parts):
        traverse(start)

    if not all_paths:
        return []

    average_path = sum(len(path) for path in all_paths) / len(all_paths)
    return [path for path in all_paths if abs(len(path) - average_path) > 1]


def unknown_markers(parts: dict[str, NodeIR]) -> list[VariantIR]:
    nodes = []

    for path in parts.values():
        for part in path.variants:
            for line in part.text.splitlines():
                stripped = line.strip()
                if not stripped:
                    continue

                for regex in [
                    PACE_PATTERN,
                    COLOUR_PATTERN,
                    BACKGROUND_COLOUR_PATTERN,
                    EFFECT_PATTERN,
                    POV_PATTERN,
                    MESSAGE_PATTERN,
                    MESSAGE_TITLE_PATTERN,
                    PAUSE_PATTERN,
                    WEATHER_PATTERN,
                    SFX_PATTERN,
                    BACKGROUND_EFFECTS_PATTERN,
                    CONDITIONAL_STRIP_PATTERN,
                    EFFECT_LINE_STRIP,
                ]:
                    stripped = regex.sub("", stripped)

                if markers := re.findall(r"(?:^|[^`\w])(/\w[\w.-]*)", stripped):
                    nodes.append(part)
                    debug(
                        f"{part.pathname}: Unknown markers in text: "
                        + ", ".join(markers)
                    )

    return nodes


def command_metadata(
    parts: dict[str, NodeIR],
    regex: re.Pattern[str] = META_COLOUR_PATTERN,
    property: str = "colour",
) -> list[VariantIR]:
    nodes = []

    for path in parts.values():
        for part in path.variants:
            match = getattr(part, property, None)
            if not match:
                continue
            if not isinstance(match, str) or not regex.match(match):
                debug(f"{part.pathname}: has invalid metadata pattern")
                nodes.append(part)

    return nodes


def commands_in_text(
    parts: dict[str, NodeIR],
    regex: re.Pattern[str] = META_COLOUR_PATTERN,
    allow_multiple: bool = False,
    only: bool = False,
) -> list[VariantIR]:
    nodes = []

    for path in parts.values():
        for part in path.variants:
            for line in part.text.splitlines():
                stripped = line.strip()
                if not stripped:
                    continue

                markers = regex.findall(stripped)
                if not allow_multiple and len(markers) > 1:
                    debug(f"{part.pathname}: has more than one marker")
                    nodes.append(part)
                    break

                if markers and not stripped.startswith("/"):
                    debug(f"{part.pathname}: has markers not at the start of the text")
                    nodes.append(part)
                    break

                if markers and only and regex.sub("", stripped).strip():
                    debug(
                        f"{part.pathname}: has other markers despite being "
                        "an exclusive line"
                    )
                    nodes.append(part)
                    break

    return nodes


def colour_metadata(parts: dict[str, NodeIR]) -> list[VariantIR]:
    return command_metadata(parts, META_COLOUR_PATTERN, "colour")


def colour_markers(parts: dict[str, NodeIR]) -> list[VariantIR]:
    return commands_in_text(parts, COLOUR_PATTERN)


def pace_metadata(parts: dict[str, NodeIR]) -> list[VariantIR]:
    return command_metadata(parts, META_PACE_PATTERN, "pace")


def pace_markers(parts: dict[str, NodeIR]) -> list[VariantIR]:
    return commands_in_text(parts, PACE_PATTERN)


def effect_metadata(parts: dict[str, NodeIR]) -> list[VariantIR]:
    return command_metadata(parts, META_EFFECT_PATTERN, "effect")


def effect_markers(parts: dict[str, NodeIR]) -> list[VariantIR]:
    return commands_in_text(parts, EFFECT_PATTERN, allow_multiple=True)


def pov_metadata(parts: dict[str, NodeIR]) -> list[VariantIR]:
    return command_metadata(parts, META_POV_PATTERN, "pov")


def pov_markers(parts: dict[str, NodeIR]) -> list[VariantIR]:
    return commands_in_text(parts, POV_PATTERN)


def message_metadata(parts: dict[str, NodeIR]) -> list[VariantIR]:
    return command_metadata(parts, META_MESSAGE_PATTERN, "messagepov")


def message_markers(parts: dict[str, NodeIR]) -> list[VariantIR]:
    return commands_in_text(parts, MESSAGE_PATTERN)


def message_title_metadata(parts: dict[str, NodeIR]) -> list[VariantIR]:
    return command_metadata(parts, META_MESSAGE_TITLE_PATTERN, "messagetitle")


def message_title_markers(parts: dict[str, NodeIR]) -> list[VariantIR]:
    return commands_in_text(parts, MESSAGE_TITLE_PATTERN, only=True)


def weather_metadata(parts: dict[str, NodeIR]) -> list[VariantIR]:
    return command_metadata(parts, META_WEATHER_PATTERN, "weather")


def weather_markers(parts: dict[str, NodeIR]) -> list[VariantIR]:
    return commands_in_text(parts, WEATHER_PATTERN, only=True)


def background_metadata(parts: dict[str, NodeIR]) -> list[VariantIR]:
    return command_metadata(parts, META_COLOUR_PATTERN, "background")


def background_markers(parts: dict[str, NodeIR]) -> list[VariantIR]:
    return commands_in_text(parts, BACKGROUND_COLOUR_PATTERN, only=True)


def pause_markers(parts: dict[str, NodeIR]) -> list[VariantIR]:
    return commands_in_text(parts, PAUSE_PATTERN, only=True)


def background_effect_markers(parts: dict[str, NodeIR]) -> list[VariantIR]:
    return commands_in_text(parts, BACKGROUND_EFFECTS_PATTERN, only=True)


def sfx_markers(parts: dict[str, NodeIR]) -> list[VariantIR]:
    return commands_in_text(parts, SFX_PATTERN, only=True)


def _asset_missing(value: str | None, folder: str) -> bool:
    """a reference to a file that is not in the site folder"""
    if not value or value.lower() in CLEAR_VALUES:
        return False
    # refuse anything that escapes the site folder
    if "/" in value or "\\" in value or ".." in value:
        return True
    return not (Path("src") / folder / value).is_file()


def missing_images(parts: dict[str, NodeIR]) -> list[VariantIR]:
    return [
        part
        for path in parts.values()
        for part in path.variants
        if _asset_missing(part.image, "images")
    ]


def missing_music(parts: dict[str, NodeIR]) -> list[VariantIR]:
    return [
        part
        for path in parts.values()
        for part in path.variants
        if _asset_missing(part.music, "audio")
    ]


def missing_sfx(parts: dict[str, NodeIR]) -> list[VariantIR]:
    nodes = []
    for path in parts.values():
        for part in path.variants:
            for line in part.text.splitlines():
                for name in SFX_PATTERN.findall(line.strip()):
                    if _asset_missing(name, "audio"):
                        nodes.append(part)
                        break
    return nodes


def unknown_keys(parts: dict[str, NodeIR]) -> list[VariantIR]:
    """misspelled or not-yet-implemented frontmatter keys (design 4.1)"""
    nodes = []
    for path in parts.values():
        for part in path.variants:
            if part.unknown_keys:
                nodes.append(part)
                debug(f"{part.pathname}: " + ", ".join(part.unknown_keys))
    return nodes


def count_range(parts: dict[str, NodeIR]) -> list[VariantIR]:
    """level 3 counts must satisfy 0 <= N <= M <= len(entries) (design 1.4)"""
    nodes = []
    for path in parts.values():
        node_conds = [path.next_if] if path.next_if else []
        for part in path.variants:
            problem = None
            for cond in [*node_conds, *variant_conds(part)]:
                for node in walk_cond(cond):
                    if node.get("op") != "count":
                        continue
                    size = len(node.get("args", []))
                    low = node.get("min", 0)
                    high = node.get("max")
                    # max is null for unbounded groups (any/at_least): only
                    # the min side is checkable against the entry count
                    if low > size or (high is not None and (high > size or low > high)):
                        problem = f"count group {low}..{high} outside 0..{size} entries"
                        break
                if problem:
                    break
            if problem:
                nodes.append(part)
                debug(f"{part.pathname}: {problem}")
    return nodes


def _expansion_errors(parts: dict[str, NodeIR], kind: str) -> list[str]:
    return [
        message
        for path in parts.values()
        for part in path.variants
        for error_kind, message in part.expand_errors
        if error_kind == kind
    ]


def include_missing(parts: dict[str, NodeIR]) -> list[str]:
    """{{...}} pointing at a missing or non-'_' file (design 1.8)"""
    return _expansion_errors(parts, "include_missing")


def macro_params(parts: dict[str, NodeIR]) -> list[str]:
    """macro called with the wrong number of arguments (design 1.8)"""
    return _expansion_errors(parts, "macro_params")


def macro_recursion(parts: dict[str, NodeIR]) -> list[str]:
    """macro cycle or nesting past the depth limit (design 1.8)"""
    return _expansion_errors(parts, "macro_recursion")


# ---------------------------------------------------------------------------
# emit story.json v2 (design 2.1): serialization only, no decisions here
# ---------------------------------------------------------------------------


def node_title(node: NodeIR) -> str | None:
    """frontmatter title, else the first text line (design 1.2)"""
    if node.title:
        return node.title
    for variant in node.variants:
        for line in variant.lines:
            text = "".join(tok["v"] for tok in line if tok["t"] == "lit").strip()
            if text:
                return text
    return None


def emit_variant(variant: VariantIR) -> dict[str, Any]:
    out: dict[str, Any] = {
        "lines": variant.lines,
        "choices": [
            {
                "label": choice.label,
                "to": choice.target,
                "once": choice.once,
                "chance": choice.chance,
                "fallback": choice.fallback,
            }
            | ({"if": choice.cond} if choice.cond else {})
            | ({"effects": choice.effects} if choice.effects else {})
            for choice in variant.choices
        ],
    }
    if variant.effects:
        out["effects"] = variant.effects
    for attr in PRESENTATION_KEYS.values():
        if value := getattr(variant, attr):
            out[attr] = value
    return out


def generate_json(parts: dict[str, NodeIR]) -> dict[str, Any]:
    nodes: dict[str, Any] = {}
    for node_id, node in parts.items():
        entry: dict[str, Any] = {
            "start": node.is_start,
            "end": node.is_end,
            "revisit": node.revisit,
            "title": node_title(node),
            "chapter": node.chapter,
        }
        if node.next:
            entry["next"] = node.next
        if node.next_if:
            entry["nextIf"] = node.next_if
        entry["variants"] = [emit_variant(v) for v in node.variants]
        nodes[node_id] = entry

    ends = [node_id for node_id, node in parts.items() if node.is_end]
    return {
        "version": 2,
        "nodes": nodes,
        "ends": ends,
        "meta": {"endings": [{"id": i, "title": node_title(parts[i])} for i in ends]},
    }


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


def main() -> int:
    sim_walks = 0
    if "--sim" in sys.argv:
        position = sys.argv.index("--sim")
        try:
            sim_walks = int(sys.argv[position + 1])
        except (IndexError, ValueError):
            failure("--sim needs a walk count, e.g. --sim 200")
            return 1
        if sim_walks < 1:
            failure("--sim needs a walk count of at least 1")
            return 1

    print("Searching for story parts")
    try:
        parts = find_parts()
    except ValueError as e:
        failure(str(e))
        return 1

    if not parts:
        failure("Could not locate any story parts")
        return 1
    else:
        print(
            f"Story contains {len(parts)} distinct parts with "
            f"{len(all_nodes(parts))} total variations"
        )

    print("Validating story pathways\n")

    checks = [
        StoryCheck(starting_nodes, "at least one starting part", raise_on_empty=True),
        StoryCheck(ending_nodes, "at least one ending part", raise_on_empty=True),
        StoryCheck(start_end_nodes, "parts that are both start and end points"),
        StoryCheck(empty_nodes, "parts without text"),
        StoryCheck(duplicate_nodes, "parts with duplicate text"),
        StoryCheck(invalid_links, "parts with missing or invalid links", False),
        StoryCheck(dead_ends, "parts with no choices"),
        StoryCheck(fully_conditional, "parts where every choice needs a flag", False),
        StoryCheck(unknown_names, "parts reading a name nothing sets", False),
        StoryCheck(set_but_never_read, "parts setting a name nothing reads", False),
        StoryCheck(satisfiability, "parts with never-true conditions"),
        StoryCheck(
            chance_only_exit, "parts whose only visible exit rolls chance", False
        ),
        StoryCheck(condition_syntax, "parts with unparseable conditions"),
        StoryCheck(conditional_blocks, "parts with unbalanced /if blocks"),
        StoryCheck(continuing_ends, "ending parts contain choices"),
        StoryCheck(noncontinuing_variants, "parts with choices on only some variants"),
        StoryCheck(revisit_variants, "parts are revisitable while others aren't"),
        StoryCheck(single_choice, "parts with a single choice", False),
        StoryCheck(duplicate_choices, "parts with duplicate choice paths", False),
        StoryCheck(unreachable_nodes, "parts that cannot be reached"),
        StoryCheck(escapable_looping_nodes, "parts with looping choices", False),
        StoryCheck(
            inescapable_looping_nodes, "parts with inescapable looping choices", True
        ),
        StoryCheck(abnormal_paths, "parts with very short comparable paths", False),
        StoryCheck(unknown_markers, "parts with unknown markers applied", True),
        StoryCheck(colour_metadata, "parts with valid colour options", True),
        StoryCheck(colour_markers, "parts with valid colour markers", True),
        StoryCheck(pace_metadata, "parts with valid pace options", True),
        StoryCheck(pace_markers, "parts with valid pace markers", True),
        StoryCheck(effect_metadata, "parts with valid effect options", True),
        StoryCheck(effect_markers, "parts with valid effect markers", True),
        StoryCheck(pov_metadata, "parts with valid pov options", True),
        StoryCheck(pov_markers, "parts with valid pov markers", True),
        StoryCheck(message_metadata, "parts with valid message-pov options", True),
        StoryCheck(message_markers, "parts with valid message markers", True),
        StoryCheck(
            message_title_metadata, "parts with valid message-title options", True
        ),
        StoryCheck(
            message_title_markers, "parts with valid message title markers", True
        ),
        StoryCheck(weather_metadata, "parts with valid weather options", True),
        StoryCheck(weather_markers, "parts with valid weather markers", True),
        StoryCheck(background_metadata, "parts with valid background options", True),
        StoryCheck(background_markers, "parts with valid background markers", True),
        StoryCheck(pause_markers, "parts with valid pause markers", True),
        StoryCheck(
            background_effect_markers,
            "parts with valid background effect markers",
            True,
        ),
        StoryCheck(sfx_markers, "parts with valid sfx markers", True),
        StoryCheck(missing_sfx, "parts referencing a missing sound file", True),
        StoryCheck(missing_images, "parts referencing a missing image", True),
        StoryCheck(missing_music, "parts referencing a missing music track", True),
        StoryCheck(unknown_keys, "parts with unknown frontmatter keys"),
        StoryCheck(count_range, "parts with count groups out of range"),
        StoryCheck(include_missing, "parts including a missing or non-'_' file"),
        StoryCheck(macro_params, "parts calling a macro with the wrong arguments"),
        StoryCheck(macro_recursion, "parts with a macro cycle or deep nesting"),
    ]

    func_pad = 0
    for check in checks:
        if (thislen := len(check.function.__name__)) and thislen > func_pad:
            func_pad = thislen

    failures = 0
    warnings = 0
    check_count = len(checks)
    checkpad = len(str(check_count))
    for i, check in enumerate(checks):
        debug(
            msg=str(i + 1).rjust(checkpad)
            + f"/{check_count} Testing {check.function.__name__}"
        )

        text = (
            str(i + 1).rjust(checkpad)
            + f"/{check_count} "
            + check.function.__name__.capitalize().ljust(func_pad)
            + f" - {check.check_type}"
        )
        value = check.function(parts)
        if (not value and check.raise_on_empty) or (value and not check.raise_on_empty):
            if check.required:
                failure(text)
                failures += 1
            else:
                warning(text)
                warnings += 1

            if value:
                pretty_print_paths(value, 4 + checkpad * 2)
        else:
            success(text)

    if failures:
        return 1

    print("\nStory has passed all required steps")

    json = generate_json(parts)
    story_path = Path("src/story.json")
    story_path.write_text(dumps(json, indent=2))
    if sim_walks:
        from simulator import load_artifact, run_sim

        load_artifact(story_path)
        run_sim(sim_walks)
    return 0


if __name__ == "__main__":
    code = main()
    if code:
        print("---")
        failure("Could not generate story, fix and rerun")
    sys.exit(code)
