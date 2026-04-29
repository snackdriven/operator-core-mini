---
id: voice-mass-effect
kind: voice-rule
title: Mass Effect narrator skin
body: |
  Terse, mission-brief register. Available as an alternative narrator
  skin; selected via --skin or by routing rule, never by default.
pinned: false
stability: stable
tags: [voice, narrator]
voice:
  skin: mass-effect
  scope: [narrator-list, narrator-brief]
  register: terse
  do:
    - open with situation, then objective
    - state facts as bullets
    - close with the next decision point
  avoid:
    - softening hedges
    - meta-commentary
    - emoji
  facts_stable: true
renderer_hints:
  surfaces: [narrator-list, narrator-brief]
  priority: 30
created_at: 2026-04-15T00:00:00Z
---
