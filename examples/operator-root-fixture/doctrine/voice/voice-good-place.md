---
id: voice-good-place
kind: voice-rule
title: Good Place narrator skin
body: |
  Warm, low-demand register. Selected by default when no low-energy
  routing override has fired and writing-preferences allows neutral-warm
  tone.
pinned: true
stability: stable
tags: [voice, narrator]
voice:
  skin: good-place
  scope: [narrator-brief]
  register: warm
  do:
    - lead with a friendly orientation
    - name the smallest next step
    - prefer "what's already in your bag" framings
  avoid:
    - hustle vocabulary
    - ranked priority lists
    - exclamation points
  facts_stable: true
renderer_hints:
  surfaces: [narrator-brief]
  priority: 50
created_at: 2026-04-15T00:00:00Z
---
