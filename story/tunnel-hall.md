---
revisit: true
choices:
    - label: Slip back out
      return: true
    - label: Peer into the study
      to: tunnel-search
      call: true
---
The hall is deeper than it looks: it holds a tunnel of its own, so the call stack can reach two levels deep before anything pops

Slip back out early and the caller resumes with its choices untouched; push deeper instead and the inner terminator pops first, handing you back to this hall before the outer one lets you go
