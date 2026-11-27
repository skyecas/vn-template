"""Shared runtime simulator for story.json v2 (docs/design.md 4.2).

Mirrors src/script.js line for line: same seeded rng stream, same condition
and effect semantics, same transition order, so `--sim N` and `play.py`
reproduce exactly what the browser does. The purity rule holds here too:
apply_transition is the only writer of state.
"""

from __future__ import annotations

import copy
import json
import math
import random
import re
from collections import Counter
from pathlib import Path
from typing import Any

from yaml import safe_load

try:
    from PIL import ImageColor
except ImportError:  # only the cosmetic pov-colour contrast filter needs PIL
    ImageColor = None  # type: ignore[assignment]

# set by load_artifact: the compiled story, the site config, the colour list
story: dict[str, Any] = {}
config: dict[str, Any] = {}
colours: list[str] = []

# whole-line markers run a command and never draw (script.js EXCLUSIVE_MARKERS)
EXCLUSIVE_MARKERS = {
    "pause",
    "focus",
    "effectReset",
    "background",
    "weather",
    "sfx",
    "messageTitle",
}


def load_artifact(story_path: str | Path = "src/story.json") -> None:
    """load story.json + config.yaml + named_colours; run from the repo root.

    Updates the module dicts in place: `from simulator import story` stays
    valid across loads.
    """
    loaded = json.loads(Path(story_path).read_text())
    story.clear()
    story.update(loaded)
    config.clear()
    config.update(safe_load(Path("config.yaml").read_text()) or {})
    colours[:] = [
        line
        for line in Path("src/named_colours").read_text().lower().splitlines()
        if line
    ]


def empty_state() -> dict[str, Any]:
    return {
        "v": 2,
        "path": [],
        "variants": [],
        "vars": {},
        "visits": {},
        "used": [],
        "rng": {"seed": 0, "n": 0},
        "call": [],
        "resume": [],
        "povColours": {},
    }


# ---- seeded rng + hashing (script.js) --------------------------------------


def new_seed() -> int:
    return random.randrange(0x7FFFFFFF)


def js_string(value: Any) -> str:
    """JS String(): booleans lowercase, integral floats drop the .0"""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def hash32(*parts: Any) -> int:
    """FNV-1a over each part's UTF-16 code units, 0xff separator per part"""
    h = 0x811C9DC5
    for part in parts:
        text = js_string(part)
        units = text.encode("utf-16-le", errors="surrogatepass")
        for i in range(0, len(units), 2):
            h ^= units[i] | (units[i + 1] << 8)
            h = (h * 0x01000193) & 0xFFFFFFFF
        h ^= 0xFF
        h = (h * 0x01000193) & 0xFFFFFFFF
    return h


def rng_value(state: dict[str, Any]) -> float:
    state["rng"]["n"] += 1
    n = state["rng"]["n"]
    x = (state["rng"]["seed"] ^ ((n * 0x9E3779B9) & 0xFFFFFFFF)) & 0xFFFFFFFF
    x = ((x ^ (x >> 16)) * 0x85EBCA6B) & 0xFFFFFFFF
    x = ((x ^ (x >> 13)) * 0xC2B2AE35) & 0xFFFFFFFF
    x = (x ^ (x >> 16)) & 0xFFFFFFFF
    return x / 4294967296


def shuffle_order(seed: int, node_id: str, line_index: int, length: int) -> list[int]:
    return sorted(range(length), key=lambda i: hash32(seed, node_id, line_index, i))


# ---- conditions (design 1.4) -----------------------------------------------


def js_number(value: Any) -> Any:
    """JS ToNumber; None stands for NaN"""
    if isinstance(value, bool):
        return 1 if value else 0
    if isinstance(value, (int, float)):
        return value
    if isinstance(value, str):
        text = value.strip()
        if text == "":
            return 0.0
        if "_" in text:
            return None
        if text[:2].lower() in {"0x", "+0x", "-0x"}:
            try:
                return int(text, 16)
            except ValueError:
                return None
        try:
            number = float(text)
        except ValueError:
            return None
        return None if math.isnan(number) else number
    return None


