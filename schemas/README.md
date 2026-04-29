# Operator Core Schemas (Phase 1)

JSON Schemas (Draft 2020-12) for the Backpack / Doctrine / Hoard substrate
described in [`operator-core-mini`](https://github.com/snackdriven/operator-core-mini).

These schemas are designed for the **file-system-as-database** layout (one
markdown file per entry, with YAML frontmatter), while remaining backward
compatible with the legacy single-file `backpack.json`.

## Files

### Per-item schemas (validate one entry in isolation)

Use these against a single record — typically a markdown file's YAML frontmatter,
a single ingestion event, or one row in a stream.

| File | Purpose |
|---|---|
| `backpack-item.schema.json` | One Backpack entry. Accepts raw string (legacy) or structured object. |
| `doctrine-entry.schema.json` | One Doctrine entry (identity, default, workflow, routing-rule, voice-rule, evergreen-reference, policy, vocabulary). The `policy` kind may carry a `consent` object describing posture (opt-in / opt-out / forbidden / allow) for an ingestion or rendering scope. |
| `hoard-item.schema.json` | One Hoard record. Hoard files are JSONL where each line validates against this schema. |

### Aggregate schemas (validate a whole layer at once)

| File | Purpose |
|---|---|
| `backpack.schema.json` | Whole Backpack object. Wraps `backpack-item.schema.json` plus `_config:pinned_keys` / `_config:ttl`. Use for the legacy `backpack.json` or for the generated `_index.json`. |
| `doctrine.schema.json` | Whole Doctrine document `{ version, entries[] }`. Wraps `doctrine-entry.schema.json`. |

### Cross-cutting schemas

| File | Purpose |
|---|---|
| `renderer-hints.schema.json` | Optional metadata attached to any item telling renderers how it is allowed to surface. Referenced by every per-item schema. |
| `freshness-policy.schema.json` | Declarative version of the rules currently expressed in prose inside `backpack-freshness-guide`. Bands, TTL presets, verify-after windows, replace-in-place rules. |
| `index.schema.json` | The generated, single-shot read snapshots (`backpack/_index.json`, `doctrine/doctrine.lock.json`, `hoard/_hoard.jsonl` index). Machine-written; never hand-edited. |
| `ingestion-event.schema.json` | Audit record emitted by every ingestion or lifecycle operation. Appended to `hoard/_ingestion-events.jsonl`. |

## Layer mapping

- **Backpack** — *what should be near right now?* Curated, freshness-aware, replace-in-place. Protects against overload.
- **Doctrine** — *what remains true across sessions?* Pinned, low-churn. Protects against drift.
- **Hoard** — *what should not be lost, even if it is not active?* Append-heavy, searchable. Protects against loss.

## Recommended physical layout

```
operator/
├── backpack/
│   ├── current/<id>.md          # YAML frontmatter validates against backpack-item.schema.json
│   ├── pinned/<id>.md
│   ├── evergreen/<id>.md
│   └── _index.json              # generated; validates against index.schema.json (kind: backpack-index)
├── doctrine/
│   ├── identity/<id>.md         # frontmatter validates against doctrine-entry.schema.json
│   ├── workflows/<id>.md
│   ├── routing/<id>.md
│   └── doctrine.lock.json       # generated; validates against index.schema.json (kind: doctrine-index)
├── hoard/
│   ├── YYYY/MM/DD/<id>.json     # each file validates against hoard-item.schema.json
│   ├── blobs/                   # binary attachments referenced by hoard items
│   └── _hoard.jsonl             # generated; one JSON object per line, each validates against hoard-item.schema.json
└── policy/
    └── freshness.json           # validates against freshness-policy.schema.json
```

The per-file form is the source of truth; the `_index.json` / `*.lock.json`
files are machine-generated for one-shot reads (narrator, statusline, daily
brief, Claude bootstraps).

## Backward compatibility

The aggregate `backpack.schema.json` still validates the legacy single-file
`backpack.json` exactly as it exists today, including:

- `_config:pinned_keys` and `_config:ttl` accepted as either a JSON-encoded
  string (legacy) or the parsed object (preferred going forward).
- Each non-config value validates against `backpack-item.schema.json#`, which
  accepts a raw string or a structured object.
- TTL `replaces` chains preserved verbatim.

Migration to the per-file layout is a content move, not a schema break.

## Examples

### Per-item and aggregate examples

| Example | Validates against | Demonstrates |
|---|---|---|
| `examples/backpack.sample.json` | `backpack.schema.json` | Legacy whole-object form. Covers raw-string entries, structured items, all 5 memory classes, replacement chains, pinned keys, TTL config. |
| `examples/backpack-item.sample.json` | `backpack-item.schema.json` | Single structured item with full metadata. |
| `examples/backpack-item.frontmatter.md` | `backpack-item.schema.json` (frontmatter) | File-system-as-database form: YAML frontmatter + body. |
| `examples/backpack-index.sample.json` | `index.schema.json` | Generated, machine-written snapshot for renderers. |
| `examples/doctrine.sample.json` | `doctrine.schema.json` | Whole document. Covers all 8 doctrine kinds; includes 3 consent policies (health-records forbidden, work-channel transcripts opt-in, narrator vault opt-out) demonstrating the `consent` posture extension. |
| `examples/doctrine-entry.sample.json` | `doctrine-entry.schema.json` | Single routing-rule entry. |
| `examples/hoard-sample.jsonl` | `hoard-item.schema.json` | 11 records covering all 11 kinds (transcript, transcript-summary, note, scrap, screenshot, log, journal-entry, artifact, timeline-event, session-summary, imported-memory). |
| `examples/freshness-policy.sample.json` | `freshness-policy.schema.json` | All 5 freshness bands with treatments, TTL presets, promote/demote thresholds. |

### Renderer outputs (`examples/renders/`)

Four surfaces over the **same** Backpack + Doctrine state, proving "one truth
layer, many renderers." Shared inputs documented in `_shared-state.md`.

| Example | Surface | Demonstrates |
|---|---|---|
| `renders/session-brief.sample.md` | Assistant bootstrap | Pinned doctrine + current carry-state + verify-before-acting + aged-out section. |
| `renders/daily-brief.sample.md` | Morning resumption | Today / near-today / verify / aged-out / week / month bands. |
| `renders/narrator-brief.sample.md` | Narrator (Good Place skin) | Same facts; warm low-demand tone; respects writing-preferences and life-state consent gate. |
| `renders/narrator-brief.mass-effect.sample.md` | Narrator (Mass Effect skin) | Same facts as above, terse mission-brief register; proves facts-stable / framing-adapts via the `voice-rule` Doctrine entry. |
| `renders/statusline.sample.txt` | Single-line ambient cue | ~80 char budget; demonstrates RendererHints `priority` and `max_chars_in`. |

### Ingestion trace (`examples/ingestion-trace/`)

One entry's full lifecycle across the three layers. See `ingestion-trace/README.md`.

```
hoard/01HW-q2-2026-04-06.json   ── promoted_to_backpack ──▶ backpack/_replaced/meetings-2026-04-06-q2-roadmap.md
                                                                       │
                                                              replaces (back-ref)
                                                                       │
hoard/01HW-q2-2026-04-29.json   ── promoted_to_backpack ──▶ backpack/current/meetings-2026-04-29-q2-roadmap.md
```

Demonstrates: bidirectional Hoard ↔ Backpack pointers (`promoted_to_backpack`
and `hoard_refs`), replacement chains (`replaces`), and the `_replaced/`
directory convention for retired carry-state.

## Validating

From the repo root:

```bash
python tools/validate.py
```

This self-validates every schema and validates every example payload
against its declared schema. See [`../tools/validate.py`](../tools/validate.py)
for the loader behavior (frontmatter merge, ISO-date string handling,
fresh resolver per check).

## Status

Phase 1 (substrate), Phase 2 (examples), and Phase 3 (ingestion pathways) of
the [roadmap](https://github.com/snackdriven/operator-core-mini/blob/main/ROADMAP.md)
are complete. Phase 3 adds `ingestion-event.schema.json` and the six docs
under `docs/ingestion/`.

The single-file `backpack.json` layout remains supported via the aggregate
`backpack.schema.json`, but the recommended physical layout is the file-system-
as-database form with generated indexes. See `schemas/README.md` and
`docs/ingestion/00-overview.md`.
