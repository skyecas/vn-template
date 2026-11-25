---
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
    - label: How do I show text only sometimes
      to: conditions-test
    - label: How do I track a score or number
      to: vars-test
    - label: What happens to a choice with no implementation
      to: not-done
    - label: What about when I end the story
      to: end
pace: slow
pov: You
---

We can make it clearly clear who is talking or narating a section

by adding the POV marker around the entire part

but maybe another person wan't to offer an opition

/pov author just like this, perhaps

in that case, unless there's a POV colour defined in the config, it will randomly assign one

/pov author2 like this!

/pov You oh and don't worry about accidentally doubling up, This line is your POV

/pov You and so is this one

/pov author notice how that was all perfectly fine?

/pov Author don't worry, the random colour choice persists to future lines, but POV Name is case-sensitive
/pov Author unless you modify the config!
