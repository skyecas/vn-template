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
    - label: "Level 1 if: a list of terms"
      to: condition-level-1
      if:
        - flags-demo-seen
        - conditions-demo-seen
    - label: "Level 2 if: a list of expressions"
      to: condition-level-2
      if:
        - flags-demo-seen
        - score >= 0 or not flags-demo-seen
    - label: "Level 3 if: grouped counts"
      to: condition-level-3
      if:
        any:
          - flags-demo-seen
          - score >= 9999
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

`/if` also takes one full expression: comparisons, `and`/`or`/`not`, and parentheses all combine in a single line

/if score >= 3 and conditions-demo-seen
This line needs a score of 3 or more from the numbers page and this page's own flag; both hold right now, so it rendered
/else
This line stays hidden until you have visited "How do I track a score or number" - the score condition fails without it
/endif

A node can count its own visits too, which is how a scene changes on a second look

/if visits(conditions-test) >= 2
You have opened this page at least twice, so the visit counter condition passed
/else
The counter reads 1 on a first visit; open this page again and these two lines swap
/endif

Conditionals also work mid-sentence, picking a fragment instead of a whole line: you are reading the {conditions-demo-seen: flag-raised|flag-cleared} branch inline, and your score is {score >= 3: at least 3|under 3} as far as this line cares

Three more menu entries spell `if:` at the other levels, and they only appear once you have visited the flags page: level 1 is a plain list of terms (every term must hold), level 2 lets every list entry be a full expression, and level 3 groups terms under `all:`/`any:`/`none:`/count keys like `at_least 2`. Level 4 is a single expression string - the only spelling `/if` and the inline braces above accept, and the spelling the flag-gated menu entry uses

## Back to the menu
