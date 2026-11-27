---
revisit: true
vars:
    home: "Alder Street"
choices:
    - label: Call yourself Skye
      to: string-test
      effects:
        - player = "Skye"
    - label: Back to the line effects demo
      to: line-effects-test
choices_from: _shared/menu
---

Numbers are not the only variable: a name, a place, a passphrase - anything text-shaped - lives in the same `vars` map, quoted in the front matter like `home` above or written by an effect

/if not player
/set player = "Ash"
/endif

You are {player}, and you live at {home}

/if player == "Ash"
The comparison `player == "Ash"` is true: both sides quoted, exact match
/else
The comparison `player == "Ash"` is false now - the button above rewrote your name before this page redrew
/endif

Strings compare with `==` and `!=` only - a name has no `>=` - and a choice effect can rewrite a string mid-story, which is what "Call yourself Skye" does before this page appears again

## Back to the menu
