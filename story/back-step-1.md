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

You stepped forward from the save demo

Press Back in the toolbar now: the URL rewinds, the path re-renders, and every flag you were carrying is still set

---

# Rewind

Back can walk all the way out to the title screen, one choice at a time, without losing the story state along the way

## Back to the menu
