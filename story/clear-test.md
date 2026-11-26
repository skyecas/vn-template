---
revisit: true
sets: clear-demo-seen
choices:
    - label: Go to the room that clears the flag
      to: clear-room
      if: clear-demo-seen
    - label: This choice never appears either
      to: clear-test
      if: not clear-demo-seen
choices_from: _shared/menu
---

Flags only live until something removes them. This page raises `clear-demo-seen` in its front matter the moment it appears, so the gated choice below and the line under it both read the flag as up

/if clear-demo-seen
The flag is up: this page set it on entry, and the gated choice below opened with it
/else
Impossible here: the front matter above sets the flag before any line renders
/endif

Follow the gated choice into the next room to watch a flag disappear. One lesson hides in plain sight on this page: a choice gated on `not clear-demo-seen` would never show, because the front matter sets the flag before choices are built - effects run first, visibility is judged after
