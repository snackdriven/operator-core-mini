---
id: consent-health-private
kind: policy
title: Health-state items are forbidden on shared surfaces
body: |
  Items tagged or scoped 'health' are personal context. They MUST NOT
  surface in renderers shared with others (daily-brief, statusline). The
  session-primer and narrator-brief MAY surface them in aggregate but
  never by name.
pinned: true
stability: stable
tags: [consent, health]
consent:
  scope: health
  posture: forbidden
  applies_to_pathways: [transcripts]
  applies_to_renderers: [daily-brief, statusline]
  requires:
    - drop on rejection
    - never preserve raw payload in quarantine
  rationale: Health context is private; co-viewers should never see it.
  gate_message: "{count} health-state item(s) held back from this surface."
  gate_message_short: "{count} held: health"
created_at: 2026-04-15T00:00:00Z
---
