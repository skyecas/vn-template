# vn-template v2 design

Status: approved for implementation, 2026-11-25.
This document is the contract for the compiler rewrite. Syntax changes get recorded here first, never hacked in during implementation.

## 0. Principles

1. **Compiler, not interpreter.** `story/` markdown is parsed into an IR, validated, and emitted as `story.json`. The artifact contains no syntax left to parse: conditions are ASTs, text is token streams, markers are structured records, effects are ordered lists.
2. **Python owns all logic** (parsing, validation, simulation). **JS is a dumb renderer** of tokens plus an input handler.
3. **One grammar per concept:** one condition grammar (three call sites), one effect grammar (three spellings), one marker definition (Python parser + JS renderer cannot disagree).
4. **Purity rule:** render never mutates state. Effects run only inside the transition function. Replaying from empty state reproduces any step exactly; the Python simulator and the browser runtime share this rule.
5. **Breaking changes are fine.** `story.json` gets `version: 2`, state blobs get `v: 2`; old URLs and saves are refused, not migrated.
6. **Every feature ships with a demo page** in `story/` and a README entry. If a feature cannot be demoed in under 20 lines, the design is wrong.

## 1. Authoring format

### 1.1 File layout

- `story/<id>.md` - one node, filename = node id
- `story/<dir>/<name>.md` - variant of node `<dir>` (random pick on first entry)
- `story/_...` - not nodes; shared macro/include/choice files (`_shared/`, `_macros/`)
- Frontmatter is YAML; body is prose with line markers

### 1.2 Node frontmatter

| Key | Type | Status | Meaning |
|---|---|---|---|
| `start` | bool | keep | start candidate (runtime picks one at random) |
| `end` | bool | keep | **segment terminator**; see tunnels (1.9). No choices, no `next` |
| `revisit` | bool | keep | node may be re-entered through a loop |
| `title` | str | **new** | display name for saves, recap, debug (default: first text line) |
| `chapter` | str | **new** | sticky status-bar label until another `chapter:` is set (P3) |
| `sets` | str/list | keep | sugar for effect `name` (set true) |
| `clear` | str/list | **new** | sugar for effect `clear name` |
| `vars` | map | keep | assign (`n`, `"str"`) or delta (`"+n"`/`"-n"`); strings now allowed |
| `next` | node id | **new** | unconditional continuation (structural edge for the validator) |
| `if` (alongside `next`) | cond | **new** | conditional fall-through; false = fall through to choices; accepts all 4 levels |
| `choices_from` | path | **new** | merge `choices:` from a `story/_` file (1.8) |
| `pace` `colour` `effect` `pov` `message-pov` `message-title` `background` `weather` `image` `music` | | keep | unchanged |

Unknown node or choice keys are a **build error** (`unknown_keys`), not silently ignored.

### 1.3 Choices

```yaml
choices:
    - label: Pay the toll
      to: gate-open
      if:
          - met_guard
          - gold >= 5
      effects:
          - gold -5
          - paid_toll
    - label: Ask about the road
      to: toll-keeper
      once: true
    - label: Force the gate
      to: gate-forced
      chance: 25
    - label: Bluff your way through
      to: gate-open
      if: bluffed >= 2
```

| Key | Type | Meaning |
|---|---|---|
| `label` | str | required, unique within the node (incl. merged `choices_from`) |
| `to` | node id | target; may be omitted when `return: true` |
| `if` | cond | gate; 4 levels (1.4); false = choice hidden |
| `effects` | list | effect grammar entries (1.5), applied at click, before the snapshot |
| `once` | bool | consumed after picking; recorded in `state.used` as `node:variant:index` |
| `chance` | int 0-100 | probability of being offered; validator warns if it is the node's only exit |
| `fallback` | bool | auto-picked when nothing else is visible |
| `call` | bool | push current node onto `call` stack before following `to:` (1.9) |
| `return` | bool | pop the call stack instead of navigating (early tunnel exit) |

`chance` is a pure offer predicate over the state blob - seeded rng, node id, choice index, visit number - so render and replay derive the same roll without writing to state; a failed roll hides the choice exactly like a false `if`. `fallback` choices render as ordinary buttons while any non-fallback choice is visible; when only fallbacks remain the node offers no buttons and the first fallback is taken on advance.

