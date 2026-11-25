from __future__ import annotations

import re
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from json import dumps
from pathlib import Path
from typing import Any

from yaml import safe_load

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

POV_PATTERN = re.compile(r"/pov \w+", re.IGNORECASE)
META_POV_PATTERN = re.compile(r"^\w+$")

MESSAGE_PATTERN = re.compile(r"/message(-unsent)? \w+", re.IGNORECASE)
META_MESSAGE_PATTERN = re.compile(r"^\w+$")

MESSAGE_TITLE_PATTERN = re.compile(r"^/message-title ([^/]+)$", re.IGNORECASE)
META_MESSAGE_TITLE_PATTERN = re.compile(r"^.+$")

PAUSE_PATTERN = re.compile(r"^/pause \d+\s?(ms|s)$", re.IGNORECASE)

BACKGROUND_EFFECTS_PATTERN = re.compile(
    r"^/(" + r"focus (?:\d+(\.\d+)?\%|reset)|effect reset" + ")",
    re.IGNORECASE,
)

WEATHER_TYPES = "rain|snow|fog|fireflies|sunny|clear|none"
WEATHER_PATTERN = re.compile(rf"^/({WEATHER_TYPES})$", re.IGNORECASE)
META_WEATHER_PATTERN = re.compile(rf"^({WEATHER_TYPES})$", re.IGNORECASE)

SFX_PATTERN = re.compile(r"^/sfx ([\w.-]+)$", re.IGNORECASE)

# values that mean "turn it off" rather than naming a file
CLEAR_VALUES = {"none", "reset", "clear"}


def debug(part: StoryPart | None = None, msg: str = ""):
    if DEBUG:
        if part:
            print(f" - {part.pathname}: {msg}")
        else:
            print(f" - {msg}")


@dataclass
class StoryParts:
    variants: list[StoryPart]
    is_start: bool = False
    is_end: bool = False

    @property
    def revisit(self) -> bool:
        return all(variant.revisit for variant in self.variants)


@dataclass
class Choice:
    label: str
    target: str
    # flags that must already be set for this choice to appear
    condition: list[str] = field(default_factory=list)


def parse_choices(raw: Any, part: StoryPart | None = None) -> list[Choice]:
    """choices is a list of {label, to, if} entries."""
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

        condition = entry.get("if") or []
        if isinstance(condition, str):
            condition = [condition]
        if not isinstance(condition, list) or not all(
            isinstance(flag, str) for flag in condition
        ):
            raise ValueError(
                f"choice {i + 1}: if must be a flag name or list of flag names"
            )

        choices.append(Choice(str(label), str(target), condition))

    labels = [choice.label for choice in choices]
    if len(labels) != len(set(labels)):
        raise ValueError("choices must have unique labels")

    return choices


@dataclass
class StoryPart:
    text: str
    filepath: Path
    pathname: str
    pace: str | None
    colour: str | None
    effect: str | None
    pov: str | None
    messagepov: str | None
    messagetitle: str | None
    background: str | None
    weather: str | None
    revisit: bool = True
    choices: list[Choice] = field(default_factory=list)
    # flags raised while this part is on screen
    sets: list[str] = field(default_factory=list)
    # background image file under src/images/
    image: str | None = None
    # looping track file under src/audio/
    music: str | None = None


def parse_markdown(content: str) -> tuple[dict[str, Any], str]:
    content = content.strip()
    if not content.startswith("---"):
        return {}, content
    parts = content.split("---", 2)
    if len(parts) < 3:
        raise ValueError("unterminated frontmatter, missing the closing '---'")
    _, meta, body = parts
    return safe_load(meta), body.strip().replace("\\", "/")