def js_strict_eq(lhs: Any, rhs: Any) -> bool:
    """JS ===: one number type, no bool/number mixing"""
    lhs_num = isinstance(lhs, (int, float)) and not isinstance(lhs, bool)
    rhs_num = isinstance(rhs, (int, float)) and not isinstance(rhs, bool)
    if lhs_num and rhs_num:
        return lhs == rhs
    if isinstance(lhs, bool) and isinstance(rhs, bool):
        return lhs == rhs
    if isinstance(lhs, str) and isinstance(rhs, str):
        return lhs == rhs
    return False


def js_compare(op: str, lhs: Any, rhs: Any) -> bool:
    """JS relational/equality primitives: strings compare by UTF-16 unit,
    everything else coerces to number, NaN fails every relational test"""
    if op in {">=", "<=", ">", "<"}:
        if isinstance(lhs, str) and isinstance(rhs, str):
            left = lhs.encode("utf-16-le", errors="surrogatepass")
            right = rhs.encode("utf-16-le", errors="surrogatepass")
            ordered = (left > right) - (left < right)
        else:
            left_num = js_number(lhs)
            right_num = js_number(rhs)
            if left_num is None or right_num is None:
                return False
            ordered = (left_num > right_num) - (left_num < right_num)
        return {
            ">=": ordered >= 0,
            "<=": ordered <= 0,
            ">": ordered > 0,
            "<": ordered < 0,
        }[op]
    if op == "==":
        return js_strict_eq(lhs, rhs)
    if op == "!=":
        return not js_strict_eq(lhs, rhs)
    return False


def cond_side(side: Any, state: dict[str, Any]) -> Any:
    if isinstance(side, bool):
        return side
    if isinstance(side, (int, float)):
        return side
    if isinstance(side, str):
        return state["vars"].get(side, 0)
    if isinstance(side, dict) and "str" in side:
        return side["str"]
    return eval_cond(side, state)


def eval_cond(cond: Any, state: dict[str, Any]) -> Any:
    if not cond:
        return True
    op = cond.get("op")
    if op == "truth":
        return bool(state["vars"].get(cond["name"]))
    if op == "not":
        return not eval_cond(cond["arg"], state)
    if op == "and":
        return all(eval_cond(arg, state) for arg in cond["args"])
    if op == "or":
        return any(eval_cond(arg, state) for arg in cond["args"])
    if op == "cmp":
        return js_compare(
            cond["cmp"],
            cond_side(cond["lhs"], state),
            cond_side(cond["rhs"], state),
        )
    if op == "visits":
        return state["visits"].get(cond["id"], 0)
    if op == "count":
        hits = sum(1 for arg in cond["args"] if eval_cond(arg, state))
        return hits >= cond["min"] and (cond["max"] is None or hits <= cond["max"])
    return False  # "bad" never renders: condition_syntax fails the build


# ---- effects (design 1.5): the only writer of state ------------------------


def apply_effect(effect: dict[str, Any], state: dict[str, Any]) -> None:
    op = effect["op"]
    if op == "set":
        state["vars"][effect["name"]] = True
    elif op == "clear":
        state["vars"].pop(effect["name"], None)
    elif op == "assign":
        state["vars"][effect["name"]] = effect["val"]
    elif op == "add":
        current = js_number(state["vars"].get(effect["name"]))
        if current is None or current == 0:
            current = 0
        total = current + effect["val"]
        if isinstance(total, float) and total.is_integer():
            total = int(total)
        state["vars"][effect["name"]] = total
    elif op == "roll":
        count, sides, modifier = effect["dice"]
        total = modifier
        for _ in range(count):
            total += 1 + int(rng_value(state) * sides)
        state["vars"][effect["var"]] = total
    # unlock: achievements arrive with the meta work (P3)


# ---- pov colours -----------------------------------------------------------