### 1.4 Conditions - four levels, one grammar

**Level 1 - the default; a list read top to bottom:**

```yaml
if:
    - met_guard
    - not in_hurry
    - gold >= 5
```

**Level 2 - entries are full expressions** (each entry parsed with the same grammar; simple terms are the degenerate case):

```yaml
if:
    - met_guard
    - gold >= 5 or bluffed >= 2
```

**Level 3 - structured groups; every line stays one atomic condition:**

```yaml
if:
    all:
        - met_guard
        - not in_hurry
    any:
        - gold >= 5
        - bluffed >= 2
    at_least 2:
        - sneaky >= 10
        - fast >= 8
        - charm >= 6
    at_most 1:
        - paid_toll
        - bluffed
    exactly 1:
        - rolled_high
        - rolled_low
```

Level 3 keys:

| Key | Meaning |
|---|---|
| `all:` | every entry true (desugars to `count(min=len, max=len)`) |
| `any:` | at least one true (`count(1, null)`) |
| `none:` | zero true (`count(0, 0)`) |
| `at_least N:` | >= N entries true (`count(N, null)`) |
| `at_most N:` | <= N entries true (`count(0, N)`) |
| `exactly N:` | exactly N entries true (`count(N, N)`) |
| `between N and M:` | N..M entries true (`count(N, M)`); replaces pairing `at_least N` with `at_most M` on the same list |

Rules:
- All groups in one map are **ANDed** together (`at_least 2` + `at_most 3` = "between 2 and 3")
- No nesting inside groups; deeper structure = level 4 string (validator error says so)
- `N`/`M` must satisfy `0 <= N <= M <= len(entries)` (`count_range` error); `exactly N` with `N > len` is caught as never-true by satisfiability
- Level 3 is **frontmatter-only**; `/if` and inline sites are single-line and take level 4

**Level 4 - one full expression**; the only form the single-line sites accept:

```yaml
if: (gold >= 5 or bluffed >= 2) and met_guard and not in_hurry
```

**Grammar (written once, used by all sites):**

```
expr     := or
or       := and ("or" and)*
and      := not ("and" not)*
not      := "not" not | primary
primary  := "(" expr ")" | comparison | truth | visited(id)
comparison := term (==|!=|>|>=|<|<=) term
term     := number | string | name | visits(id)
truth    := name                  # bare name = non-zero / non-empty / true
```

- `visited(id)` desugars to `visits(id) >= 1`; `visits(id)` is a number term
- `if:` accepts string | list (AND) | level-3 map at **every** frontmatter site (`choices[].if`, node `next`+`if`); line/brace sites accept level 4 strings only

### 1.5 Effects - one grammar, three spellings

```
paid_toll            # set true
clear paid_toll      # delete
gold = 10            # assign (number, bool, string)
gold -5 / gold +1    # delta
player = "Ash"       # string assign
roll sneaky 1d20     # seeded RNG write (dice: NdM with optional +/- K)
unlock gallery_gate  # P3: achievement unlock
```

| Site | Spelling |
|---|---|
| Node frontmatter | `sets:` / `clear:` / `vars:` (structured YAML; desugars to the same EffectIR) |
| Choice / anywhere in a list | `effects:` - one entry per line, grammar above |
| Text line | `/set gold -5`, `/clear paid_toll`, `/roll sneaky 1d20` |

Assignment vs delta is never encoded as string punctuation (`"+n"` at node level is YAML sugar that desugars to `add`; the choice/line spellings are always explicit).

### 1.6 Text markup

**Line-only markers** (entire line): all current (`/pace`, `/colour`, `/background`, `/pov`, `/message*`, `/message-title`, `/pause`, `/focus`, `/effect reset`, `/weather`, `/sfx`, `/if` `/else` `/endif`) plus:

| Marker | Meaning |
|---|---|
| `/set <effect>` | apply one effect mid-prose (1.5) |
| `/clear <name>` | remove a var/flag |
| `/roll <var> <dice>` | seeded roll into a var |
| `/input <var>` | P3: inline text entry written to a string var (length-capped) |

**Inline / brace rules** (single rule: `{` + bare name = variable; anything else = block):

