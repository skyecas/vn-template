---
revisit: true
choices:
    - label: Try the level 3 gate again
      to: condition-level-1
    - label: Back to the menu
      to: conditions-test
---

# Level 3: grouped counts

Level 3 trades the list for a map of groups - `all:`, `any:`, `none:`, `at_least 2:`, `exactly 1:`, `between 1 and 3:` - where each group's entries are simple terms and the groups themselves are ANDed together

The choice that brought you here used `any:` with two entries: visit the flags page and the first entry holds, so one true term was enough; nothing ever sets a score of 9999, so the group earns its keep by showing what a failing entry looks like

Counts never nest and never exceed their own entry list - the generator checks both and refuses to emit a group that could never be true

## Back to the menu
