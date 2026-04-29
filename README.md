# operator-core-schemas

Schemas, examples, and ingestion specifications for the
[operator-core-mini](https://github.com/snackdriven/operator-core-mini) substrate.

## Layout

```
operator-core-schemas/
├── schemas/          JSON Schemas (Draft 2020-12) for Backpack / Doctrine / Hoard
│   └── README.md     schema-level docs + coverage table
├── examples/         sample payloads validating against the schemas
│   ├── renders/      four renderer outputs over one shared state
│   └── ingestion-trace/   one entry's full lifecycle across three layers
├── tools/            reference scripts: validate.py, lint.py, migrate.py, bp_build.py
├── renderers/        pure projections over Backpack + Doctrine (Phase 4)
│   ├── _common.py             shared loaders, consent gate, voice/routing helpers
│   ├── session_primer.py      session-start markdown briefing
│   ├── daily_brief.py         morning resumption surface
│   ├── statusline.py          single-line ambient cue
│   └── narrator_brief.py      same facts, voice-rule controlled framing
├── CONTRIBUTING.md   how to change anything in this repo
└── docs/
    ├── ingestion/    Phase 3 — how outside systems feed the substrate
    │   ├── 00-overview.md
    │   ├── 01-scratch-pad.md
    │   ├── 02-narrator.md
    │   ├── 03-life-state.md
    │   ├── 04-transcripts.md
    │   └── 05-promotion-demotion.md
    └── decisions/    lightweight ADRs for load-bearing choices
        ├── 0001-backpack-is-active-carry-state.md
        ├── 0002-doctrine-vs-hoard.md
        ├── 0003-renderers-over-one-truth-layer.md
        └── 0004-consent-posture-is-doctrine.md
```

## Roadmap status

| Phase | Status | Notes |
|---|---|---|
| [Phase 0](https://github.com/snackdriven/operator-core-mini/blob/main/ROADMAP.md#phase-0--preserve-the-synthesis) — preserve synthesis | done (upstream) | in `operator-core-mini` |
| [Phase 1](https://github.com/snackdriven/operator-core-mini/blob/main/ROADMAP.md#phase-1--define-the-substrate) — define substrate | **done** | 8 schemas in `schemas/` |
| [Phase 2](https://github.com/snackdriven/operator-core-mini/blob/main/ROADMAP.md#phase-2--add-examples) — add examples | **done** | examples + renderer outputs + ingestion trace |
| [Phase 3](https://github.com/snackdriven/operator-core-mini/blob/main/ROADMAP.md#phase-3--define-ingestion-pathways) — define ingestion | **done** | 6 docs + ingestion-event schema |
| Phase 4 — renderer prototypes | **in progress** | 4 renderers shipped: session-primer, daily-brief, statusline, narrator-brief |
| Phase 5 — evaluate and prune | not started | |

## Start here

- Philosophy: [operator-core-mini/MANIFESTO.md](https://github.com/snackdriven/operator-core-mini/blob/main/MANIFESTO.md)
- Layers: [schemas/README.md](./schemas/README.md)
- Ingestion contract: [docs/ingestion/00-overview.md](./docs/ingestion/00-overview.md)
- Lifecycle: [docs/ingestion/05-promotion-demotion.md](./docs/ingestion/05-promotion-demotion.md)
- Decisions: [docs/decisions/README.md](./docs/decisions/README.md)
- Contributing: [CONTRIBUTING.md](./CONTRIBUTING.md)
- Validate: `python tools/validate.py`

## Architecture decisions

The load-bearing choices behind the substrate, with alternatives and
consequences:

- [ADR 0001](./docs/decisions/0001-backpack-is-active-carry-state.md) — Backpack is active carry-state, not recent memory.
- [ADR 0002](./docs/decisions/0002-doctrine-vs-hoard.md) — Doctrine and Hoard are different layers, not different views.
- [ADR 0003](./docs/decisions/0003-renderers-over-one-truth-layer.md) — Renderers over one truth layer; not one truth per surface.
- [ADR 0004](./docs/decisions/0004-consent-posture-is-doctrine.md) — Consent posture is Doctrine, not infrastructure.
- [ADR 0005](./docs/decisions/0005-voice-rules-and-routing-rules.md) — Voice rules and routing rules are Doctrine, selected by contract.