```markdown
You have {gold} coins.                            # substitution (strings too)
{score >= 10: You feel rich.|You count twice.}    # inline conditional (level 4 cond)
{first visit.|second visit.|again.}               # sequence keyed off visits(id)
{&He nods.|She shrugs.}                          # cycle every visit
{~A cat.|A crow.|A rat.}                         # shuffle, no repeat until exhausted
```

- `// comment` at line start: stripped at build, never reaches `story.json`
- Unknown markers remain a build error (`unknown_markers`), now checked on macro-expanded text

**Branch shape for `if`/`alt`** (both token kinds store the same thing): a branch is an *array of line-entries*, i.e. exactly the shape of `lines` (each entry = one lexed line's token list). Two modes:

- **block mode** - the line's sole token is an `if` built from `/if` ... `/else` ... `/endif`; `then`/`else` hold the lines between the markers (an `alt` never occurs here).
- **inline mode** - the `{...}` brace appears mid-line and matches the shape below. Inline `if` is `{cond: then|else}` (a colon before the first pipe; no colon-before-pipe = not an if site): first pipe branch = one entry in `then`, second pipe branch = one entry in `else` (no second pipe = empty `else`; more than two pipes is `condition_syntax`). Inline `alt` (`{a|b}`, `{&a|b}`, `{~a|b}`): every pipe branch is one entry in `branches`. Braces matching no shape stay literal text.

### 1.7 Visibility rule for `/if`

Effects inside conditional lines execute in source order during entry (state evolves as the walk proceeds). Display visibility is evaluated against the post-entry state. Divergence is possible only when a line effect mutates a var that a later `/if` in the *same node* depends on; documented, accepted (rare, and the validator can warn on it later).

### 1.8 Macros and includes

```markdown
story/_shared/omen.md          # no params = plain include
A crow watches from the wall.

story/_macros/greet.md
---
params: [who]
---
/pov {who} Well met, {who}.
```

```markdown
# in any node body
The gate swings open.
{{_shared/omen}}
{{_macros/greet Alice}}
```

- Paths are relative to `story/`, minus `.md`; `_` prefix required (subdirs are otherwise variants)
- `params:` binds positional args (`{{_macros/greet Lady Alice}}` - quoted string args supported); `{who}` substitutes during expansion
- **Compile-time expansion** before validation, so reachability/`unknown_markers`/condition checks see real text
- Recursion: depth limit + cycle check (`macro_recursion` error)
- Diagnostics carry the origin chain: `story/_macros/greet.md:2 (via gate.md:12): unknown marker /pv`
- `choices_from: _shared/menu` merges a file's frontmatter `choices:` (body includes cannot reach frontmatter; this is the shared-menu mechanism)
- Merge semantics: only the file's `choices:` list is merged (its other frontmatter keys are ignored); the node's own choices come first and the merged choices follow; the merged file may itself carry `choices_from`, which chains with a cycle check; a missing file, a file with no `choices:`, or duplicate labels across the merged whole are build errors (P2's `choices_from_clash` will name the last one)

### 1.9 Tunnels

**Rule: `end: true` means "this segment ends here." The call site is the only opt-in; the finish needs no marker.**

```yaml
# corridor.md
choices:
    - label: Submit to the search
      to: search
      call: true              # push corridor
```

```yaml
# search.md
---
end: true
---
He finds nothing.
```

- Flow: click -> push -> sub-scene runs normally (edges, `next`, effects, choices) -> terminator text reveals -> advance (or `autoAdvance`) performs the pop -> caller's choices offer again
- **Early exit:** choice-level `return: true` (a reader decision, not bookkeeping)
- **Resume rule:** a return transition does not re-apply the caller's effects and does not re-pick its variant (only fresh-entry transitions do); `gold +1` on the caller cannot double-fire
- **Nested tunnels:** pop one level per terminator; `call` is a stack in the state blob
- **Gallery:** an `end:` node records a finishing only when the stack was empty
- **Rendering intent:** tunnel content appends to the log transcript-style; after the pop, the caller's choices render at the bottom (refine in P2; no DOM snapshotting)
- **Validator:** every `call` target must reach an `end:` on all paths (tunnel-never-pops = trap); `return` choice in a node no `call` targets = warning; `end:` with `next:`/choices = error (extends `continuing_ends`)

**Reuse matrix:**

| Need | Mechanism |
|---|---|
| Shared paragraph or choice list | `{{macro}}` / `choices_from` (compile-time, no flow) |
| Shared scene, return target always the same | hub-and-spoke node + plain edges (zero features) |
| Shared scene, return to whoever called | tunnel |
| Parameterized scene | choice `effects:` sets vars, then `call:`; vars are the arguments |
| Return values | deferred; vars cover it |

## 2. Artifact and runtime

### 2.1 `story.json` v2

```json
{
  "version": 2,
  "nodes": {
    "gate": {
      "start": false, "end": false, "revisit": true,
      "title": "The Gate", "chapter": null,
      "next": "shop", "nextIf": {"op": "truth", "name": "has_key"},
      "variants": [{
        "lines": [
          [{"t": "lit", "v": "The guard blocks the road."}],
          [{"t": "mk", "k": "pov", "v": "alice"}, {"t": "lit", "v": "You again?"}],
          [{"t": "fx", "op": "roll", "var": "sneaky", "dice": [1, 20, 0]}],
          [{"t": "lit", "v": "You scored "}, {"t": "var", "name": "sneaky"}, {"t": "lit", "v": "."}],
          [{"t": "if", "cond": {"op": "cmp", "lhs": "sneaky", "cmp": ">=", "rhs": 15},
            "then": [{"t": "lit", "v": "He waves you through."}],
            "else": [{"t": "lit", "v": "He shakes his head."}]}]
        ],
        "effects": [
          {"op": "set", "name": "met_alice"},
          {"op": "clear", "name": "guard_suspicious"},
          {"op": "assign", "name": "gold", "val": 10},
          {"op": "add", "name": "trust_alice", "val": 1}
        ],
        "choices": [
          {"label": "Pay the toll", "to": "gate-open",
           "cond": {"op": "and", "args": [{"op": "truth", "name": "met_guard"},
                                          {"op": "cmp", "lhs": "gold", "cmp": ">=", "rhs": 5}]},
           "effects": [{"op": "add", "name": "gold", "val": -5},
                       {"op": "set", "name": "paid_toll"}],
           "once": false, "chance": 100, "fallback": false, "call": false, "return": false}
        ]
      }]
    }
  },
  "ends": ["end"],
  "meta": {"endings": [{"id": "end", "title": "The End"}]}
}
```

Token types: `lit`, `mk` (marker record), `var`, `if`, `alt` (mode: `seq`|`cycle`|`shuffle`), `fx`.
Condition AST ops: `truth`, `not`, `and`, `or`, `cmp`, `visits`, `count` (`min`/`max`/`args`; `null` max = unbounded).
Effect ops: `set`, `clear`, `assign`, `add`, `roll`, `unlock`.

### 2.2 State blob v2

```json
{
  "v": 2,
  "path": ["gate", "gate-open"],
  "variants": [0, 1],
  "vars": {"gold": 5, "player": "Ash", "paid_toll": true},
  "visits": {"gate": 1},
  "used": ["gate:0:1"],
  "rng": {"seed": 41771, "n": 3},
  "call": ["corridor"],
  "povColours": {"alice": "mediumpurple"}
}
```

- **Flags and vars are unified:** one `vars` map holding bool/number/string. `sets:` is sugar for `name = true`; `if: paid_toll` is a truthy check; `not` works on anything; one unknown-name check, one satisfiability domain
- `visits` auto-tracked (sequences, `visited()`, recap); `used` = once-only choices; `rng` = seeded (saves reproduce; Python sim and JS can be diff-tested on one seed); `call` = tunnel stack
- Everything (URL, save slots, history step, Back, jump-to-step, share permalink) is **selecting a blob**; one code path
- `sanitizeState` validates every field; string values length-capped (URL bloat guard); `v` must equal 2 or the state is refused

### 2.3 Transition sequence

`applyTransition(state, action)` where action = choice click | implicit advance | return | restart:

1. Consume the choice (`once` -> `used`; `chance` offer predicate from 1.3)
2. Apply choice `effects`
3. Flow: push (`call`) / pop (`return` / terminator) / append path / follow `next`
4. Fresh entry only: pick variant (stored index wins), apply node `effects`, walk lines applying visible `fx` in source order, `visits++`
5. Return/resume transitions **skip step 4's effects and variant pick**

Render receives the finished blob and draws it; it never writes to it.

### 2.4 Runtime responsibilities

**Does:** load `story.json` + `config.yaml`; own the state blob (URL sync incl. `pushState`/`replaceState`, 3 save slots, popstate, history snapshots, jump-to-step); run the transition function; render token streams through the existing visual machinery; input (advance/reveal, click-to-advance, 1-9 hotkeys, auto-advance, timed choices, panels, toolbar).

**Stops doing:** parsing any syntax - no marker regexes, no condition regexes, no `{}` logic, no frontmatter awareness.

**Unchanged surface:** config.yaml `theme:` block, toolbar/panels/settings UI, weather canvas, audio pipeline (music crossfade, sfx, volume), POV headers/boxes, message bubbles, title screen, reduced-motion/high-contrast handling, `ResizeObserver` toolbar height.

## 3. Parser and IR

### 3.1 Pipeline

```
story/*.md
  -> 1. load + YAML frontmatter (file:line spans kept)
  -> 2. lex body lines into tokens        <- the one marker grammar
  -> 3. build typed IR (dataclasses)
  -> 4. validate IR                       <- all checks live here
  -> 5. emit story.json                   <- serialization only
  optional: --sim N | --dot | --report | --watch | --github
```

### 3.2 IR sketch

```
NodeIR    : id, flags(start/end/revisit), title, chapter, next(+cond),
            choices_from, effects[EffectIR], presentation, variants[VariantIR]
VariantIR : lines[list[TokenIR]], choices[ChoiceIR], effects[EffectIR]
TokenIR   : Lit | Var | Marker(k,v) | If(cond, then, else) | Alt(mode, branches) | Fx(op,...)
           # then/else/branches = arrays of line-entries (same shape as lines); see 1.6
ChoiceIR  : label, to, cond(CondAST|None), effects, once, chance, fallback, call, return
CondAST   : Truth | Not | And/Or(args) | Cmp(lhs,cmp,rhs) | Visits(id) | Count(min,max,args)
EffectIR  : Set | Clear | Assign | Add | Roll | Unlock
```

Every IR node carries `(file, line)`.

### 3.3 Diagnostics

- Format: `story/gate.md:14: parse: unexpected token '>>'`; macros add origin chain
- Stage flags: `-lex`, `-parse`, `-check` (replaces the single `-DEBUG` trace; `-d` still works as "all")
- `--github`: emit `::error file=...,line=...::` annotations for PR inline display

## 4. Validation and tooling

### 4.1 Checks

All **44 existing checks migrate** to the IR (conditions are now ASTs, not regex hits). New checks:

| Check | Severity | Catches |
|---|---|---|
| `unknown_keys` | error | misspelled/unknown node and choice frontmatter keys |
| `condition_syntax` (extended) | error | unparseable conditions at all three sites; illegal level-3 nesting |
| `count_range` | error | `at_least N` etc. with `N` outside `0..len` |
| `unknown_names` | warning | flags/vars/`{vars}` in text that nothing sets (replaces `unknown_flags`+`unknown_vars`) |
| `set_but_never_read` | warning | names set but never tested or displayed |
| `satisfiability` | error | never-true conditions: `a and not a`, `exactly N` > len, flags only set behind their own negation (memoised walk over the flag/var domain; `count` nodes are cheap predicates inside it) |
| `chance_only_exit` | warning | `chance` on the node's only visible exit |
| `tunnel_no_end` | error | `call` target that cannot reach `end:` on all paths |
| `orphan_return` | warning | `return` choice in a node no `call` targets |
| `choices_from_clash` | error | duplicate labels after merging |
| `macro_recursion` | error | macro cycle / depth overflow |
| `next_targets` | error | `next`/`next if` pointing at missing nodes (folded into `invalid_links`) |
| `contrast` | warning | authored `colour`/`background` pairs below WCAG AA ratio (computed from `named_colours` luminance) |

Final count lands in the README at implementation time.

### 4.2 Analysis tools

| Tool | Output |
|---|---|
| `--sim N` | seeded random walks over the compiled artifact: unreached nodes, ending distribution, dead-end walks, choice pick heat |
| `--dot` | DOT/Mermaid graph export |
| `--report` | `report.html`: sim stats, branch heat, **asset weight per route**, reading time, set-but-never-read, contrast failures, and for every unsatisfiable/locked condition an **example state that would unlock it** |
| `play.py` | interactive terminal player over the same artifact: numbered choices, `back`, `state`, `save`/`load`; shares the simulator with `--sim` |
| `--watch` | file watcher -> rebuild -> live-reload the browser |
| `?debug` (runtime) | overlay: current node/variant, full state dump, per-choice condition results **with the reason a hidden choice failed** |

### 4.3 Runtime meta (P3)

localStorage `vn-template.meta`: `{endings: [], achievements: [], unlocks: {}, lastRun: {path, at}, playtime}`.
Feeds: endings gallery ("3/7"), achievement toasts, returning-reader recap, skip-read (skip stops at first node not in `read`), NG+ unlocks.

## 5. Feature phases

### P0 - compiler spine (breaking; no new story-visible features except level grammar)

- Pipeline, IR, condition grammar (all 4 levels incl. count quantifiers), effect grammar, token lexer
- `story.json` v2 + state blob v2 (unified vars) + purity rule in the runtime
- All 44 checks migrated; `unknown_keys` added
- Pure-renderer rewrite of `script.js` (visual machinery untouched)
- Render drivers + static tests re-baselined for v2; demo pages ported
- `docs/design.md` (this file) committed first as the format freeze

### P1 - branching correctness

- Choice-level `effects:`, `once:`, `fallback:`, `next:` + `if`, `chance:`
- Line-level `/set`, `/clear`, `/roll`; seeded RNG in state
- String vars + `{name}` string substitution + `name == "Ash"`
- New checks: `satisfiability`, `set_but_never_read`, `unknown_names`, `chance_only_exit`
- `--sim`, `play.py`, `?debug` overlay

### P2 - reusability and authoring

- `{{includes}}` / `{{macros}}` with `params:`, `choices_from:`, `//` comments
- Tunnels (`call`, terminator pops, choice-level `return`) + tunnel checks
- `--dot`, `--report`, `--watch`, `--github`, `contrast` check

### P3 - reader and meta

- Endings gallery + achievements + persistent meta (localStorage)
- History jump-to-step (snapshots), skip-read, quicksave hotkeys, save metadata (node title, playtime, timestamp)
- Timed choices (`timeout:` / `timeoutTo:` per choice; pause while a panel is open; settings kill-switch)
- Auto reading mode (generalizes `autoAdvance`; stops at multi-choice nodes like Ren'Py)
- Share-the-exact-run permalink, route-aware recap, chapter label + HUD caption (`hud: [gold, day]` in config)
- Text input (`/input <var>`), font-size setting

### P4 - presentation

- Sprites (`src/sprites/`, `/show name@left`, `/expr`, `/hide`, `missing_sprites` check)
- Typewriter reveal (blip pipeline exists), node transitions, `/voice`

### Later / deferred

- Translation extract + `--check-translations`
- ink lists, threads, return values, fairmath (ChoiceScript), `<<script>>`-style moddable JS, storylets, weave/gathers, full Ren'Py-style rollback (jump-to-step approximates it), build-diff, auto-screenshot gallery thumbnails

## 6. Migration (old stories -> v2)

| Old | New |
|---|---|
| `if:` list of terms | unchanged (level 1) |
| `sets:` / `vars:` with `"+n"` | unchanged semantics (sugar over effects) |
| choice-only `label`/`to` | unchanged |
| separate `flags` state | unified `vars` (truthy checks) |
| `return:` node key (never shipped) | deleted; `end:` is the terminator |
| old `?state=` URLs / saves | refused (`v` must be 2) |
| unknown frontmatter keys | now errors - audit stories with the new `unknown_keys` check |

## 7. Verification (every wave)

1. `ruff check src/ && ruff format --check src/`
2. Generator: exit 0, baseline warnings only (repo story)
3. Render drivers (`main` / `flags` / `media`) + `static_test.py`, counts re-baselined at P0
4. Headless Chromium screenshots for every new demo effect
5. Commit (one sentence, no prefix) + push; watch Lint + Deploy CI; verify live site