def pov_key(pov: str | None, existing: dict[str, str]) -> str | None:
    if not pov or not config.get("povCaseInsensitive"):
        return pov
    for key in existing:
        if key.lower() == pov.lower():
            return key
    return pov


def parse_color(color: str) -> list[int]:
    """RGB the browser's canvas would serialise this colour to"""
    text = color.strip()
    if text.startswith("#"):
        if len(text) == 4:
            return [int(text[i] * 2, 16) for i in (1, 2, 3)]
        return [int(text[i : i + 2], 16) for i in (1, 3, 5)]
    if re.fullmatch(r"rgba?\([^)]*\)", text):
        digits = re.findall(r"\d+", text)
        if digits:
            return [int(d) for d in digits[:3]]
    # named: CSS keywords only (canvas serialises those to hex); anything the
    # browser would reject leaves fillStyle at its #000000 default
    if text.isalpha() and ImageColor is not None:
        try:
            return list(ImageColor.getrgb(text))
        except ValueError:
            pass
    return [0, 0, 0]


def contrast(fg: str, bg: str) -> float:
    def brightness(rgb: list[int]) -> float:
        red, green, blue = rgb
        return (red * 299 + green * 587 + blue * 114) / 1000

    return abs(brightness(parse_color(fg)) - brightness(parse_color(bg)))


def assign_pov_colour(state: dict[str, Any], pov: str, partpov: str | None) -> None:
    if not pov:
        return
    key = pov_key(pov, state["povColours"])
    if state["povColours"].get(key):
        return

    used = list(state["povColours"].values())
    pool = [colour for colour in colours if colour not in used]
    if not pool:
        pool = colours

    partkey = pov_key(partpov, state["povColours"]) if partpov else None
    if partkey and state["povColours"].get(partkey) and ImageColor is not None:
        contrasting = [
            colour
            for colour in pool
            if contrast(colour, state["povColours"][partkey]) >= 10
        ]
        if contrasting:
            pool = contrasting

    state["povColours"][key] = pool[int(rng_value(state) * len(pool))]


# ---- alt branches (design 1.6) ---------------------------------------------


def pick_alt_branch(
    token: dict[str, Any],
    state: dict[str, Any],
    node_id: str,
    visit_number: int,
    line_index: int,
) -> list[Any]:
    branches = token["branches"]
    if not branches:
        return []
    if token["mode"] == "cycle":
        index = visit_number % len(branches)
    elif token["mode"] == "shuffle":
        order = shuffle_order(state["rng"]["seed"], node_id, line_index, len(branches))
        index = order[visit_number % len(branches)]
    else:
        index = min(visit_number, len(branches) - 1)
    return branches[index] or []


def walk_tokens(
    tokens: list[dict[str, Any]],
    state: dict[str, Any],
    node_id: str,
    visit_number: int,
    line_index: int,
    on_token: Any,
) -> None:
    for token in tokens:
        kind = token.get("t")
        if kind == "mk":
            on_token(token)
        elif kind == "fx":
            apply_effect(token, state)
        elif kind == "if":
            branch = token["then"] if eval_cond(token["cond"], state) else token["else"]
            for entry in branch:
                walk_tokens(entry, state, node_id, visit_number, line_index, on_token)
        elif kind == "alt":
            branch = pick_alt_branch(token, state, node_id, visit_number, line_index)
            for entry in branch:
                walk_tokens(entry, state, node_id, visit_number, line_index, on_token)
        # lit and var carry no markers


def walk_line_list(
    lines: list[Any],
    state: dict[str, Any],
    node_id: str,
    visit_number: int,
    on_token: Any,
) -> None:
    for line_index, entry in enumerate(lines):
        if len(entry) == 1 and entry[0].get("t") == "if":
            branch = (
                entry[0]["then"]
                if eval_cond(entry[0]["cond"], state)
                else entry[0]["else"]
            )
            walk_line_list(branch, state, node_id, visit_number, on_token)
        else:
            walk_tokens(entry, state, node_id, visit_number, line_index, on_token)


