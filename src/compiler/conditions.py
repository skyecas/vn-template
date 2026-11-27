"""Condition grammar: one parser, four levels, AST out (design 1.4)."""

from __future__ import annotations

import re
from typing import Any

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
