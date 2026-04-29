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
│   └── events.jsonl                ← 21 ingestion events covering every kind in the schema enum
├── quarantine/
│   ├── 01HW-EVT-0010-rejected.json     ← schema-violation rejection (failed pattern + null value)
│   └── 01HW-EVT-0012-rejected.json     ← consent-violation rejection (consent-health-data forbidden); raw payload deliberately not stored
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

The trace also includes the non-happy paths from the universal ingestion
contract:

- **`quarantine/01HW-EVT-0010-rejected.json`** — a dashboard-manifest entry
  that failed *schema validation* lands here, untouched, with the validation
  errors recorded next to it. Corresponding event: `01HW-EVT-0010`.
- **`quarantine/01HW-EVT-0012-rejected.json`** — a calendar-recorded
  transcript that triggered a *consent violation* (matched the
  `consent-health-data` policy with `posture=forbidden`). The raw payload is
  deliberately NOT stored: a consent-violation rejection that preserves the
  source content would defeat the policy. Only the calendar-event id is
  retained for audit. Corresponding event: `01HW-EVT-0012`.
- **`doctrine-proposals/01HW-EVT-0009-user-profile.md`** — a proposed change
  to `doctrine/identity/user-profile.md` sits here pending operator review
  rather than being written to Doctrine directly. Corresponding event:
  `01HW-EVT-0009`.

Quarantine is *not* part of the substrate; renderers MUST NOT read from it.
The three artifacts together illustrate the rule that capture cannot
silently fail and Doctrine cannot silently change.

## Lifecycle chains in the events log

Beyond the Q2 meeting story, `events/events.jsonl` carries additional
complete chains so all 14 event kinds are exercised:

- **Transcripts pathway with consent gate** (events `0013`–`0014`): a
  calendar event includes the `transcript-ok` marker (recorded as a
  `hint-observed` event), then the transcripts adapter ingests with
  participant-name redaction per `consent-work-transcripts`.
- **Promotion / pin / unpin / demote** (events `0015`–`0018`): a TTOAD
  ticket is `ingested` into Hoard, `promote`d to Backpack, `pin`ned by the
  user, `unpin`ned three weeks later, and `demote`d back to Hoard once its
  TTL expires (event `0005` records the demote, completing the chain).
- **`superseded-by-hand`** (event `0019`): the user hand-edits an
  evergreen-reference (team roster) in place. No new file, no replacement
  chain — just an audit event.
- **Doctrine approval close-the-loop** (event `0020`): the operator
  approves the `doctrine-proposed` change from event `0009`. A
  `promote-to-doctrine` event records the approval, links back via
  `event_refs`, and the `from`/`to` pair shows the proposal moving from
  the holding area into Doctrine proper.
- **Narrator-vault bi-weekly re-import** (event `0021`): a
  `vault-version-imported` event records a scheduled vault refresh with
  full `stats` (files seen, imported, excluded by frontmatter, excluded
  by path, duplicates skipped). The exclusion counts demonstrate the
  `consent-narrator-vault` opt-out posture in action.

Together with the Q2 meeting chain, this trace exercises every kind in
`ingestion-event.schema.json` (all 14: `ingested`, `ingested-duplicate`,
`rejected`, `superseded-by-hand`, `hint-observed`, `promote`, `replace`,
`demote`, `promote-to-doctrine`, `doctrine-proposed`, `pin`, `unpin`,
`vault-version-imported`, `migration-summary`).

## Validation

- The two Hoard files (and the two Backpack frontmatter files) validate
  against `schemas/backpack-item.schema.json` after stripping the `---`
  fences and parsing YAML. Per follow-up #3 (2026-04-29), Hoard items
  share the Backpack item shape; the optional `aged_out_at` field flips
  them into the aged-out window for renderers.
- Every line in `events/events.jsonl` (21 records) validates against
  `schemas/ingestion-event.schema.json`.
- `quarantine/*.json` and `doctrine-proposals/*.md` are reference artifacts;
  they are not part of any layer schema and do not need to validate. Run
  `python tools/validate.py` from the repo root to run the full suite.
