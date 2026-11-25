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
    - label: Step forward, then press Back
      to: back-step-1
---

Every choice you take is pushed into history, so the Back button in the toolbar undoes the last decision and re-renders the path from there

The story state lives in the URL: path, variant choices, POV colours and flags, so refresh, Back and bookmark all behave

Saving is the same state, so a save made on any page loads back into exactly the story you left

/sfx confirm.wav

Step forward below, then press Back and watch this page rebuild itself

---

# Step forward

The choice labelled "Step forward, then press Back" moves you on; pressing Back right after puts you straight back here with every flag intact

Going back is safe at any depth, even after loading a save or rewinding through several choices

---

# Load a save

Open Save in the toolbar, write a slot here, then reload the page and load it again

The save carries your flags, so anything unlocked before saving stays unlocked after loading

## Back to the menu
