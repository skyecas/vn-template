"""Marker patterns and colour tables the lexer and checks share (design 1.5/1.6)."""

from __future__ import annotations

import re
from pathlib import Path

SPEEDS = "fastest|faster|fast|slowest|slower|slow"
PACE_PATTERN = re.compile(rf"/({SPEEDS}|pace \d+\s?(ms|s))", re.IGNORECASE)
META_PACE_PATTERN = re.compile(rf"^({SPEEDS}|\d+\s?(ms|s))$", re.IGNORECASE)


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
