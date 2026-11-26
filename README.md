# vn-template
a small template for web based choice engine stories

# Using the template

Write your story as markdown files in `story/`, then generate and validate:

```
python3 src/generate_story.py
```

This checks the whole story for broken links, missing starts/ends, unknown markers and the like,
then writes `src/story.json`. It must be run from the repo root (it reads `story/` and `src/named_colours`).

Serve the site over HTTP - browsers block `fetch()` on `file://`:

```
python3 -m http.server
```

Then open `http://localhost:8000/src/`.

Pass `-DEBUG` (or `-d`) to the generator for a line-by-line trace of what it did with each part.

# Story files

Each file in `story/` is one node. The filename (without `.md`) is the id other nodes link to.
Put files in a subdirectory to make them variants of the same node; a variant is picked at random
when the node is reached.

```markdown
---
start: true
revisit: false
choices:
    - label: Where do I go next
      to: next-node
    - label: What about the ending
      to: end
    - label: Only if I found the key
      to: vault
      if: has_key
sets: [met_guard]
pace: slow
colour: red
pov: narrator
---

The text of the node goes here.
```

## Frontmatter keys

| key | meaning |
| --- | --- |
| `start: true` | a random start node is picked among all nodes marked as start |
| `end: true` | marks a node as an ending (it should have no choices) |
| `choices:` | list of choices, see below; empty or missing = dead end |
| `choices_from:` | path of a `_` file whose `choices:` are appended after this node's own; see Shared menus below |
| `sets:` | flags raised while this node is on screen, a name or a list of names |
| `clear:` | flag or var names deleted when this node is entered, a name or a list of names |
| `vars:` | numeric variables set on entry, a `name: value` map; see Variables below |
| `next:` | node id to continue to automatically; see Automatic continuation below |
| `if` (with `next`) | condition for the continuation; when false the page falls through to its choices |
| `revisit: false` | the node cannot be re-entered through a loop; default is `true` |
| `pace:` | default pace for the whole node, see `/pace` below |
| `colour:` | default colour for the whole node, see `/colour` below |
| `effect:` | default effect for the whole node, see the effects below |
| `pov:` | default speaker for the whole node, see `/pov` below |
| `message-pov:` | default speaker for `/message` lines |
| `message-title:` | default chat-window title |
| `background:` | background colour on entry, same values as `/background` |
| `image:` | background image file under `src/images/` on entry; `none` clears it |
| `music:` | looping track file under `src/audio/` on entry; `none` stops it |
| `weather:` | weather effect on entry, same values as the weather markers |

Anything referenced by a choice that does not exist is reported as an invalid link.

### Choices

Each choice needs a `label` (what the reader sees) and a `to` (the node id it leads to).
`if` is optional and gates the choice; it accepts four spellings of the same grammar:

**Level 1 - a list of terms** (every term must hold, so a list reads as `and`):

```yaml
if: [has_key, saw_notice]
```

**Level 2 - a list of full expressions** (each entry parsed on its own):

```yaml
if:
    - has_key
    - skill >= 5 or not alarmed
```

**Level 3 - grouped counts** (simple terms per group, groups ANDed together):

```yaml
if:
    all:
        - has_key
    any:
        - skill >= 5
        - luck >= 3
```

Level 3 group keys are `all:`, `any:`, `none:`, `at_least N:`, `at_most N:`, `exactly N:`
and `between N and M:`; `N` must fit inside the group's entry list.

**Level 4 - one expression string** - the only spelling `/if` and inline braces accept:

```yaml
if: has_key and (skill >= 5 or not alarmed)
```

Expressions combine flag names, `not`, comparisons (`>`, `>=`, `<`, `<=`, `==`, `!=`),
`and` / `or`, parentheses, and visit counters (`visited(node_id)`, `visits(node_id) >= 2`).

### Shared menus

A menu written once can ship on every page with `choices_from`, instead of copying the
list into each file:

```yaml
# story/_shared/menu.md - frontmatter only, no body needed
---
choices:
    - label: Back to the menu
      to: menu
---
```

```yaml
# in any node's frontmatter
choices:
    - label: Open the secret door
      to: secret
choices_from: _shared/menu
```

The path is relative to `story/`, minus `.md`, and must point at a `_` file; only the
file's `choices:` list is merged (its other keys are ignored). The node's own choices
come first, the merged ones follow, and a shared file may chain its own `choices_from`.
Missing files and duplicate labels across the merged whole are build errors.

## Automatic continuation

`next: node_id` makes a page continue on its own: while the continuation is live no choices are
offered, and a click (or Space) moves the story to the named node. Pair it with `if:` to make
it conditional - the condition accepts the same four levels as a choice, and while it is false
the page falls through to its choices as normal:

```yaml
next: epilogue
if: saw_truth
```

A live `next` wins over choices completely: even a page that lists a full menu shows none of
it. `end:` nodes never continue - they have no choices and no `next`.

Within a run, flags come from the `sets:` of the nodes visited so far - `clear:` is the one
way a name comes back down again - so the browser Back button and the save slots restore
exactly the flags that were live at that point. The validator warns when a node's choices are
*all* gated, because a reader missing every flag would have nowhere to go, and when a choice
is gated on a flag that nothing sets.

## Conditional text

`/if`, an optional `/else`, and `/endif` show or hide whole lines based on the same conditions
a choice uses. The markers are stripped; only the matching lines render, and hidden lines never
enter the history:

```markdown
/if has_key
The lock opens.
/else
The door stays shut.
/endif
```

