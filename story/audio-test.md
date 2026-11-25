---
revisit: true
music: demo-loop.wav
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

This page declares `music: demo-loop.wav` in its front matter, so a quiet pad is looping behind the text right now

/pause 1s

/sfx blip.wav

That was a `/sfx` marker on its own line: one-shot sound effects can sit anywhere in the story, and the file lives in `src/audio/`

Both music and sound effects obey the volume slider and mute in Settings, and both are remembered between visits

Music crossfades when the story moves to a page with a different track, and stops on pages that say `music: none`

The validator checks sound files exactly like images, so a typo fails the build rather than playing nothing

---

# Music and sfx

Music loops for the whole page and crossfades to the next track; sound effects fire once and get out of the way

## Back to the menu