def find_parts() -> dict[str, StoryParts]:
    parts: dict[str, StoryParts] = {}
    base = Path("story")
    for f in base.glob("**/*.md"):
        has_variants = len(f.parts) > 2

        pathname = f.parts[-2] if has_variants else f.stem

        try:
            metadata, body = parse_markdown(f.read_text("utf-8"))
        except ValueError as e:
            raise ValueError(f"{f}: {e}") from e
        try:
            choices = parse_choices(metadata.get("choices"))
        except (ValueError, TypeError) as e:
            raise ValueError(f"{f}: {e}") from e

        raw_sets = metadata.get("sets") or []
        if isinstance(raw_sets, str):
            raw_sets = [raw_sets]
        if not isinstance(raw_sets, list) or not all(
            isinstance(flag, str) for flag in raw_sets
        ):
            raise ValueError(f"{f}: sets must be a flag name or list of flag names")

        this_part = StoryPart(
            choices=choices,
            sets=raw_sets,
            text=body,
            filepath=f,
            pathname=pathname,
            pace=metadata.get("pace"),
            colour=metadata.get("colour"),
            effect=metadata.get("effect"),
            pov=metadata.get("pov"),
            revisit=metadata.get("revisit", True),
            messagepov=metadata.get("message-pov"),
            messagetitle=metadata.get("message-title"),
            background=metadata.get("background"),
            weather=metadata.get("weather"),
            image=metadata.get("image"),
            music=metadata.get("music"),
        )

        if pathname not in parts:
            parts[pathname] = StoryParts(variants=[this_part])
        else:
            parts[pathname].variants.append(this_part)

        # any variant can mark the part as a start or an end point
        parts[pathname].is_start = parts[pathname].is_start or metadata.get(
            "start", False
        )
        parts[pathname].is_end = parts[pathname].is_end or metadata.get("end", False)
        debug(msg=f"added {f.name} to {pathname}")

    return parts


def all_nodes(parts: dict[str, StoryParts]) -> list[StoryPart]:
    nodes = []
    for path in parts.values():
        nodes.extend(path.variants)
    return nodes


def starting_nodes(parts: dict[str, StoryParts]) -> list[StoryPart]:
    nodes = []
    for path in parts.values():
        if path.is_start:
            nodes.extend(path.variants)
    return nodes


def ending_nodes(parts: dict[str, StoryParts]) -> list[StoryPart]:
    nodes = []
    for path in parts.values():
        if path.is_end:
            nodes.extend(path.variants)
    return nodes


def start_end_nodes(parts: dict[str, StoryParts]) -> list[StoryPart]:
    nodes = []
    for path in parts.values():
        if path.is_end and path.is_start:
            nodes.extend(path.variants)
    return nodes


def empty_nodes(parts: dict[str, StoryParts]) -> list[StoryPart]:
    nodes = []
    for path in parts.values():
        for part in path.variants:
            if not part.text:
                nodes.append(part)
    return nodes


def duplicate_nodes(parts: dict[str, StoryParts]) -> list[StoryPart]:
    text = []
    nodes = []
    for path in parts.values():
        for part in path.variants:
            if part.text in text:
                nodes.append(part)
            else:
                text.append(part.text)
    return nodes


def invalid_links(parts: dict[str, StoryParts]) -> list[StoryPart]:
    nodes = []
    for path in parts.values():
        if path.is_end:
            continue

        for part in path.variants:
            for choice in part.choices:
                if choice.target not in parts:
                    debug(part, f"{choice.target} was not in {parts.keys()}")
                    nodes.append(part)
                    break
    return nodes


def dead_ends(parts: dict[str, StoryParts]) -> list[StoryPart]:
    nodes = []
    for path in parts.values():
        if not path.is_end:
            for part in path.variants:
                if not part.choices:
                    nodes.append(part)
    return nodes


def fully_conditional(parts: dict[str, StoryParts]) -> list[StoryPart]:
    """every choice needs a flag, so a player missing all of them is stuck"""
    nodes = []
    for path in parts.values():
        if path.is_end:
            continue
        for part in path.variants:
            if part.choices and all(choice.condition for choice in part.choices):
                nodes.append(part)
    return nodes


def unknown_flags(parts: dict[str, StoryParts]) -> list[StoryPart]:
    """choices gated on a flag that no part ever sets"""
    set_flags = {flag for part in all_nodes(parts) for flag in part.sets}
    nodes = []
    for path in parts.values():
        for part in path.variants:
            needed = {flag for choice in part.choices for flag in choice.condition}
            if needed - set_flags:
                nodes.append(part)
    return nodes