Blocks nest, and `/if` takes one full level 4 expression: comparisons, `and`/`or`/`not`,
parentheses and visit counters all combine in a single line (`/if score >= 3 and visited(vault)`).

Conditions also work mid-sentence, picking a fragment instead of a whole line:
`you are reading the {has_key: unlocked|locked} branch`.

## Alternate lines

A brace holding branches picks one of them each visit - no flags involved, three spellings:

- `{a|b|c}` - sequence: advances one branch per visit to the node and stops on the last one
- `{&a|b}` - cycle: walks the branches in order every visit and wraps back to the start
- `{~a|b|c}` - shuffle: plays one fixed seeded order, so no branch repeats until the order
  has played out, then the same order starts again

The pick is a pure function of the save state: Back, reloads and shared links all show the
same branch the first visit produced. The brace can be the whole line or sit mid-sentence,
where only the picked fragment renders. See `story/alt-test.md`.

## Variables

`vars:` in the front matter tracks anything that counts - a score, health, gold. A plain number
assigns the value; a quoted `"+1"` or `"-2"` string adjusts it:

```yaml
vars:
    score: 5
    gold: "+10"
```

Write `{name}` anywhere in the text and it is replaced with the current value when the line
renders (`Your score is {score}`). Variables also drive `if:` on choices and `/if` blocks
through comparisons (`score >= 3`, with `>`, `>=`, `<`, `<=`, `==`, `!=`). They carry through
Back, saves and the URL like flags do. `clear:` in the front matter deletes a name - flag or
var - the moment its page is entered, before any line or choice is built.

## Markers

Colours are either a name from `src/named_colours` or a hex value like `#ef0`.

Line-wide markers must be the only thing on their line: `/pause`, `/background`, `/focus`,
`/effect reset`, `/weather`, `/sfx` and `/message-title`. Everything else is inline and can sit
anywhere in the text, with the marker itself stripped out.

| marker | effect |
| --- | --- |
| `/pov name` | the rest of the line is spoken by `name`, marked in its own colour (see `theme.povStyle`) |
| `/message name` | the line renders as a chat message from `name` |
| `/message-unsent name` | same, but shown as an unsent message |
| `/message-title title` | sets the chat window title (line must not contain `/`) |
| `/colour name` or `/colour #ef0` | text colour for the line; `/reset` returns to default |
| `/background name` or `/background #ef0` | fades the page background; `/background reset` returns to default |
| `/focus 80%` | vignette focus around the text; `/focus reset` clears it |
| `/effect reset` | clears background effects |
| `/pause 1s` / `/pause 500ms` | waits before continuing |
| `/pace slow` | scales the typing speed of the line |
| `/pace 200ms` | absolute ms per line |
| `/bounce` `/blink` `/glow` `/wave` | animation applied to the line; several can be combined |
| `/rain` `/snow` `/fog` `/fireflies` `/sunny` | weather effect; `/clear` or `/none` stops it |
| `/sfx name` | plays `src/audio/name` once; line must contain nothing else |

`fastest`, `faster`, `fast`, `slow`, `slower`, `slowest` are the named paces; their multipliers
come from `paceMultipliers` in `config.yaml`.

# Configuration

`config.yaml` holds the tuning values: text/choice/fade speeds, colours, text width, pace
multipliers and the default POV colours. The site loads it directly, so edits take effect on
reload; the deploy workflow copies it next to `src/` before generating.

`autoAdvance` (ms) makes a linear story read hands-off: after a node's text finishes, its only
choice is followed automatically once the delay elapses. It only ever fires when a node has
exactly one choice, so branching points are never guessed at, and any reader input cancels it.
`0` (the default) disables it.

The `theme:` block is the story's visual identity, applied before a reader ever touches
Settings:

- `font` / `uiFont` - font stacks for the story text and for the controls
- `textColour` / `darkTextColour` / `backgroundColour` - the core palette
- `accentColour` - primary buttons, hovers and focus rings
- `cornerRadius` - rounding for buttons, choices and panels
- `povStyle` - `header` for a subtle coloured heading over the block, or `box` for the
  original outlined panel

The older top-level `textColour`, `darkTextColour`, `backgroundColour` and `redoButtonColour`
keys still work; `theme:` wins when both are present.

# Controls

The toolbar at the top of the page gives you:

- **Back** - undo the last choice (also wired to the browser Back button)
- **History** - every line read so far
- **Skip** - fast-forward the current node's remaining text
- **Save** - three save slots in `localStorage`, with load and delete
- **Settings** - text speed, reduced motion, high contrast, volume, mute, restart

`Esc` closes any open panel.

While reading you can also:

- **Click anywhere** (or press `Space` / `Enter`) - finish the current line's reveal, or, when
  the story is at a single choice, follow it; a branching point still needs an explicit pick
- **`1`-`9`** - pick that numbered choice directly

# Media

Drop files into `src/images/` (backgrounds) and `src/audio/` (music and sound effects), then
reference them by filename from frontmatter (`image:`, `music:`) or a `/sfx` marker. The
validator fails generation if a referenced file is missing. Music loops and crossfades between
nodes; the volume and mute controls in Settings apply to music and sfx alike.

A demo set ships with the template (`demo-room.png`, `demo-loop.wav`, `blip.wav`,
`confirm.wav`, `success.wav`) so the demo pages have something to play; replace or delete them
once your own media goes in.

# Checks

`python3 src/generate_story.py` runs 46 checks over the story. Failures (❌) stop generation and
exit non-zero; warnings (⚠️) are printed but let the story through. CI runs the same generator,
plus `ruff check` and `ruff format --check`, on every push and pull request, and deploys to
GitHub Pages from `main`.
