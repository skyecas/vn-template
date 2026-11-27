"""Loader: story files -> IR (design 3.1)."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .conditions import parse_condition
from .effects import EffectError, parse_effect
from .expand import expand_body
from .frontmatter import parse_markdown
from .ir import PRESENTATION_KEYS, ChoiceIR, NodeIR, VariantIR
from .lexer import lex_body
from .report import debug

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
CHOICE_KEYS = {
    "label",
    "to",
    "if",
    "effects",
    "once",
    "chance",
    "fallback",
    "call",
    "return",
}


def parse_choices(raw: Any, filepath: Path, unknown: list[str]) -> list[ChoiceIR]:
    """choices is a list of {label, to, if, effects, once, chance, fallback, call, return}"""
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
        call = bool(entry.get("call", False))
        returns = bool(entry.get("return", False))
        if not label:
            raise ValueError(f"choice {i + 1} needs a label")
        if call and returns:
            raise ValueError(f"choice {i + 1} cannot be both call and return")
        if call and not target:
            raise ValueError(f"choice {i + 1} call needs a to")
        if not target and not returns:
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
                target=str(target) if target else None,
                file=filepath,
                cond=parse_condition(entry.get("if")),
                effects=effects,
                once=bool(entry.get("once", False)),
                chance=chance,
                fallback=bool(entry.get("fallback", False)),
                call=call,
                return_=returns,
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
