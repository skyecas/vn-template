"""Effect grammar: one parser, three spellings (design 1.5)."""

from __future__ import annotations

import re
from typing import Any

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
