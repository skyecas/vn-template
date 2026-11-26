---
revisit: true
sets: flags-demo-seen
choices:
    - label: How do I remove a flag I raised
      to: clear-test
choices_from: _shared/menu
---

Flags let a story remember what the reader has done, without forcing them down one path

The moment this page appeared, `sets: flags-demo-seen` in the front matter raised a flag of that name

Flags survive Back, saving and loading, and they live in the URL too, so a link you send someone carries the story state with it

They do nothing on their own, they only gate choices: the menu above now carries a choice labelled "Open the page only a flag can reach", and it stayed hidden until you read this page

If you had gone straight to any other page first, that choice would not have been there at all

/pause 1s
/sfx success.wav

Pick the flag-only door below, or choose anything else from the menu

---

# The flag

You raised `flags-demo-seen` on the way here

Open the menu on any other page and the flag-only choice will be waiting there too, because every page carries the same menu

---

# The choice

Gated choices take `if:` with a single flag or a list of flags, and every flag in the list has to be set before the choice appears

## Back to the menu