def assign_visible_povs(
    state: dict[str, Any],
    node: dict[str, Any],
    variant: dict[str, Any],
    node_id: str,
) -> None:
    seen: set[str] = set()

    def consider(pov: str | None) -> None:
        if not pov or pov in seen:
            return
        seen.add(pov)
        assign_pov_colour(state, pov, variant.get("pov"))

    consider(variant.get("pov"))
    consider(variant.get("messagepov"))
    visit_number = state["visits"].get(node_id, 0)  # pre-increment: this visit
    walk_line_list(
        variant["lines"],
        state,
        node_id,
        visit_number,
        lambda token: (
            consider(token["v"])
            if token.get("k") in {"pov", "message", "messageUnsent"}
            else None
        ),
    )


# ---- flow (design 2.3) -----------------------------------------------------


def variant_index_for(state: dict[str, Any], node: dict[str, Any], index: int) -> int:
    stored = state["variants"][index] if 0 <= index < len(state["variants"]) else None
    if (
        isinstance(stored, int)
        and not isinstance(stored, bool)
        and 0 <= stored < len(node["variants"])
    ):
        return stored
    return 0


def used_key(node_id: str, variant_index: int, choice_index: int) -> str:
    return f"{node_id}:{variant_index}:{choice_index}"


def chance_offered(
    state: dict[str, Any], node_id: str, choice_index: int, chance: Any
) -> bool:
    if chance is None or chance >= 100:
        return True
    if chance <= 0:
        return False
    visit = state["visits"].get(node_id, 0)
    return hash32(state["rng"]["seed"], node_id, choice_index, visit) % 100 < chance


def live_next(state: dict[str, Any], node: dict[str, Any]) -> bool:
    return bool(
        node.get("next")
        and not node.get("end")
        and (not node.get("nextIf") or eval_cond(node["nextIf"], state))
    )


def node_variant(node: dict[str, Any], index: Any) -> dict[str, Any]:
    variants = node.get("variants") or []
    if (
        isinstance(index, int)
        and not isinstance(index, bool)
        and 0 <= index < len(variants)
    ):
        return variants[index]
    return variants[0] if variants else {"lines": [], "choices": []}


def visible_choices(
    state: dict[str, Any],
    node: dict[str, Any],
    variant: dict[str, Any],
    path: list[str],
    index: int,
) -> list[tuple[int, dict[str, Any]]]:
    """(original index, choice) for every choice the reader would see"""
    if live_next(state, node):
        return []
    node_id = path[index]
    variant_index = variant_index_for(state, node, index)
    visible: list[tuple[int, dict[str, Any]]] = []
    for choice_index, choice in enumerate(variant.get("choices") or []):
        if (
            choice.get("once")
            and used_key(node_id, variant_index, choice_index) in state["used"]
        ):
            continue
        if choice.get("if") and not eval_cond(choice["if"], state):
            continue
        if not chance_offered(state, node_id, choice_index, choice.get("chance")):
            continue
        target = story["nodes"].get(choice["to"])
        if target is None:
            visible.append((choice_index, choice))  # unimplemented: show it
            continue
        already_visited = choice["to"] in path[: index + 1]
        if not already_visited or target.get("revisit"):
            visible.append((choice_index, choice))
    return visible


def enter_node(state: dict[str, Any], node_id: str) -> None:
    state["path"].append(node_id)
    state["resume"].append(False)  # fresh entries are never resume steps
    node = story["nodes"].get(node_id)
    if node is None:
        state["variants"].append(
            None
        )  # the validator warns; render shows a placeholder
        return

    pick = 0
    if len(node["variants"]) > 1:
        pick = int(rng_value(state) * len(node["variants"]))
    state["variants"].append(pick)

    variant = node["variants"][pick]
    for effect in variant.get("effects") or []:
        apply_effect(effect, state)

    assign_visible_povs(state, node, variant, node_id)

    state["visits"][node_id] = state["visits"].get(node_id, 0) + 1


