# Ingestion Trace — one entry's lifecycle

A single worked example showing how a piece of context moves through the three
layers and how replacement chains read end-to-end.

## The story

On **2026-04-06**, Kayla attended a Q2 roadmap meeting. The transcript was
captured into the Hoard. A summary was promoted into Backpack as
`meetings-2026-04-06-q2-roadmap`.

Three weeks later, on **2026-04-29**, a follow-up Q2 sync happened. The new
transcript was captured into the Hoard. The new summary was promoted into
Backpack as `meetings-2026-04-29-q2-roadmap`, with `replaces:
meetings-2026-04-06-q2-roadmap`. The predecessor was moved to
`backpack/_replaced/` so it stops surfacing in current renderers but remains
on disk and in git history.

## Files in this trace

```
ingestion-trace/
├── hoard/
│   ├── 01HW-q2-2026-04-06.json     ← Hoard: original transcript-summary
│   └── 01HW-q2-2026-04-29.json     ← Hoard: follow-up transcript-summary
├── backpack/
│   ├── current/
│   │   └── meetings-2026-04-29-q2-roadmap.md   ← Backpack: current carry-state
│   └── _replaced/
│       └── meetings-2026-04-06-q2-roadmap.md   ← Backpack: predecessor (kept in git)
├── events/
│   └── events.jsonl                ← 11 ingestion events (ingested, promote, replace, demote, doctrine-proposed, rejected, ...)
├── quarantine/
│   └── 01HW-EVT-0010-rejected.json     ← raw payload + validation errors for the rejected dashboard-manifest entry
├── doctrine-proposals/
│   └── 01HW-EVT-0009-user-profile.md   ← proposed Doctrine change with diff and approval instructions
└── README.md (this file)
```

## How to read the chain

Start at `backpack/current/meetings-2026-04-29-q2-roadmap.md`. Its frontmatter
contains:

- `replaces: meetings-2026-04-06-q2-roadmap` — points back to the predecessor.
- `hoard_refs: ["01HW-q2-2026-04-29"]` — points to the source transcript-summary.

Following `replaces` lands at `backpack/_replaced/meetings-2026-04-06-q2-roadmap.md`,
whose `hoard_refs` points to the original April 6 transcript-summary. Both
Hoard items have `promoted_to_backpack` set so the relationship is bidirectional.

## What renderers do with this

- The session brief and daily brief read only `backpack/current/`, so they
  surface the **2026-04-29** summary.
- Search across the Hoard finds **both** transcript-summaries.
- A "what changed since last sync?" renderer would diff the two Hoard summaries.
- `git log backpack/_replaced/meetings-2026-04-06-q2-roadmap.md` shows the
  predecessor's full edit history before retirement.

## Failure paths

The trace also includes the two non-happy paths from the universal
ingestion contract:

- **`quarantine/01HW-EVT-0010-rejected.json`** — a dashboard-manifest entry
  that failed schema validation lands here, untouched, with the validation
  errors recorded next to it. The corresponding `kind: rejected` event is
  in `events/events.jsonl` at `01HW-EVT-0010`. Quarantine is *not* part of
  the substrate; renderers MUST NOT read from it.
- **`doctrine-proposals/01HW-EVT-0009-user-profile.md`** — a proposed change
  to `doctrine/identity/user-profile.md` sits here pending operator review
  rather than being written to Doctrine directly. The corresponding
  `kind: doctrine-proposed` event is at `01HW-EVT-0009`.

Both illustrate the rule that capture cannot silently fail and Doctrine
cannot silently change.

## Validation

- The two Hoard files validate against `schemas/hoard-item.schema.json`.
- The two Backpack frontmatter files validate against
  `schemas/backpack-item.schema.json` (after stripping the `---` fences and
  parsing YAML).
- Every line in `events/events.jsonl` validates against
  `schemas/ingestion-event.schema.json`.
- `quarantine/*.json` and `doctrine-proposals/*.md` are reference artifacts;
  they are not part of any layer schema and do not need to validate.