def continuing_ends(parts: dict[str, StoryParts]) -> list[StoryPart]:
    nodes = []
    for path in parts.values():
        if path.is_end:
            for part in path.variants:
                if part.choices:
                    nodes.append(part)
    return nodes


def revisit_variants(parts: dict[str, StoryParts]) -> list[StoryPart]:
    nodes = []
    for path in parts.values():
        for part in path.variants:
            if path.revisit and not part.revisit:
                nodes.append(part)
    return nodes


def noncontinuing_variants(parts: dict[str, StoryParts]) -> list[StoryPart]:
    nodes = []
    for path in parts.values():
        variant_choices = any(len(part.choices) > 0 for part in path.variants)
        for part in path.variants:
            if variant_choices and not part.choices:
                nodes.append(part)
    return nodes


def single_choice(parts: dict[str, StoryParts]) -> list[StoryPart]:
    nodes = []
    for path in parts.values():
        if not path.is_end:
            for part in path.variants:
                if len(part.choices) == 1:
                    nodes.append(part)
    return nodes


def duplicate_choices(parts: dict[str, StoryParts]) -> list[StoryPart]:
    nodes = []
    for path in parts.values():
        if not path.is_end:
            for part in path.variants:
                if len(part.choices) != len({choice.target for choice in part.choices}):
                    nodes.append(part)
    return nodes


def unreachable_nodes(parts: dict[str, StoryParts]) -> list[StoryPart]:
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
        if parts[node.pathname].is_end:
            continue

        for choice in node.choices:
            if choice.target in parts:
                stack.extend(parts[choice.target].variants)
    return [node for node in every_node if node.pathname not in visited]


def looping_nodes(parts: dict[str, StoryParts]) -> list[list[StoryPart]]:
    loops: list[list[StoryPart]] = []
    # dense menus make the walkable paths explode combinatorially; stop after
    # a generous budget so validation always finishes (small stories finish
    # long before the cap, so their output is unaffected)
    budget = 50_000

    def depth_search(node: StoryPart, ancestors: list[StoryPart] | None = None) -> None:
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

    def canonical_looping(loop: list[StoryPart]) -> tuple[list[StoryPart], list[str]]:
        names = [part.pathname for part in loop]
        # the loop closes on itself, trim everything before the first repeat
        start = names.index(names[-1])

        loop = loop[start:]
        names = names[start:]

        # rotate so every entry point of the same loop collapses to one form
        rotations = [tuple(names[i:] + names[:i]) for i in range(len(names))]
        best = rotations.index(min(rotations))
        return loop[best:] + loop[:best], names[best:] + names[:best]

    unique: list[list[StoryPart]] = []
    unique_name: list[list[str]] = []
    for loop in loops:
        this_loop, this_name = canonical_looping(loop)
        if this_name not in unique_name:
            unique.append(this_loop)
            unique_name.append(this_name)

    return unique


def _nodes_reaching_end(parts: dict[str, StoryParts]) -> set[str]:
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


def can_escape_loop(parts: dict[str, StoryParts], loop: list[StoryPart]) -> bool:
    """can the story reach an ending without going back around this loop"""
    # walking every path from every loop node re-exploded on dense graphs;
    # reachability is direction-independent, so one reverse pass answers all
    # of the loops at once
    reaching = _nodes_reaching_end(parts)
    return any(node.pathname in reaching for node in loop)


def escapable_looping_nodes(parts: dict[str, StoryParts]) -> list[list[StoryPart]]:
    return [loop for loop in looping_nodes(parts) if can_escape_loop(parts, loop)]


def inescapable_looping_nodes(parts: dict[str, StoryParts]) -> list[list[StoryPart]]:
    return [loop for loop in looping_nodes(parts) if not can_escape_loop(parts, loop)]


