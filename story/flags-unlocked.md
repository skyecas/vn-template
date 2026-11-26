---
revisit: true
choices_from: _shared/menu
---

You made it through a door that only exists for readers carrying the `flags-demo-seen` flag

Nothing on this page is special: flags do not unlock content, they unlock choices, so the same page can hide in plain sight until the story decides you have earned it

/pause 1s

If you found this choice in the menu of any other page, that is because every page carries the same gated menu entry

---

# How it worked

The choice carried `if: flags-demo-seen`, and the flags page raised that flag with `sets:` in its front matter

Both live in story front matter, and the generator warns if a gate references a flag that nothing ever sets

## Back to the menu
