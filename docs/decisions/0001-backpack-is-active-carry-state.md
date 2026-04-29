# ADR 0001 — Backpack is active carry-state, not "recent memory"

- **Status:** Accepted
- **Date:** 2026-04-29
- **Deciders:** operator-core-mini owner
- **Supersedes:** —
- **Superseded by:** —
- **Related:** [0002 — Doctrine vs Hoard](./0002-doctrine-vs-hoard.md), [0003 — Renderers over one truth layer](./0003-renderers-over-one-truth-layer.md)

## Context

The substrate has three layers — Backpack, Doctrine, Hoard — defined in the
[MANIFESTO](https://github.com/snackdriven/operator-core-mini/blob/main/MANIFESTO.md).
Of the three, Backpack is the only layer that is read on every surface
(session primer, daily brief, narrator, statusline). It is therefore the
layer most at risk of slow corruption: if its semantics drift even slightly,
every renderer drifts with it.

Two competing framings kept showing up while reading the existing material
(`scratch-pad/backpack.json`, the `dailies/` adapters, the dashboard manifest,
the .claude hooks):

1. **"Backpack = recent memory."** A rolling window of the last N days of
   activity. Pro: easy to reason about. Con: encourages dumping. Anything
   recent qualifies, so the file grows monotonically. The live
   `backpack.json` (119 keys, ~150 KB) is a direct consequence of this
   framing and is exactly the failure mode the project is reacting against.

2. **"Backpack = active carry-state."** Only items the operator is currently
   carrying — open work, open threads, current emotional state, current
   meeting context, current commitments. Pro: bounded by what's actually in
   flight, not by the calendar. Con: requires explicit demotion when work
   ends, instead of passive aging.

Phase 1 schemas, the file-system-as-database refactor, and the ingestion
docs all assumed framing 2 implicitly. This ADR makes that assumption
explicit so future contributors can't quietly re-introduce framing 1.

## Decision

**Backpack is active carry-state.** Membership is determined by what is
currently in flight, not by recency.

Concretely:

1. **Inclusion is intentional.** A Backpack item exists because something —
   a pathway adapter, a hook, or the operator — decided this item is being
   carried right now. "It happened recently" is not sufficient justification
   for a Backpack write. Recent activity that isn't being actively carried
   belongs in [Hoard](./0002-doctrine-vs-hoard.md).

2. **Replacement is the dominant mutation.** New information about an
   already-carried item replaces the predecessor in place
   (predecessor moves to `backpack/_replaced/`); it does not append. See
   [docs/ingestion/05-promotion-demotion.md](../ingestion/05-promotion-demotion.md).

3. **Demotion is mandatory, not opportunistic.** Items that are no longer
   being carried must leave Backpack. The freshness-policy mechanism
   (`schemas/freshness-policy.schema.json`) is how this is enforced
   automatically; explicit operator-driven demotion is also supported.
   Either way, Backpack shrinks over time when nothing new is carried.

4. **The five memory classes stay narrow.** The classes encoded in
   `schemas/backpack-item.schema.json`
   (`current-meta`, `working-memory`, `emotional-state`, `meeting-context`,
   `commitment`) are the full taxonomy. Adding a sixth class is a schema
   change and therefore a deliberate decision, not a casual addition.
   Anything that doesn't fit one of those classes is by definition not
   carry-state.

5. **Auto-promotion to Backpack is consent-gated and conservative.** Life
   state, in particular, never auto-promotes
   (see [docs/ingestion/03-life-state.md](../ingestion/03-life-state.md)).
   Transcript summaries promote only on a small allow-list
   (see [docs/ingestion/04-transcripts.md](../ingestion/04-transcripts.md)).
   The defaults bias toward staying in Hoard.

## Consequences

### Positive

- Backpack stays small enough to render in full inside a session primer or
  daily brief without truncation. The renderer in `examples/renders/` is
  small for this reason.
- Drift is detectable. If Backpack is growing without explicit work being
  added, the demotion path is broken — and that is now an obvious bug, not
  a "we'll clean it up later" condition.
- Each Backpack item can carry rich `renderer_hints` because there are few
  of them. Hints scale poorly when applied to thousands of items; they
  scale fine for the dozens this framing produces.
- Replacement chains stay legible. With small N, a chain of 3–4 versions is
  comprehensible by inspection. With recency-based Backpack, chains
  fragment into "this week's version, last week's version, the version
  from the meeting two weeks ago" with no clean predecessor link.

### Negative

- Demotion logic must actually run. If TTLs fire but the demotion side
  effects don't (file move, index regen, event emit), Backpack accumulates.
  Phase 4 renderer prototypes must include a demotion sweep, not just read.
- Operator effort is required when work ends. Closing a project should
  trigger demotion of its open commitments. If the operator never closes
  anything, Backpack grows. This is acceptable — that growth then matches
  reality, and the resulting noise is itself signal.
- Some adapters need to detect "this is no longer being carried" rather
  than "this is new." Detecting absence is harder than detecting presence,
  so adapters get a little more code.

### Neutral

- Recency, when relevant, lives in `_meta.last_updated` and freshness
  bands, not in the membership rule. Renderers that want a "today" view
  filter on those fields rather than asking Backpack to mean "today."

## Alternatives considered

### A. Backpack as bounded recency window

A LRU-style window: the last N items written to the layer, oldest evicted.
Rejected: this loses the distinction between "recent and being carried" and
"recent but already done." A meeting from yesterday that's been actioned and
filed is not carry-state; an open commitment from three weeks ago is. Time
order doesn't capture this, and pretending it does produces the exact
overload the project is reacting against.

### B. Backpack as inbox

Everything new lands in Backpack; the operator sorts to Hoard or Doctrine
periodically. Rejected: this re-introduces the inbox problem the system
exists to avoid. The default state of an unsorted inbox is "full." Pathways
that need to drop something fast already have a target — Hoard — and Hoard
is correctly sized for that.

### C. Backpack as "what would I want on a fresh session?"

Closer to the chosen framing, but framed as a renderer concern rather than
a layer concern. Rejected as the *primary* definition because it conflates
membership rule (what's in the layer) with rendering rule (what gets shown
when). Renderers can and do filter Backpack further; that's
[ADR 0003](./0003-renderers-over-one-truth-layer.md). Membership comes
first.

## References

- [MANIFESTO.md](https://github.com/snackdriven/operator-core-mini/blob/main/MANIFESTO.md) — three-layer model.
- [docs/04-backpack-analysis.md](https://github.com/snackdriven/operator-core-mini/blob/main/docs/04-backpack-analysis.md) — upstream Backpack analysis.
- `schemas/backpack-item.schema.json` — the five memory classes.
- `schemas/freshness-policy.schema.json` — TTL bands for demotion.
- [docs/ingestion/05-promotion-demotion.md](../ingestion/05-promotion-demotion.md) — lifecycle operations.
- [scratch-pad/backpack.json](https://github.com/snackdriven/scratch-pad/blob/main/backpack.json) — the live file this decision is reacting to.
