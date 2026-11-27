---
revisit: true
choices:
    - label: Search the study
      to: tunnel-search
      call: true
    - label: Step into the hall
      to: tunnel-hall
      call: true
choices_from: _shared/menu
---

A tunnel is a scene that borrows you: both doors below push this node onto the call stack before they open, so the passage on the other side runs as its own story and knows how to find its way back

`call: true` records this node and the variant picked here at the moment you click; the sub-scene then enters fresh - front matter, variant pick, visits and its own effects all run as if you had walked in from nowhere

One door ends its sub-scene on an `end:` page and lets the advance perform the pop; the other slips back early through a `return:` choice - either way this page reappears in the transcript with its choices ready again, and nothing here runs twice
