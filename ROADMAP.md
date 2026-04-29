# Roadmap

This roadmap focuses on turning the current docs-first `operator-core-mini` repo into a durable design and implementation spine without prematurely forcing a giant app.

## Phase 0 — Preserve the synthesis

Goal: make sure the throughline is saved in one place before implementation starts.

- Finalize `README.md`, `MANIFESTO.md`, and the core docs set.
- Confirm the central model: Backpack, Doctrine, Hoard.
- Keep the repo intentionally small and legible.

## Phase 1 — Define the substrate

Goal: turn the philosophy into explicit data contracts.

- Create a first-pass `schemas/` folder.
- Define Backpack item shape: key, value, freshness, scope, source, decay policy, renderer hints.
- Define Doctrine item shape: pinned truth, routing rules, defaults, workflows, identity.
- Define Hoard item shape: transcript, artifact, note, timeline entry, imported memory.
- Define freshness and replacement policy explicitly instead of keeping it only implicit in the docs.

## Phase 2 — Add examples

Goal: make the system concrete enough that future implementation work has reference artifacts.

- Add sample Backpack entries based on the current `backpack.json` patterns.
- Add sample Doctrine entries based on stable truths, user profile, routing rules, and evergreen references.
- Add sample Hoard entries such as transcript summaries, timeline events, or archived notes.
- Add sample rendered outputs: session brief, daily brief, narrator brief, statusline summary.

## Phase 3 — Define ingestion pathways

Goal: identify how existing systems would feed the substrate.

- Document `scratch-pad` → Backpack ingestion.
- Document narrator vault/task/theme → Doctrine and Backpack interactions.
- Document life-state tools → Backpack / Hoard ingestion rules.
- Document transcript and session summary → Hoard ingestion rules.

## Phase 4 — Build the first renderer prototypes ✅ shipped (2026-04-29)

Goal: prove that one truth layer can support multiple surfaces.

The renderer prototypes are implemented in the companion `operator-core-schemas` working repo. All five surfaces project from a single deterministic `FactBundle` (per ADR 0003) and are covered by golden tests under `tools/test_renderers.py` (two-tier check: structural fingerprint + snapshot).

- ✅ `renderers/session_primer.py` — assistant bootstrapping primer.
- ✅ `renderers/daily_brief.py` — daily brief from Backpack + Doctrine.
- ✅ `renderers/narrator_list.py` — template-driven, deterministic narrator surface (carries the active voice rule).
- ✅ `renderers/narrator_brief.py` — prompt-driven narrator surface; renderer emits a versioned prompt artefact for an LLM (ADR 0005 clarification 2026-04-29).
- ✅ `renderers/statusline.py` — compact ambient cue.
- ✅ Voice-rule + routing-rule selection (ADR 0005), including an `--energy` regression test that flips skin via routing.

Open follow-ups tracked in the working repo's `docs/PLAN-followups-2026-04-29.md`.

## Phase 5 — Evaluate and prune

Goal: keep the system humane, legible, and grounded in actual use.

- Validate whether Backpack remains small enough to trust.
- Validate whether Doctrine prevents drift without becoming a junk drawer.
- Validate whether Hoard is useful without becoming mandatory to maintain.
- Remove structures that create upkeep without reducing reconstruction cost.

## Immediate next files

If work starts right away, the next best additions are:

- `CONTRIBUTING.md` — how changes should align with the philosophy.
- `schemas/backpack.schema.json` — first-pass Backpack data model.
- `schemas/doctrine.schema.json` — first-pass Doctrine data model.
- `schemas/hoard-item.schema.json` — first-pass Hoard item model.
- `examples/backpack.sample.json` — representative active carry-state sample.
- `examples/session-brief.sample.md` — example renderer output.

## Non-goals for now

To protect the project from premature sprawl, these are probably not the right immediate moves:

- Do not build a giant all-in-one app first.
- Do not force Chronicle-style infrastructure back in just because it looks architecturally neat.
- Do not let Hoard logic overwhelm Backpack simplicity.
- Do not treat narrator skins as the architecture; keep them as renderers over stable truth.

## North star

Build the shared substrate first. Let every dashboard, narrator, buddy, daily brief, and assistant bootstrap become a client of that substrate rather than inventing a fresh disconnected system each time.
