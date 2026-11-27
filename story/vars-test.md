---
revisit: true
vars:
    score: 5
choices:
    - label: A choice that needs a score of 3 or more
      to: back-step-1
      if: score >= 3
    - label: How do I change a variable mid-sentence
      to: line-effects-test
choices_from: _shared/menu
---

Numbers track anything that counts: a score, health, gold, how much a reader trusts you

The front matter `vars:` block sets them, the same way `sets:` raises flags; a plain number assigns the value

Your score is currently {score}, set to 5 the moment this page appeared

Write `{score}` anywhere in the text and it is replaced with the current value when the line renders, so a running total can sit inside a sentence

Variables also drive conditions, in the choices above and in `/if` blocks: a comparison has a name, one of `>`, `>=`, `<`, `<=`, `==`, `!=`, and a number

The menu now carries a choice labelled "A choice that needs a score of 3 or more"; it is visible because {score} is 5, which is at least 3

Change the front matter to `score: 1` and that choice would disappear on the next generate, because 1 is not >= 3

A plain number overwrites the value, while a quoted `"+1"` or `"-2"` string adjusts it, so a story can both set a starting total and nudge it up or down

## Back to the menu
