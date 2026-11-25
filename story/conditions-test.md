---
revisit: true
sets: conditions-demo-seen
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
    - label: How do I show text only sometimes
      to: conditions-test
    - label: How do I track a score or number
      to: vars-test
    - label: Open the page only a flag can reach
      to: flags-unlocked
      if: flags-demo-seen
    - label: What happens to a choice with no implementation
      to: not-done
    - label: What about when I end the story
      to: end
---

Conditional text shows or hides whole lines based on what the reader has done, so one file can carry several versions of a scene

Wrap the lines in `/if`, an optional `/else`, and `/endif`; the markers themselves are stripped, only the matching lines render

/if conditions-demo-seen
This line rendered because this page raised `conditions-demo-seen` in its front matter the moment it appeared
/else
You will not see this: the flag above is already set
/endif

The reverse works too, with `not` in front of a flag name

/if not conditions-demo-seen
Hidden: the flag is set, so this never shows
/else
This `/else` branch rendered because the condition was false
/endif

Blocks nest, so a line can sit inside two conditions at once

/if conditions-demo-seen
Outer block is open
/if not conditions-demo-seen
Never shown: the inner condition fails
/endif
Still inside the outer block
/endif

Conditions read the same flags a choice would, so a line and a gated choice can agree on one name

## Back to the menu
