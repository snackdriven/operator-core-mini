# ADR 0003 — Renderers over one truth layer; not one truth per surface

- **Status:** Accepted
- **Date:** 2026-04-29
- **Deciders:** operator-core-mini owner
- **Supersedes:** —
- **Superseded by:** —
- **Related:** [0001 — Backpack is active carry-state](./0001-backpack-is-active-carry-state.md), [0002 — Doctrine vs Hoard](./0002-doctrine-vs-hoard.md)

## Context

The operator interacts with the substrate through several surfaces — a
session primer when a fresh assistant session starts, a daily brief in the
morning, a narrator skin that adapts voice, a single-line statusline in the
shell. Each surface has different constraints: lengths from 80 characters
to multiple paragraphs, very different tones, different freshness needs,
different consent considerations.

Two ways to satisfy that range:

1. **Each surface owns a tailored data store.** The narrator has its own
   memory; the daily brief has its own carry-state; the statusline has its
   own ticker. Renderers read from their own stores.

2. **One truth layer; many renderers project from it.** Backpack, Doctrine,
   and Hoard hold the canonical state. Each surface is a function from
   that state to bytes. Renderers do not own state; they read it.

The first design is what the project's component repos drifted toward
historically — `narrator` had its own beliefs, `inside-weather` had its own
notion of what mattered today, the dashboard manifest had a third opinion.
The cost is observable in the live `backpack.json`: the same entity (a
ticket, a meeting, a person) appears under different keys with different
shapes because each producer chose its own representation.

The
[MANIFESTO](https://github.com/snackdriven/operator-core-mini/blob/main/MANIFESTO.md)
calls the alternative "one truth layer and many gentle surfaces."
Operationalizing that requires this ADR.

The four sample renderers in `examples/renders/` (session primer, daily
brief, narrator brief, statusline) — generated from the *same* shared
state in `_shared-state.md` — are the existence proof that one truth layer
suffices. This ADR records why that's the chosen direction and what it
costs.

## Decision

**Renderers are pure projections over the three-layer substrate.** They
hold no state of their own. Different surfaces produce different output
from the same canonical inputs by varying inclusion, ordering, framing,
and length — never by varying facts.

Specifically:

1. **Renderers read; they do not write.** A renderer that wants to
   surface a Hoard item it found relevant either (a) emits a `promote`
   ingestion event so the lifecycle handles the write, or (b) flags the
   item for the operator to decide. Renderers never mutate the substrate
   directly.

2. **Facts come from the substrate, framing comes from Doctrine.** The
   set of items a renderer can mention is determined by what's in
   Backpack / Doctrine / Hoard at render time. The voice and ordering
   come from `voice-rule` entries in Doctrine. This is what
   "facts stable / framing adaptive" means at the file level.

3. **`renderer_hints` is the explicit projection contract.** Each item
   carries `renderer_hints` (`schemas/renderer-hints.schema.json`)
   declaring which surfaces it should appear in, with what priority,
   and what truncation policy. Renderers respect these hints; they do
   not infer.

4. **Surface-specific stores are forbidden.** A renderer that needs
   surface-specific configuration (e.g. statusline width, narrator skin
   selection) gets it from Doctrine, not from a private store. If
   something that looks like surface-specific state appears (the
   narrator's "current skin," the daily brief's "last-shown date"), it's
   either a Doctrine entry or a render-time computation — never a fourth
   layer.

5. **Determinism is required where possible.** Given the same substrate
   contents, the same Doctrine, and the same render time, a renderer
   MUST produce the same output. Non-determinism (LLM rephrasing, random
   selection) is permitted only inside a clearly-bounded "framing" step,
   never inside the inclusion step.

## Consequences

### Positive

- **Coherence across surfaces.** When the operator sees a ticket in the
  daily brief and then opens a session, the session primer mentions the
  same ticket with the same status. The narrator skin describes it in
  different words, but the underlying fact is the same. This is the
  central UX promise of the substrate.
- **Renderers are cheap to add.** A new surface (e.g. a wearable
  notification, a mobile widget) is a function over the same data. No
  new ingestion pathway is required. No new schema is required. The
  marginal cost of surfaces drops, which is a precondition for the
  "many gentle surfaces" goal.
- **Renderers are cheap to remove.** A renderer that isn't earning its
  keep can be deleted without touching ingestion or schemas. The Phase 5
  prune step in the roadmap depends on this property.
- **Inspectability is local.** To audit what a surface said, read the
  substrate at that timestamp and re-run the renderer. There is no
  hidden state that drifted.

### Negative

- **`renderer_hints` becomes load-bearing.** Items without good hints
  get rendered poorly or not at all. The schema must be expressive
  enough to handle real surface diversity without becoming a
  configuration language. Mitigation: hints are conservative — surfaces
  default to *not* showing items, and items opt in.
- **Some surface-specific work moves to ingestion time.** Computing
  "this item is relevant to the daily brief" is now an adapter or
  policy concern, not a renderer concern. Adapters are slightly more
  involved as a result.
- **One renderer can't compensate for missing data.** If Backpack is
  empty, the session primer is empty. The renderer can't paper over
  it with cached state from yesterday. This is correct behavior, but
  it makes it more obvious when ingestion is broken — which is some
  cost on bad days, even though it's the right design.
- **Voice-skin variants need explicit Doctrine support.** The narrator
  skin (Good Place, Borderlands, neutral, etc.) is a `voice-rule`
  entry. Operators who want a new skin must write the rule rather than
  letting the narrator "figure it out." This is intentional but adds
  friction.

### Neutral

- Caching is fine. A renderer can cache its output for 60 seconds
  without violating the contract; the cache is just a memoization of a
  deterministic projection.

## Alternatives considered

### A. Per-surface state stores

Each surface owns its own data and ingestion. Rejected: this is the
historical drift the substrate exists to undo. The cost manifests as
inconsistent facts across surfaces, which the operator then has to
reconcile by hand.

### B. One renderer with parameters

A single mega-renderer that takes a `surface` parameter and produces
the right output. Rejected: this collapses to a giant if-tree and
discourages adding surfaces. Many small pure renderers compose better
and stay independently testable.

### C. Renderers may write back to Backpack

Allow renderers to update freshness on items they touched, or pin
items they surfaced repeatedly. Rejected: this is the "renderers
mutate state" trap. The substrate becomes harder to reason about
because reads have side effects. The same goals are reachable through
explicit lifecycle operations (ADR 0001's demotion + Doctrine's
auto-promotion proposals).

### D. LLM-driven renderers without `renderer_hints`

Let an LLM look at all of Backpack and decide what belongs on each
surface. Rejected: non-deterministic, untestable, and silently
inconsistent across runs. LLMs are useful inside the framing step
(turning facts into prose in the narrator's voice). They are not
useful as the inclusion gate, where stability matters.

## References

- [MANIFESTO.md](https://github.com/snackdriven/operator-core-mini/blob/main/MANIFESTO.md) — "one truth layer, many gentle surfaces."
- [docs/05-narrator-analysis.md](https://github.com/snackdriven/operator-core-mini/blob/main/docs/05-narrator-analysis.md) — facts stable / framing adaptive.
- [docs/06-design-principles.md](https://github.com/snackdriven/operator-core-mini/blob/main/docs/06-design-principles.md) — design principles for surfaces.
- `schemas/renderer-hints.schema.json` — projection contract.
- `examples/renders/` — four renderers over one shared state.
- `examples/renders/_shared-state.md` — documents the inputs.
