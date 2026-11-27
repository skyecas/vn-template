"""v2 compiler: story/*.md -> IR -> validated story.json (version 2).

Thin entry: argv, the check registry, and the runner. The pipeline itself
lives in src/compiler/, one module per docs/design.md section.
"""

from __future__ import annotations

import sys
from json import dumps
from pathlib import Path

from compiler.checks import (
    abnormal_paths,
    background_effect_markers,
    background_markers,
    background_metadata,
    chance_only_exit,
    colour_markers,
    colour_metadata,
    condition_syntax,
    conditional_blocks,
    continuing_ends,
    count_range,
    dead_ends,
    duplicate_choices,
    duplicate_nodes,
    effect_markers,
    effect_metadata,
    empty_nodes,
    ending_nodes,
    escapable_looping_nodes,
    fully_conditional,
    include_missing,
    inescapable_looping_nodes,
    invalid_links,
    macro_params,
    macro_recursion,
    message_markers,
    message_metadata,
    message_title_markers,
    message_title_metadata,
    missing_images,
    missing_music,
    missing_sfx,
    noncontinuing_variants,
    pace_markers,
    pace_metadata,
    pause_markers,
    pov_markers,
    pov_metadata,
    revisit_variants,
    satisfiability,
    set_but_never_read,
    sfx_markers,
    single_choice,
    start_end_nodes,
    starting_nodes,
    unknown_keys,
    unknown_markers,
    unknown_names,
    unreachable_nodes,
    weather_markers,
    weather_metadata,
)
from compiler.emit import generate_json
from compiler.ir import all_nodes
from compiler.load import find_parts
from compiler.report import (
    StoryCheck,
    debug,
    failure,
    pretty_print_paths,
    success,
    warning,
)


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