def abnormal_paths(parts: dict[str, StoryParts]) -> list[list[StoryPart]]:
    all_paths: list[list[StoryPart]] = []
    visited_paths: set[tuple[str]] = set()
    # same budget idea as looping_nodes: generous enough that small stories
    # enumerate completely, finite so a dense graph cannot hang the build
    budget = 50_000

    def traverse(node: StoryPart, path: list[StoryPart] | None = None):
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


def unknown_markers(parts: dict[str, StoryParts]) -> list[StoryPart]:
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
                ]:
                    stripped = regex.sub("", stripped)

                if markers := re.findall(r"(?:^|[^`\w])(/\w[\w.-]*)", stripped):
                    nodes.append(part)
                    debug(part, "Unknown markers in text: " + ", ".join(markers))

    return nodes


def command_metadata(
    parts: dict[str, StoryParts],
    regex: re.Pattern[str] = META_COLOUR_PATTERN,
    property: str = "colour",
) -> list[StoryPart]:
    nodes = []

    for path in parts.values():
        for part in path.variants:
            match = getattr(part, property, None)
            if not match:
                continue
            if not isinstance(match, str) or not regex.match(match):
                debug(part, "has invalid metadata pattern")
                nodes.append(part)

    return nodes


def commands_in_text(
    parts: dict[str, StoryParts],
    regex: re.Pattern[str] = META_COLOUR_PATTERN,
    allow_multiple: bool = False,
    only: bool = False,
) -> list[StoryPart]:
    nodes = []

    for path in parts.values():
        for part in path.variants:
            for line in part.text.splitlines():
                stripped = line.strip()
                if not stripped:
                    continue

                markers = regex.findall(stripped)
                if not allow_multiple and len(markers) > 1:
                    nodes.append(part)
                    debug(part, "has more than one marker")
                    break

                if markers and not stripped.startswith("/"):
                    nodes.append(part)
                    debug(part, "has markers not at the start of the text")
                    break

                if markers and only and regex.sub("", stripped).strip():
                    nodes.append(part)
                    debug(part, "has other markers despite being an exclusive line")
                    break

    return nodes


def colour_metadata(parts: dict[str, StoryParts]) -> list[StoryPart]:
    return command_metadata(parts, META_COLOUR_PATTERN, "colour")


def colour_markers(parts: dict[str, StoryParts]) -> list[StoryPart]:
    return commands_in_text(parts, COLOUR_PATTERN)


def pace_metadata(parts: dict[str, StoryParts]) -> list[StoryPart]:
    return command_metadata(parts, META_PACE_PATTERN, "pace")


def pace_markers(parts: dict[str, StoryParts]) -> list[StoryPart]:
    return commands_in_text(parts, PACE_PATTERN)


def effect_metadata(parts: dict[str, StoryParts]) -> list[StoryPart]:
    return command_metadata(parts, META_EFFECT_PATTERN, "effect")


def effect_markers(parts: dict[str, StoryParts]) -> list[StoryPart]:
    return commands_in_text(parts, EFFECT_PATTERN, allow_multiple=True)


def pov_metadata(parts: dict[str, StoryParts]) -> list[StoryPart]:
    return command_metadata(parts, META_POV_PATTERN, "pov")


def pov_markers(parts: dict[str, StoryParts]) -> list[StoryPart]:
    return commands_in_text(parts, POV_PATTERN)


def message_metadata(parts: dict[str, StoryParts]) -> list[StoryPart]:
    return command_metadata(parts, META_MESSAGE_PATTERN, "messagepov")


def message_markers(parts: dict[str, StoryParts]) -> list[StoryPart]:
    return commands_in_text(parts, MESSAGE_PATTERN)


def message_title_metadata(parts: dict[str, StoryParts]) -> list[StoryPart]:
    return command_metadata(parts, META_MESSAGE_TITLE_PATTERN, "message-title")


def message_title_markers(parts: dict[str, StoryParts]) -> list[StoryPart]:
    return commands_in_text(parts, MESSAGE_TITLE_PATTERN, only=True)


def weather_metadata(parts: dict[str, StoryParts]) -> list[StoryPart]:
    return command_metadata(parts, META_WEATHER_PATTERN, "weather")


