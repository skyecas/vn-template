"""Validation: every check from design 4.1 over the IR."""

from __future__ import annotations

import itertools
import re
from collections.abc import Iterator
from pathlib import Path

from .conditions import walk_cond
from .ir import NodeIR, VariantIR, all_nodes
from .patterns import (
    BACKGROUND_COLOUR_PATTERN,
    BACKGROUND_EFFECTS_PATTERN,
    CLEAR_VALUES,
    COLOUR_PATTERN,
    EFFECT_LINE_STRIP,
    EFFECT_PATTERN,
    MESSAGE_PATTERN,
    MESSAGE_TITLE_PATTERN,
    META_COLOUR_PATTERN,
    META_EFFECT_PATTERN,
    META_MESSAGE_PATTERN,
    META_MESSAGE_TITLE_PATTERN,
    META_PACE_PATTERN,
    META_POV_PATTERN,
    META_WEATHER_PATTERN,
    PACE_PATTERN,
    PAUSE_PATTERN,
    POV_PATTERN,
    SFX_PATTERN,
    WEATHER_PATTERN,
)
from .report import debug

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
                if choice.target is not None and choice.target not in parts:
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
                # an end with a next: is dead config the renderer ignores (1.9)
                if part.choices or path.next:
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


def tunnel_no_end(parts: dict[str, NodeIR]) -> list[VariantIR]:
    """a call target the reader can get stuck inside (design 1.9)"""
    forward: dict[str, set[str]] = {name: set() for name in parts}
    for name, node in parts.items():
        if node.next and not node.is_end and node.next in parts:
            forward[name].add(node.next)
        for variant in node.variants:
            for choice in variant.choices:
                if choice.target in parts:
                    forward[name].add(choice.target)

    # the tunnel pops at an end: node or at a return choice (design 1.9)
    can_pop = {
        name
        for name, node in parts.items()
        if node.is_end
        or any(
            choice.return_ for variant in node.variants for choice in variant.choices
        )
    }
    reverse: dict[str, set[str]] = {name: set() for name in parts}
    for name, targets in forward.items():
        for target in targets:
            reverse[target].add(name)
    stack = list(can_pop)
    while stack:
        name = stack.pop()
        for caller in reverse[name]:
            if caller not in can_pop:
                can_pop.add(caller)
                stack.append(caller)

    nodes = []
    for name, node in parts.items():
        stuck: set[str] = set()
        for variant in node.variants:
            for choice in variant.choices:
                if not choice.call or choice.target not in parts:
                    continue
                seen: set[str] = set()
                todo = [choice.target]
                while todo:
                    current = todo.pop()
                    if current in seen:
                        continue
                    seen.add(current)
                    if current not in can_pop:
                        stuck.add(current)
                    todo.extend(forward[current] - seen)
        if stuck:
            debug(f"{name}: call never pops, stuck at {sorted(stuck)}")
            nodes.extend(node.variants)
    return nodes


def orphan_return(parts: dict[str, NodeIR]) -> list[VariantIR]:
    """a return choice in a node no call targets (design 1.9)"""
    called = {
        choice.target
        for node in parts.values()
        for variant in node.variants
        for choice in variant.choices
        if choice.call and choice.target
    }
    return [
        variant
        for name, node in parts.items()
        if name not in called
        for variant in node.variants
        if any(choice.return_ for choice in variant.choices)
    ]
