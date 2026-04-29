---
id: narrator-high-energy-routing
kind: routing-rule
title: Stay on Good Place narrator on high-energy days
body: |
  When the morning life-state token is `high-energy`, keep the warmer
  Good Place skin and the list-style surface. This routing rule exists
  alongside `narrator-low-energy-routing` so the selector has more than
  one entry to disambiguate by `routing.when`; it's also the regression
  fixture for the renderer test that exercises `--energy high-energy`.
pinned: true
stability: evolving
tags: [routing, narrator]
routing:
  when: high-energy
  prefer_renderer: narrator-list
  narrator: good-place
  tone: warm
created_at: 2026-04-29T00:00:00Z
---
