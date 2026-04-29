# Narrator brief prompt — 2026-04-29

> This document is a *prompt*, not narrator prose. An LLM consumes the system block + facts and renders prose offline. The facts surface here is identical to what narrator-list, daily-brief, and statusline would surface for the same state (ADR 0003).

---
role: system
prompt_version: 1
renderer_id: narrator-brief
rendered_at: 2026-04-29T14:00:00+00:00
voice:
  skin: mass-effect
  register: terse
  selected_via: 'routing-rule `narrator-low-energy-routing` (when=low-energy)'
  do: ['open with situation, then objective', 'state facts as bullets', 'close with the next decision point']
  avoid: ['softening hedges', 'meta-commentary', 'emoji']
contract: 'Facts stable across renderers; only framing adapts. Do not invent items not in the Facts block. Cite each prose claim by item id in a trailing comment.'
---

## Facts

### Today's life-state

- **life-state-2026-04-29** — 2026-04-29 — Sleep 6h, body 4/10, mood mild. One real meeting today,

### In the bag

- **qa-queue-2026-04-29** — 2026-04-29 — 4 in-flight TTOAD tickets: 367 in code review with auth
- **q2-roadmap-sync-2026-04-29** — 2026-04-29 — Q2 roadmap sync: scope locked for May, NHHA RCM phase 2
- **nhha-rcm-board-2026-04-29** — 2026-04-29 — Current board reflects post-launch fast-follows; phase 2
- **life-state-2026-04-29** — 2026-04-29 — Sleep 6h, body 4/10, mood mild. One real meeting today,

### Verify before acting

- **bug-referral-setup-2026-04-09** (~20d old) — 2026-04-09 — Bug-referral path established with Jamie's team. Re-confirm

### Aged out overnight

- **ttoad-221-discharge-filter-bug-2026-04-09** (aged out 2026-04-29) — 2026-04-09 — Discharge-filter bug pattern: discharge endpoint silently

## Instruction

Render the Facts block above as prose using the voice rule declared in the system block (skin: `mass-effect`, register: `terse`). Apply the do/avoid rules verbatim. Do not invent items not in the Facts block. Cite each prose claim by item id in a trailing HTML comment (e.g. `<!-- cite: q2-roadmap-sync -->`). Keep the prose under ~250 words. End with a single-line closer consistent with the active voice.

---
*Source: `/home/user/workspace/operator-core-schemas/examples/operator-root-fixture`. Rendered 2026-04-29T14:00:00+00:00 by `renderers/narrator_brief.py`. Deterministic prompt artefact; the LLM step is outside the renderer boundary.*
