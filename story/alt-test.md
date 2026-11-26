---
revisit: true
choices:
    - label: Read these lines again to advance them
      to: alt-test
choices_from: _shared/menu
---

Some lines pick a different branch every time the page opens - no flags, no conditions, just the shape of the source deciding how the pick advances

The plain form is a sequence: the first visit shows the first branch, the next visit steps to the next one, and the walk stops on the last branch instead of wrapping

{first visit.|second visit.|third visit.}

Put an ampersand straight after the opening brace and the same shape cycles instead: it walks the branches in order forever, wrapping back to the start no matter how often you visit

{&The left path curves away.|The right path climbs.|The road doubles back.}

A tilde shuffles instead: every visit takes the next position of one fixed order, so no branch repeats until the whole order has played out, and then the order starts again

{~A cat watches from the wall.|A crow hops along the fence.|A rat disappears under the stones.}

The branches can sit mid-sentence too, where only the picked fragment shows: this line is the {first take.|second take.|third take.} of it

Choose "Read these lines again to advance them" three times and every brace steps forward one visit at a time. The pick is a pure function of the save state, so going Back or reloading a save shows the same branch the first visit produced
