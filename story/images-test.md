---
revisit: true
image: demo-room.png
choices_from: _shared/menu
---

This page declares `image: demo-room.png` in its front matter, and the file ships in `src/images/`, so the picture is already behind this text

/pause 1s

Images fade in over 400ms, scaled to cover the screen, and sit under the vignette so the text stays readable

A page without `image:` fades the old picture out rather than cutting, and a newer image takes over from an older one mid-fade instead of fighting it

The validator checks every reference: remove the file from `src/images/` and the build fails before a reader ever sees a blank space

---

# The image layer

The picture never moves when you scroll, and it is hidden from assistive technology because it is purely decorative

Changing the front matter to another filename swaps it the same way

## Back to the menu
