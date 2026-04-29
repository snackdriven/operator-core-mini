---
id: ttoad-221-discharge-filter-bug-2026-04-09
freshness_class: historical
memory_class: timeline
area: work
dated: 2026-04-09
created_at: 2026-04-09T15:30:00Z
aged_out_at: 2026-04-29T05:00:00Z
ttl_seconds: 1728000
tags: [ttoad, bug, discharge-filter]
source:
  kind: qa-brain
  ref: ttoad-221
---
2026-04-09 — Discharge-filter bug pattern: discharge endpoint silently
truncates results when the auth token's scope is narrower than legacy
sessions. Pattern lives on in `hunches-and-open-bugs`; raw ticket on the
TTOAD board.
