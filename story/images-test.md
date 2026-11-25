---
revisit: true
image: demo-room.png
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
    - label: What happens to a choice with no implementation
      to: not-done
    - label: What about when I end the story
      to: end
---

This page declares `image: demo-room.png` in its front matter, and the file ships in `src/images/`, so the picture is already behind this text

/pause 1s

Images fade in over 400ms, scaled to cover the screen, and sit under the vignette so the text stays readable

A page without `image:` fades the old picture out rather than cutting, and a newer image takes over from an older one mid-fade instead of fighting it

The validator checks every reference: remove the file from `src/images/` and the build fails before a reader ever sees a blank space

---

# The image layer

The picture never moves when you scroll, and it is hidden from assistive technology because it is purely decorative

Changing the front matter to another filename swaps it the same way

## Back to the menu
