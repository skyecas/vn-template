---
revisit: true
next: end
if: flags-demo-seen
choices_from: _shared/menu
---

# Falling through to choices

This page carries both exits: a continuation (`next: end`, conditioned on `if: flags-demo-seen`) and the full menu you see below

While the flag is unset the condition is false, so the continuation stays dormant and the page falls through to its choices - the menu is what you are reading now

Open the flags demo page, then come back here (Back works): the moment `flags-demo-seen` is set the condition turns true, the whole menu disappears, and one click sends you straight to the ending instead

That is the entire rule: a live `next` suppresses the node's choices completely, and a false `if` means `next` is not live, so the choices offer as normal

## Back to the menu
