# Repo Structure

This is a proposed structure for the `operator-core` repo based on the synthesized documentation set and the architecture it describes.

## Minimal docs-first structure

```text
operator-core/
├── README.md
├── MANIFESTO.md
├── REPO_STRUCTURE.md
└── docs/
    ├── 01-manifesto.md
    ├── 02-system-architecture.md
    ├── 03-repo-map.md
    ├── 04-backpack-analysis.md
    ├── 05-narrator-analysis.md
    ├── 06-design-principles.md
    └── 07-future-direction.md
```

Use this if the repo is only meant to preserve the vision and architecture for now.

## Recommended structure for the next phase

```text
operator-core/
├── README.md
├── MANIFESTO.md
├── REPO_STRUCTURE.md
├── ROADMAP.md
├── CONTRIBUTING.md
├── docs/
│   ├── 01-manifesto.md
│   ├── 02-system-architecture.md
│   ├── 03-repo-map.md
│   ├── 04-backpack-analysis.md
│   ├── 05-narrator-analysis.md
│   ├── 06-design-principles.md
│   ├── 07-future-direction.md
│   ├── architecture/
│   │   ├── memory-ecology.md
│   │   ├── renderers.md
│   │   ├── retrieval-and-freshness.md
│   │   └── narrator-routing.md
│   ├── repo-notes/
│   │   ├── scratch-pad.md
│   │   ├── qa-brain.md
│   │   ├── narrator.md
│   │   └── life-systems.md
│   └── decisions/
│       ├── 0001-backpack-is-active-carry-state.md
│       ├── 0002-doctrine-vs-hoard.md
│       └── 0003-renderers-over-one-truth-layer.md
├── schemas/
│   ├── backpack.schema.json
│   ├── doctrine.schema.json
│   ├── hoard-item.schema.json
│   ├── renderer-hints.schema.json
│   └── freshness-policy.schema.json
├── examples/
│   ├── backpack.sample.json
│   ├── doctrine.sample.json
│   ├── hoard-sample.jsonl
│   └── session-brief.sample.md
├── prompts/
│   ├── narrator-bootstrap.md
│   ├── session-primer.md
│   ├── daily-brief.md
│   └── statusline-summary.md
├── ingestion/
│   ├── README.md
│   ├── scratch-pad/
│   ├── narrator/
│   ├── journal/
│   └── transcripts/
└── renderers/
    ├── README.md
    ├── dashboard/
    ├── narrator/
    ├── statusline/
    ├── session-primer/
    └── daily-brief/
```

## Folder roles

### Root files

- `README.md` — short repo introduction and map.
- `MANIFESTO.md` — the top-level statement of purpose and throughline.
- `REPO_STRUCTURE.md` — this file.
- `ROADMAP.md` — concrete implementation sequencing once building starts.
- `CONTRIBUTING.md` — rules for future changes so the philosophy does not drift.

### docs/

This is the durable design record.

- Keep the current synthesized docs here.
- Add `architecture/` for deeper design notes.
- Add `repo-notes/` for repo-specific readings and crosswalks.
- Add `decisions/` for lightweight ADRs so future implementation choices stay legible.

### schemas/

This folder should define the data contracts for the memory ecology.

- `backpack.schema.json` — active carry-state items.
- `doctrine.schema.json` — stable truths, defaults, routing, identity.
- `hoard-item.schema.json` — archive items, transcripts, notes, artifacts.
- `renderer-hints.schema.json` — metadata telling renderers how an item can surface.
- `freshness-policy.schema.json` — TTL, pinning, replace-in-place, review windows.

### examples/

This folder makes the architecture concrete.

- Sample Backpack entries.
- Sample Doctrine entries.
- Sample Hoard records.
- Example rendered outputs like a session brief or daily brief.

### prompts/

If the system uses LLMs, this folder holds reusable prompt templates or instruction stubs.

Examples:
- `narrator-bootstrap.md`
- `session-primer.md`
- `daily-brief.md`
- `statusline-summary.md`

These are not the center of the system; they are clients of the truth layer.

### ingestion/

This is where ingestion logic or specs would live.

Potential subfolders:
- `scratch-pad/` for work artifact ingestion.
- `narrator/` for task/vault/theme-related ingestion.
- `journal/` for life-state notes.
- `transcripts/` for meeting/session archives.

### renderers/

This folder is for downstream surfaces.

Potential subfolders:
- `dashboard/` for qa-brain-style current work rendering.
- `narrator/` for role-first, skin-second adaptive voice rendering.
- `statusline/` for compact terminal context.
- `session-primer/` for assistant continuity bootstraps.
- `daily-brief/` for resume and planning surfaces.

## Suggested starting point

If this repo is being created today, the best immediate structure is probably:

```text
operator-core/
├── README.md
├── MANIFESTO.md
├── REPO_STRUCTURE.md
├── docs/
├── schemas/
└── examples/
```

That is enough to preserve the philosophy, define the data model, and give future implementation work a stable landing zone without prematurely forcing a full code architecture.
