---
revisit: true
choices:
    - label: "Next: level 2 demo"
      to: condition-level-2
    - label: Back to the menu
      to: conditions-test
---

# Level 1: a list of terms

You reached this page through a level 1 gate, where `if:` takes a plain YAML list and every term in it has to hold - a list is just `and` written vertically

The choice that brought you here read `flags-demo-seen` and `conditions-demo-seen`, and both were true: the flags page raises the first one with `sets:`, and this menu's own page raises the second the moment you open it

## Back to the menu
