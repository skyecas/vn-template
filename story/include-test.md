---
revisit: true
choices:
    - label: How do I send the reader somewhere and get them back
      to: tunnel-test
choices_from: _shared/menu
---

This page was assembled at build time: two lines in the source were replaced with file contents before validation, so the reader, the renderer and every check only ever see the finished text

{{_shared/omen}}

The crow above came from a single `{{_shared/omen}}` line pointing at `story/_shared/omen.md` - a plain include is a `_` file with a body and no parameters, and its body drops in exactly where that line sat

{{_macros/greet Alice}}

The greeting above came from one `{{_macros/greet Alice}}` line: the macro at `story/_macros/greet.md` declares `params: [who]`, the argument bound that name everywhere in its body, and the crow arrived again because a macro body may include files too

// this line is a comment: stripped at build, it never reaches story.json and never draws anything

Swap Alice for Bob in the source and the next build greets Bob; expansion is build time, so there is nothing runtime about it - no state, no cost to the reader

A macro called with the wrong number of arguments, or a path pointing at a file that does not exist, stops the build and names the file, the line, and where it was included from

## Back to the menu
