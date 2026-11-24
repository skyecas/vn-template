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
    - label: What happens to a choice with no implementation
      to: not-done
    - label: What about when I end the story
      to: end
pace: slower
---

We can add background effects that will persist until they're removed or overwritten, that signify certain weathers for moods.

These can be applied as either `/(weather)` in the text, or `weather: (weather)` on the story part metadata.

our options are:

/rain
rain
/pause 1s

/snow
snow
/pause 1s

/fog
fog
/pause 1s

/fireflies
fireflies
/pause 1s

/sunny
sunny
/pause 1s

/clear

Clear and none will remove

/pause 1s