def weather_markers(parts: dict[str, StoryParts]) -> list[StoryPart]:
    return commands_in_text(parts, WEATHER_PATTERN, only=True)


def background_metadata(parts: dict[str, StoryParts]) -> list[StoryPart]:
    return command_metadata(parts, META_COLOUR_PATTERN, "background")


def background_markers(parts: dict[str, StoryParts]) -> list[StoryPart]:
    return commands_in_text(parts, BACKGROUND_COLOUR_PATTERN, only=True)


def pause_markers(parts: dict[str, StoryParts]) -> list[StoryPart]:
    return commands_in_text(parts, PAUSE_PATTERN, only=True)


def background_effect_markers(parts: dict[str, StoryParts]) -> list[StoryPart]:
    return commands_in_text(parts, BACKGROUND_EFFECTS_PATTERN, only=True)


def sfx_markers(parts: dict[str, StoryParts]) -> list[StoryPart]:
    return commands_in_text(parts, SFX_PATTERN, only=True)


def _asset_missing(value: str | None, folder: str) -> bool:
    """a reference to a file that is not in the site folder"""
    if not value or value.lower() in CLEAR_VALUES:
        return False
    # refuse anything that escapes the site folder
    if "/" in value or "\\" in value or ".." in value:
        return True
    return not (Path("src") / folder / value).is_file()


def missing_images(parts: dict[str, StoryParts]) -> list[StoryPart]:
    return [
        part
        for path in parts.values()
        for part in path.variants
        if _asset_missing(part.image, "images")
    ]


def missing_music(parts: dict[str, StoryParts]) -> list[StoryPart]:
    return [
        part
        for path in parts.values()
        for part in path.variants
        if _asset_missing(part.music, "audio")
    ]


def missing_sfx(parts: dict[str, StoryParts]) -> list[StoryPart]:
    nodes = []
    for path in parts.values():
        for part in path.variants:
            for line in part.text.splitlines():
                for name in SFX_PATTERN.findall(line.strip()):
                    if _asset_missing(name, "audio"):
                        nodes.append(part)
                        break
    return nodes


def generate_json(parts: dict[str, StoryParts]) -> dict[str, Any]:
    output = {}
    for pathname, part in parts.items():
        output[pathname] = {
            "start": part.is_start,
            "end": part.is_end,
            "revisit": part.revisit,
            "variants": [
                {
                    "choices": [
                        {"label": c.label, "to": c.target}
                        | ({"if": c.condition} if c.condition else {})
                        for c in v.choices
                    ],
                    "text": v.text,
                }
                | ({"sets": v.sets} if v.sets else {})
                | ({"image": v.image} if v.image else {})
                | ({"music": v.music} if v.music else {})
                | ({"pace": v.pace} if v.pace else {})
                | ({"colour": v.colour} if v.colour else {})
                | ({"effect": v.effect} if v.effect else {})
                | ({"pov": v.pov} if v.pov else {})
                | ({"messagepov": v.messagepov} if v.messagepov else {})
                | ({"messagetitle": v.messagetitle} if v.messagetitle else {})
                | ({"weather": v.weather} if v.weather else {})
                | ({"background": v.background} if v.background else {})
                for v in part.variants
            ],
        }
    return output


def pretty_print_paths(
    value: Any, indent: int = 0, separators: list[str] | None = None, limit: int = 8
):
    """
    Nicely prints StoryPart(s) or nested paths with custom separators per depth.
    """
    if separators is None:
        separators = [", ", "; ", " - "]

    def format_paths(val: Any, depth: int = 0) -> str:
        sep = separators[depth] if depth < len(separators) else separators[-1]

        if isinstance(val, StoryPart):
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
    function: Callable[[dict[str, StoryParts]], list[StoryPart] | list[list[StoryPart]]]
    check_type: str
    required: bool = True
    raise_on_empty: bool = False


def main() -> int:
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
        StoryCheck(unknown_flags, "parts gating on a flag nothing sets", False),
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
    return 0


if __name__ == "__main__":
    code = main()
    if code:
        print("---")
        failure("Could not generate story, fix and rerun")
    sys.exit(code)
