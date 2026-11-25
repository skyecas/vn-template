---
revisit: true
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

You made it through a door that only exists for readers carrying the `flags-demo-seen` flag

Nothing on this page is special: flags do not unlock content, they unlock choices, so the same page can hide in plain sight until the story decides you have earned it

/pause 1s

If you found this choice in the menu of any other page, that is because every page carries the same gated menu entry

---

# How it worked

The choice carried `if: flags-demo-seen`, and the flags page raised that flag with `sets:` in its front matter

Both live in story front matter, and the generator warns if a gate references a flag that nothing ever sets

## Back to the menu
