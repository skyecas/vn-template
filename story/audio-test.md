---
revisit: true
music: demo-loop.wav
choices_from: _shared/menu
---

This page declares `music: demo-loop.wav` in its front matter, so a quiet pad is looping behind the text right now

/pause 1s

/sfx blip.wav

That was a `/sfx` marker on its own line: one-shot sound effects can sit anywhere in the story, and the file lives in `src/audio/`

Both music and sound effects obey the volume slider and mute in Settings, and both are remembered between visits

Music crossfades when the story moves to a page with a different track, and stops on pages that say `music: none`

The validator checks sound files exactly like images, so a typo fails the build rather than playing nothing

---

# Music and sfx

Music loops for the whole page and crossfades to the next track; sound effects fire once and get out of the way

## Back to the menu
