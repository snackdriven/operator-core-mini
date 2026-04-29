# Contributing to operator-core-schemas

This repo holds the data contracts, examples, and ingestion specs for the
[operator-core-mini](https://github.com/snackdriven/operator-core-mini)
substrate. The
[MANIFESTO](https://github.com/snackdriven/operator-core-mini/blob/main/MANIFESTO.md)
sets the philosophy. The
[ROADMAP](https://github.com/snackdriven/operator-core-mini/blob/main/ROADMAP.md)
sets the order. This file sets the operating rules.

The system is small on purpose. Most "improvements" make a small system
larger. The bar for changes is therefore higher than usual.

## What this repo is for

- Defining the **shape** of Backpack, Doctrine, and Hoard records.
- Providing reference **examples** that validate against those shapes.
- Documenting **ingestion pathways** and lifecycle operations.
- Recording **decisions** as ADRs when a change is load-bearing.

## What this repo is not for

- A general schema registry. Only operator-core schemas live here.
- Implementation code for renderers or ingestion adapters. Those live in
  consumer repos that *import* these schemas.
- Operator-personal Doctrine content. Personal Doctrine is private state;
  the repo holds shapes and examples, not contents.

## Before you change anything

Read in this order:

1. [MANIFESTO](https://github.com/snackdriven/operator-core-mini/blob/main/MANIFESTO.md) — the three-layer model.
2. [docs/decisions/README.md](./docs/decisions/README.md) — the load-bearing
   decisions.
3. [schemas/README.md](./schemas/README.md) — current coverage and the
   recommended file-system layout.
4. [docs/ingestion/00-overview.md](./docs/ingestion/00-overview.md) — the
   universal ingestion contract.

If a proposed change disagrees with the manifesto or the ADRs, the
manifesto and ADRs win. To override one, write a new ADR that supersedes
it (`Superseded by:` in the old; `Supersedes:` in the new).

## The invariants

These are non-negotiable. Any change that violates one needs an ADR before
it lands.

- **Local-first and inspectable.** Every record is a file on disk a human
  can open. No opaque binary stores. No hidden derived state.
- **Layer integrity.** Backpack, Doctrine, and Hoard have distinct write
  semantics. See
  [ADR 0002](./docs/decisions/0002-doctrine-vs-hoard.md). Crossing layers
  goes through documented lifecycle ops, not flag flips.
- **Active carry-state.** Backpack membership is "currently being
  carried," not "happened recently." See
  [ADR 0001](./docs/decisions/0001-backpack-is-active-carry-state.md).
- **Renderers are pure projections.** They read; they do not write. See
  [ADR 0003](./docs/decisions/0003-renderers-over-one-truth-layer.md).
- **Capture cannot silently fail.** Validation failures during ingestion
  emit `kind: rejected` events; raw material lands in quarantine. Never
  drop.
- **Doctrine changes are proposed, not written.** Adapters emit
  `doctrine-proposed` events with diffs; the operator approves before the
  file changes.
- **Life-state is consent-gated by default.** No auto-promotion to
  Backpack. No pattern derivation without explicit consent.
- **Schemas validate.** The CI signal is "every schema self-validates and
  every example payload validates against its schema." If a change breaks
  this, it doesn't ship.

## Change types and what each requires

### Editorial (typos, link fixes, doc clarifications)

- Open a PR. No ADR. No version bump.
- Run the validation suite (below) to make sure links/refs are intact.

### Adding an example

- Place it under `examples/` with a name that mirrors the schema it
  validates against.
- Update `schemas/README.md` if the new example fills a coverage gap.
- Run the validation suite. The example MUST validate.

### Adding a new field to an existing schema

- The field MUST default to optional. Existing valid records stay valid.
- Document the field's semantics in the schema description.
- Add at least one example payload that exercises the new field.
- If the field changes how the record is written or read in a way that
  affects more than one consumer, write an ADR.

### Adding a new enum member (e.g. a new Hoard kind, doctrine kind)

- Update the schema enum.
- Add at least one example payload of the new kind.
- Update any coverage tables (`schemas/README.md`).
- If the new kind has different write/read semantics from siblings,
  write an ADR.

### Removing or renaming a field, kind, or enum value

- This is a breaking change. Default answer is no.
- If the change must happen: write an ADR justifying it; provide a
  migration script under `tools/`; bump the version field in any
  aggregate schemas that include one.

### Adding a new schema

- Decide it's actually new and not a flavor of an existing one.
- Place it under `schemas/`. The `$id` URL must follow the existing
  pattern (`https://snackdriven.dev/operator-core/schemas/<name>`).
- Add an entry in `schemas/README.md`'s coverage table.
- Add at least one example.
- Write an ADR if the new schema introduces a layer or pathway.

### Adding an ingestion pathway

- Follow the structure of the existing pathway docs under
  `docs/ingestion/`.
- The pathway MUST honor the universal contract in
  `docs/ingestion/00-overview.md`. If it can't, it doesn't ship.
- Define the source, the target layer, the consent posture, and any
  promotion rules.
- Add at least one example to `examples/ingestion-trace/` if the pathway
  is meaningfully different from existing traces.

## Style

### Schemas

- Use Draft 2020-12. Top-level `$id` URL pinned to
  `https://snackdriven.dev/operator-core/schemas/<file>`.
- `$ref` between schemas uses the bare filename (`renderer-hints.schema.json#`),
  not full URLs. Validators resolve via the in-repo store.
- Required fields are minimal. Most metadata is optional.
- Every property gets a `description`. The description is for humans
  reading the source, not for tooling.
- `additionalProperties: false` on tightly-shaped objects (routing,
  voice, attachment). Avoid on records that are expected to grow over
  time.

### Examples

- Use realistic scenarios drawn from the
  [shared state](./examples/renders/_shared-state.md). Don't invent
  unrelated personas — the examples are stronger when they tell one
  coherent story.
- Date all examples explicitly. Use ISO 8601 with timezone where the
  schema accepts `date-time`.
- For Hoard JSONL, one record per line. No trailing newline beyond the
  final record.

### Markdown

- Sentence-case headers. No emoji unless the user explicitly requests them.
- No exclamation points.
- Lines wrapped at ~80 characters where practical, but don't fight the
  content.
- Cross-references use relative paths within the repo
  (`./docs/...`, `../schemas/...`).
- Outbound references use absolute GitHub URLs to
  `snackdriven/operator-core-mini` or related repos, never `git@` URLs.

### ADRs

See [docs/decisions/README.md](./docs/decisions/README.md) for the full
template. In short: short, declarative title; Context / Decision /
Consequences (positive, negative, neutral) / Alternatives / References.

## The validation suite

There is no test runner yet; validation is one Python script. You can run
it inline:

```python
import json, glob, yaml
from jsonschema import Draft202012Validator, RefResolver

# Load schemas into a store keyed by $id and filename.
store = {}
for f in sorted(glob.glob("schemas/*.schema.json")):
    s = json.load(open(f))
    Draft202012Validator.check_schema(s)
    if "$id" in s: store[s["$id"]] = s
    store[f] = s

# Validate every example against its declared schema.
# (See examples/ for the convention: filename mirrors schema name.)
```

Every PR that touches `schemas/` or `examples/` MUST pass this suite
before merge. It's deliberately not automated yet — keeping the loop in
the contributor's terminal makes the validator a thing they read, not a
thing that runs and disappears.

## What gets rejected fast

- **"Just one more field" PRs without examples.** A field without an
  example is a field nobody uses. Add one.
- **Sneaking layer-crossing semantics into a schema.** If your change
  makes Backpack quietly look more like Hoard or vice versa, stop and
  write an ADR.
- **Renderer logic in schemas.** The schema describes shape, not
  inclusion rules. Inclusion lives in `renderer_hints` or in renderer
  code, never inline in a per-item schema.
- **New top-level ingestion pathways without consent posture.** Every
  pathway MUST declare its consent default explicitly. The default is
  *not* "open."
- **Backwards-incompatible changes without a migration.** No quiet
  breaks.

## Philosophy reminder

The system exists to reduce the cost of resuming life and work. Every
change should be evaluable against that goal. If a contribution makes the
substrate larger, denser, or harder to read by hand, it's working against
the goal — even if it's locally well-designed. When in doubt, choose the
smaller change.
