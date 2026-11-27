#!/usr/bin/env python3
"""Interactive terminal player for story.json v2 (docs/design.md 4.2).

Shares the simulator with `generate_story.py --sim N`: same artifact, same
rng stream, same transition order as the browser.

A number picks that choice; `back` undoes; `state` dumps the save;
`save [file]` / `load [file]` write and restore it (load replays through
compute_step_states, exactly like a shared link).
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path
from typing import Any

from simulator import (
    apply_transition,
    compute_step_states,
    display_lines,
    empty_state,
    live_next,
    load_artifact,
    new_seed,
    node_variant,
    story,
    visible_choices,
)

COMMANDS = "back / state / save [file] / load [file] / quit"


def render(state: dict[str, Any]) -> None:
    node_id = state["path"][-1]
    node = story["nodes"].get(node_id)
    print()
    print(f"[{node_id}]")
    if node is None:
        print("  (missing node - the save may be stale)")
        return
    variant = node_variant(node, state["variants"][-1] if state["variants"] else None)
    for speaker, text in display_lines(state, node, variant, node_id):
        print(f"  [{speaker}] {text}" if speaker else f"  {text}")


def prompt(
    state: dict[str, Any],
) -> tuple[str, Any]:
    """describe the moment, read a line; returns (mode, payload)"""
    node_id = state["path"][-1]
    node = story["nodes"].get(node_id)
    mode = "wait"
    visible: list[tuple[int, dict[str, Any]]] = []
    if node and live_next(state, node):
        mode = "advance"
    elif node:
        variant = node_variant(
            node, state["variants"][-1] if state["variants"] else None
        )
        visible = visible_choices(
            state, node, variant, state["path"], len(state["path"]) - 1
        )
        real = [candidate for _, candidate in visible if not candidate.get("fallback")]
        if real:
            mode = "choice"
        elif visible:
            mode = "fallback"  # no buttons: the first fallback is taken
        elif node.get("end"):
            print("\n[end of story]")
        else:
            print("\n(no visible choices - dead end)")

    if mode == "advance":
        print(f"\n[Enter] continue  |  {COMMANDS}")
    elif mode == "choice":
        print()
        for number, (_, choice) in enumerate(visible, 1):
            print(f"  {number}. {choice['label']}")
        print(f"\npick 1-{len(visible)}  |  {COMMANDS}")
    elif mode == "fallback":
        return mode, None
    elif mode == "wait":
        print(f"\n{COMMANDS}")
    return mode, visible


def valid_save(target: Any) -> bool:
    return (
        isinstance(target, dict)
        and target.get("v") == 2
        and isinstance(target.get("path"), list)
        and bool(target["path"])
        and isinstance(target.get("rng"), dict)
        and isinstance(target["rng"].get("seed"), int)
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="play a compiled story in the terminal"
    )
    parser.add_argument("--story", default="src/story.json", help="compiled artifact")
    parser.add_argument("--seed", type=int, default=None, help="story rng seed")
    parser.add_argument("--start", default=None, help="start node id")
    args = parser.parse_args()

    try:
        load_artifact(args.story)
    except (OSError, ValueError) as e:
        print(f"cannot load {args.story}: {e}", file=sys.stderr)
        return 1
    if not story.get("nodes"):
        print(f"{args.story} has no nodes", file=sys.stderr)
        return 1

    starts = [node_id for node_id, node in story["nodes"].items() if node.get("start")]
    if args.start:
        if args.start not in story["nodes"]:
            print(f"no such node: {args.start}", file=sys.stderr)
            return 1
        start_id = args.start
    elif starts:
        start_id = starts[int(random.random() * len(starts))]
    else:
        print("no starting story nodes defined", file=sys.stderr)
        return 1

    seed = args.seed if args.seed is not None else new_seed()
    state, _ = apply_transition(
        empty_state(), {"type": "start", "node": start_id, "seed": seed}
    )
    history = [state]
    shown: dict[str, Any] | None = None

    while True:
        if shown is not state:
            render(state)
            shown = state

        mode, visible = prompt(state)

        if mode == "fallback":
            # only fallbacks remain: the browser shows no buttons and takes
            # the first one on advance (design 1.3)
            print("\n(only fallback choices remain - taking the first)")
            result, steps = apply_transition(state, {"type": "advance"})
            if not steps:
                print("  (that choice goes nowhere)")
                continue
            state = result
            history.append(state)
            continue

        try:
            line = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0

        if not line:
            if mode == "advance":
                result, steps = apply_transition(state, {"type": "advance"})
                if not steps:
                    print("  (nothing happens)")
                    continue
                state = result
                history.append(state)
            elif mode == "choice":
                print("  (pick a number)")
            continue

        command, _, argument = line.partition(" ")
        command = command.lower()

        if command == "quit" or command == "exit":
            return 0
        if command == "back":
            if len(history) > 1:
                history.pop()
                state = history[-1]
            else:
                print("  (nothing to go back to)")
            continue
        if command == "state":
            print(json.dumps(state, indent=2, ensure_ascii=False))
            continue
        if command in {"save", "load"}:
            path = Path(argument.strip() or "play-save.json")
            if command == "save":
                path.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n")
                print(f"  saved to {path}")
            else:
                try:
                    target = json.loads(path.read_text())
                except (OSError, ValueError) as e:
                    print(f"  (cannot read {path}: {e})")
                    continue
                if not valid_save(target):
                    print(f"  ({path} is not a valid v2 save)")
                    continue
                states = compute_step_states(target)
                if not states:
                    print(f"  ({path} no longer replays: stale link)")
                    continue
                history[:] = states
                state = history[-1]
                print(f"  loaded {path}")
            continue

        if mode == "choice" and line.isdigit():
            index = int(line) - 1
            if 0 <= index < len(visible):
                result, steps = apply_transition(
                    state, {"type": "choice", "index": index}
                )
                if not steps:
                    print("  (that choice goes nowhere)")
                    continue
                state = result
                history.append(state)
            else:
                print(f"  (pick 1-{len(visible)})")
            continue

        print(f"  (unknown command: {command}; try {COMMANDS})")


if __name__ == "__main__":
    sys.exit(main())
