---
start: true
revisit: false
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
pace: slow
colour: red
---

This is a test of different colours

You can specify a colour for the entire story part

/gold or specify a new colour per sentence, `\{name}`

/green there can only be one colour per sentence (waht would gold-green even be?)

/mediumpurple you can use and of the 148 CSS3 colours

/colour #ef0 or specify a hex code with `/colour (code)`

let's learn about some other modifiers. each can be stacked, like `colour` and `speed`
