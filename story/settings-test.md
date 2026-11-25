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

Settings live behind the Settings button in the toolbar, and everything in them is remembered in localStorage, so they survive a refresh and come back next session

/pause 1s

The panel gives you story speed, reduced motion, high contrast text, volume, mute, and Restart story

The story speed slider changes how fast the story text appears, and you can move it at any time, even mid-page

While a choice is on screen the story waits for you, so a slow setting never rushes you past anything

/sfx confirm.wav

The look of the story itself, fonts and colours, is the author's side of settings and lives in config.yaml rather than this panel

---

# Reader settings

Story speed, reduced motion, high contrast, volume, mute and restart, all persisted per reader

## Author settings

The `theme:` block of config.yaml sets fonts, colours, the accent colour, corner radius and the POV style before a reader ever touches anything

## Back to the menu
