---
revisit: true
choices:
    - label: Force the lock (one chance in four)
      to: chance-test
      chance: 25
    - label: Wait for the wind to open it
      to: chance-room
      fallback: true
---

Two ways through one door

The first choice carries `chance: 25`: three visits in four it is simply not offered, and your save's seed decides which - send someone this link and they will see exactly what you saw

The second is a `fallback`. While the forced entry is on offer it renders like any ordinary button, but when the roll hides everything else, this node shows no buttons at all and the wind carries you through on its own

Come back through the door a few times to catch both outcomes
