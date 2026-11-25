---
revisit: true
sets: flags-demo-seen
choices:
    - label: How can I change the text speed
      to: speed-test
    - label: How can I apply text effects
      to: effect-test
    - label: How to make POV explicitly clear
      to: pov-test
    - label: How can I show messages between people
      to: messages-test
    - label: How can I visually show the weather at that time
      to: weather-test
    - label: How can I add extra background effects
      to: background-effects
    - label: How can I show a background image
      to: images-test
    - label: How can I play music and sound effects
      to: audio-test
    - label: How can I make the story remember choices
      to: flags-test
    - label: How do saves and the back button work
      to: back-save-test
    - label: How do I change how the story looks and feels
      to: settings-test
    - label: Open the page only a flag can reach
      to: flags-unlocked
      if: flags-demo-seen
    - label: How do I show text only sometimes
      to: conditions-test
    - label: How do I track a score or number
      to: vars-test
    - label: What happens to a choice with no implementation
      to: not-done
    - label: What about when I end the story
      to: end
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
