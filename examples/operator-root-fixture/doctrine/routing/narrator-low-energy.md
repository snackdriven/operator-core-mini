---
id: narrator-low-energy-routing
kind: routing-rule
title: Switch to terse narrator on low-energy days
body: |
  When the morning life-state token is `low-energy`, prefer a terser
  narrator skin so the brief is short and decision-led. This is a routing
  rule, not a voice rule; it selects which voice-rule applies.
pinned: true
stability: evolving
tags: [routing, narrator]
routing:
  when: low-energy
  prefer_renderer: narrator-brief
  narrator: mass-effect
  tone: terse
created_at: 2026-04-15T00:00:00Z
---
