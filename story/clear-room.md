---
revisit: true
clear: clear-demo-seen
choices:
    - label: This door never opens on this page
      to: clear-room
      if: clear-demo-seen
choices_from: _shared/menu
---

Front matter runs the moment a page is entered: this room's `clear: clear-demo-seen` deletes the flag before a single line or choice exists, even though you arrived carrying it

/if clear-demo-seen
You still carry the flag - unreachable text: clear ran on entry, so this condition is false the instant the page appears
/else
The flag is gone: clear fired on entry, and this is the branch you are reading
/endif

The first choice below is gated on the flag this page just deleted, so it never appears - visibility is judged against the post-entry state. To raise the flag again, walk back to the flags demo page and open this room once more
