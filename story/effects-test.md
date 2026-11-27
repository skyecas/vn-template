---
revisit: true
choices:
    - label: Take the coin (this works once)
      to: effects-test
      once: true
      effects:
        - coins +1
        - took_coin
    - label: How does luck decide what you see
      to: chance-test
choices_from: _shared/menu
---

Choices can carry effects of their own: they run the moment a choice is clicked, before the story moves on, so whatever comes next judges visibility against what the click already changed

This page hands you a coin through a choice with `once: true` and two effect lines: `coins +1` grows a counter from nothing, and `took_coin` raises a flag nothing else sets

/if not coins
/set coins = 0
/endif

Your coin count: {coins}

/if took_coin
The coin is in your pocket: the click raised `took_coin` and grew the counter to {coins}, and this line is reading both back
/else
The coin is still on the table: click "Take the coin" and this branch swaps over
/endif

`once: true` records the pick in the save as `node:variant:index`, so once the choice has been used it disappears for good - click it and watch the button vanish when the page redraws, while Back still restores the moment before the click exactly

## Back to the menu
