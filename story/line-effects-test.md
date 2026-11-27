---
revisit: true
sets: carried_key
choices:
    - label: How do words become variables
      to: string-test
    - label: Read these lines again
      to: line-effects-test
choices_from: _shared/menu
---

Front matter is not the only place effects live: `/set`, `/clear` and `/roll` are lines, so an effect can sit right where it happens in the prose

/clear carried_key

/if carried_key
The key never leaves your pocket - unreachable text: the `/clear` line above removed `carried_key` while this page was still entering
/else
Your pocket is empty: the `/clear` line above ran during entry, before a single word drew
/endif

/set door_opened

/if door_opened
The door swings open: the `/set` line above raised a flag nothing else knows about
/else
Unreachable text: `door_opened` is set by the line above
/endif

/roll luck 1d20

You rolled {luck} for luck on the way in

/if luck >= 15
The roll smiled: fifteen or more on a d20
/else
The roll came up short: below fifteen
/endif

## Back to the menu