def apply_transition(
    state: dict[str, Any], action: dict[str, Any]
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """the one place state changes: pure with respect to the caller's blob"""
    nxt = copy.deepcopy(state)
    if not isinstance(nxt.get("resume"), list):  # a save from before tunnels
        nxt["resume"] = [False] * len(nxt["path"])
    steps: list[dict[str, Any]] = []

    def enter(node_id: str) -> None:
        enter_node(nxt, node_id)
        steps.append(
            {
                "index": len(nxt["path"]) - 1,
                "nodeId": node_id,
                "state": copy.deepcopy(nxt),
            }
        )

    def resume_call(record: dict[str, Any]) -> None:
        """the caller reappears with its choices only (design 1.9)"""
        nxt["path"].append(record["id"])
        nxt["variants"].append(record.get("variant"))
        nxt["resume"].append(True)
        steps.append(
            {
                "index": len(nxt["path"]) - 1,
                "nodeId": record["id"],
                "state": copy.deepcopy(nxt),
            }
        )

    kind = action.get("type")
    if kind == "start":
        nxt["path"] = []
        nxt["variants"] = []
        nxt["vars"] = {}
        nxt["visits"] = {}
        nxt["used"] = []
        nxt["call"] = []
        nxt["resume"] = []
        nxt["povColours"] = dict(config.get("povColours") or {})
        seed = action.get("seed")
        nxt["rng"] = {
            "seed": seed if seed is not None else new_seed(),
            "n": 0,
        }
        starts = [
            node_id for node_id, node in story["nodes"].items() if node.get("start")
        ]
        if not starts:
            raise SystemExit("No starting story nodes defined")
        # a replay can name the start node; a fresh run picks at random
        node_id = action.get("node") or starts[int(random.random() * len(starts))]
        enter(node_id)
        return nxt, steps

    if kind == "restart":
        return apply_transition(empty_state(), {"type": "start"})

    if kind in {"choice", "advance"}:
        if not nxt["path"]:
            return nxt, steps
        node_id = nxt["path"][-1]
        node = story["nodes"].get(node_id)
        if node is None:
            return nxt, steps
        variant = node_variant(node, nxt["variants"][-1])

        # a terminator inside a tunnel pops back to the caller instead of
        # offering restart (design 1.9)
        if kind == "advance" and node.get("end") and nxt["call"]:
            resume_call(nxt["call"].pop())
            return nxt, steps

        # next is unconditional: it wins over any choices on the node
        if kind == "advance" and live_next(state, node):
            enter(node["next"])
            return nxt, steps

        visible = visible_choices(nxt, node, variant, nxt["path"], len(nxt["path"]) - 1)
        choice: dict[str, Any] | None = None
        choice_index = -1
        if kind == "advance":
            # a lone visible choice follows itself; when only fallbacks are
            # visible the first one is taken (design 1.3)
            real = [
                candidate for _, candidate in visible if not candidate.get("fallback")
            ]
            if not real and visible or len(visible) == 1:
                choice_index, choice = visible[0]
        else:
            index = action.get("index")
            if isinstance(index, int) and 0 <= index < len(visible):
                choice_index, choice = visible[index]
        if choice is None:
            return nxt, steps

        # consume before effects, per the transition order (design 2.3)
        if choice.get("once"):
            key = used_key(
                node_id,
                variant_index_for(nxt, node, len(nxt["path"]) - 1),
                choice_index,
            )
            if key not in nxt["used"]:
                nxt["used"].append(key)
        for effect in choice.get("effects") or []:
            apply_effect(effect, nxt)
        if choice.get("return"):
            # effects ran first; an empty stack goes nowhere (design 1.9)
            if not nxt["call"]:
                return nxt, steps
            record = nxt["call"].pop()
            if choice.get("to"):
                enter(choice["to"])
            else:
                resume_call(record)
            return nxt, steps
        if choice.get("call"):
            # the record keeps the caller's id and picked variant (design 1.9)
            nxt["call"].append({"id": node_id, "variant": nxt["variants"][-1]})
        enter(choice["to"])
        return nxt, steps

    return nxt, steps


def compute_step_states(target: dict[str, Any]) -> list[dict[str, Any]]:
    """rebuild the state after every step of a save: same seed, same choices"""
    if not target.get("path"):
        return []
    states: list[dict[str, Any]] = []
    current, _ = apply_transition(
        empty_state(),
        {
            "type": "start",
            "node": target["path"][0],
            "seed": target["rng"]["seed"],
        },
    )
    states.append(current)

    for i in range(1, len(target["path"])):
        prev_id = current["path"][-1]
        node = story["nodes"].get(prev_id)
        stack = current["call"][-1] if current.get("call") else None
        result = None
        if node and node.get("end") and stack and stack["id"] == target["path"][i]:
            # a pop: advancing the terminator resumes the caller (design 1.9)
            result = apply_transition(current, {"type": "advance"})
        elif node and live_next(current, node) and node["next"] == target["path"][i]:
            result = apply_transition(current, {"type": "advance"})
        elif node:
            variant = node_variant(node, current["variants"][-1])
            visible = visible_choices(
                current, node, variant, current["path"], len(current["path"]) - 1
            )
            # first visible choice leading to the recorded target; choice
            # effects are identical across same-target choices (design 1.3)
            index = next(
                (
                    position
                    for position, (_, choice) in enumerate(visible)
                    if choice["to"] == target["path"][i]
                ),
                -1,
            )
            if index >= 0:
                result = apply_transition(current, {"type": "choice", "index": index})
            else:
                # a return choice pops to the caller without naming a target
                ret = next(
                    (
                        position
                        for position, (_, choice) in enumerate(visible)
                        if choice.get("return") and not choice.get("to")
                    ),
                    -1,
                )
                if ret >= 0 and stack and stack["id"] == target["path"][i]:
                    result = apply_transition(current, {"type": "choice", "index": ret})
        if not result or not result[1]:
            break  # stale link: render as far as it still makes sense
        current = result[0]
        states.append(current)
    return states


# ---- display (mirrors renderLineList / renderLineTokens for play.py) -------


def display_lines(
    state: dict[str, Any],
    node: dict[str, Any],
    variant: dict[str, Any],
    node_id: str,
) -> list[tuple[str | None, str]]:
    """visible (speaker, text) lines exactly as the browser would draw them"""
    lines_out: list[tuple[str | None, str]] = []
    partpov = variant.get("pov")
    # pre-increment visit number, matching the walk done while entering
    visit_number = max(0, state["visits"].get(node_id, 1) - 1)

    def render_entry(entry: list[dict[str, Any]], line_index: int) -> None:
        if (
            len(entry) == 1
            and entry[0].get("t") == "mk"
            and entry[0].get("k") in EXCLUSIVE_MARKERS
        ):
            return
        if len(entry) == 1 and entry[0].get("t") == "fx":
            return
        text = ""
        pov: str | None = None
        message: str | None = None
        unsent: str | None = None

        def collect(tokens: list[dict[str, Any]]) -> None:
            nonlocal text, pov, message, unsent
            for token in tokens:
                kind = token.get("t")
                if kind == "lit":
                    text += token["v"]
                elif kind == "var":
                    name = token["name"]
                    # unknown names stay visible as {name}
                    text += (
                        js_string(state["vars"][name])
                        if name in state["vars"]
                        else "{" + name + "}"
                    )
                elif kind == "if":
                    collect(
                        token["then"]
                        if eval_cond(token["cond"], state)
                        else token["else"]
                    )
                elif kind == "alt":
                    for sub_entry in pick_alt_branch(
                        token, state, node_id, visit_number, line_index
                    ):
                        collect(sub_entry)
                elif kind == "mk":
                    key = token.get("k")
                    if key == "pov" and pov is None:
                        pov = token["v"]
                    elif key == "message" and message is None:
                        message = token["v"]
                    elif key == "messageUnsent" and unsent is None:
                        unsent = token["v"]

        collect(entry)
        if text:
            lines_out.append((pov or message or unsent or partpov, text))

    def render_line_list(entries: list[Any]) -> None:
        for line_index, entry in enumerate(entries):
            if len(entry) == 1 and entry[0].get("t") == "if":
                branch = (
                    entry[0]["then"]
                    if eval_cond(entry[0]["cond"], state)
                    else entry[0]["else"]
                )
                render_line_list(branch)
            else:
                render_entry(entry, line_index)

    render_line_list(variant.get("lines") or [])
    return lines_out


# ---- random walks (design 4.2: --sim N) ------------------------------------


def run_sim(walks: int, max_steps: int = 300) -> None:
    """seeded random walks over the compiled artifact"""
    starts = [node_id for node_id, node in story["nodes"].items() if node.get("start")]
    if not starts:
        raise SystemExit("No starting story nodes defined")

    endings: Counter[str] = Counter()
    stuck: Counter[str] = Counter()
    heat: Counter[tuple[str, str]] = Counter()
    reached: set[str] = set()
    capped = 0

    for walk in range(walks):
        rng = random.Random(walk)  # the walker's own dice, not the story's
        state, _ = apply_transition(
            empty_state(),
            {
                "type": "start",
                "node": starts[int(rng.random() * len(starts))],
                "seed": walk,
            },
        )
        reached.add(state["path"][-1])
        outcome: tuple[str, str] | None = None
        for _ in range(max_steps):
            node_id = state["path"][-1]
            node = story["nodes"].get(node_id)
            if node is None:
                outcome = ("stuck", node_id)
                break
            if node.get("end") and not state["call"]:
                outcome = ("end", node_id)
                break
            variant = node_variant(node, state["variants"][-1])
            visible = visible_choices(
                state, node, variant, state["path"], len(state["path"]) - 1
            )
            real = [
                candidate for _, candidate in visible if not candidate.get("fallback")
            ]
            if live_next(state, node):
                action: dict[str, Any] = {"type": "advance"}
            elif node.get("end") and state["call"]:
                action = {"type": "advance"}  # the pop (design 1.9)
            elif not visible:
                outcome = ("stuck", node_id)
                break
            elif real:
                # buttons: every visible choice (fallbacks show while any
                # non-fallback does); pick one at random
                index = rng.randrange(len(visible))
                _, choice = visible[index]
                heat[(node_id, choice["label"])] += 1
                action = {"type": "choice", "index": index}
            else:
                action = {"type": "advance"}  # only fallbacks: first is taken
            state, steps = apply_transition(state, action)
            if not steps:
                outcome = ("stuck", node_id)
                break
            reached.add(state["path"][-1])
        else:
            capped += 1
        if outcome:
            kind, node_id = outcome
            if kind == "end":
                endings[node_id] += 1
            else:
                stuck[node_id] += 1

    print(f"\nSimulated {walks} walks (story seed = walk index, cap {max_steps})")
    print(
        f"  endings: {sum(endings.values())}"
        f"  stuck: {sum(stuck.values())}"
        f"  capped: {capped}"
    )
    if endings:
        print("Ending distribution:")
        for node_id, count in endings.most_common():
            print(f"  {count:5} ({count / walks:>5.1%})  {node_id}")
    if stuck:
        print("Dead-end walks:")
        for node_id, count in stuck.most_common():
            print(f"  {count:5}  {node_id}")
    unreached = [node_id for node_id in story["nodes"] if node_id not in reached]
    if unreached:
        print(f"Unreached nodes ({len(unreached)} of {len(story['nodes'])}):")
        for node_id in unreached:
            print(f"  {node_id}")
    if heat:
        print(f"Choice pick heat (top 15 of {len(heat)} picks):")
        for (node_id, label), count in heat.most_common(15):
            print(f"  {count:5}  {node_id}: {label[:48]}")
