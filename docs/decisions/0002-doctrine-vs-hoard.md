# ADR 0002 — Doctrine and Hoard are different layers, not different views

- **Status:** Accepted
- **Date:** 2026-04-29
- **Deciders:** operator-core-mini owner
- **Supersedes:** —
- **Superseded by:** —
- **Related:** [0001 — Backpack is active carry-state](./0001-backpack-is-active-carry-state.md), [0003 — Renderers over one truth layer](./0003-renderers-over-one-truth-layer.md)

## Context

Backpack has a clear membership rule (see ADR 0001). The remaining two
layers — Doctrine and Hoard — are easier to confuse, because both are
"things kept around long-term." Several reasonable-sounding designs
collapse them:

- "Doctrine is just curated Hoard." Promote anything stable enough; tag the
  rest as raw.
- "Hoard with a `doctrine: true` flag." One physical store, two logical
  views.
- "Wiki + journal." Doctrine becomes a wiki; Hoard becomes a journal.

Each of these would simplify the implementation. Each would also break a
property the substrate depends on. This ADR records why the layers stay
physically and semantically separate.

The three properties that matter:

1. **Doctrine is dense and small; Hoard is sparse and large.**
   `examples/doctrine.sample.json` shows ~7 entries covering identity,
   defaults, workflows, and routing. `examples/hoard-sample.jsonl` is
   already heterogeneous across 9 record kinds and is intended to grow
   without bound. Renderers that read Doctrine read most of it every time;
   renderers that read Hoard always filter heavily. Treating them the same
   means either Doctrine bloats or Hoard reads slow down.

2. **Doctrine changes are proposed; Hoard writes are reflexive.** Doctrine
   defines what is true *for the operator* — names, defaults, workflows,
   routing. Editing it casually is how the system loses trust in itself.
   Adapters MUST emit `doctrine-proposed` events with diffs; the operator
   approves before the file changes
   (see [docs/ingestion/02-narrator.md](../ingestion/02-narrator.md)).
   Hoard writes are append-only and require no approval — the whole point
   of Hoard is that capture is cheap and lossless.

3. **Doctrine is the basis for narrator skin; Hoard is the basis for
   recall.** The narrator brief in `examples/renders/narrator-brief.sample.md`
   reads identity, voice rules, and routing from Doctrine. Recall ("what
   was that meeting from three weeks ago?") reads Hoard. These two reads
   have completely different shapes: Doctrine is keyed-and-known, Hoard is
   queried-and-found.

The decision below treats those three properties as load-bearing.

## Decision

**Doctrine and Hoard are distinct layers** with different schemas,
different storage, different write semantics, and different read patterns.
They are not views over a shared store, and they are not unified by tag.

Specifically:

1. **Schemas are separate.** `schemas/doctrine-entry.schema.json`
   defines Doctrine's required fields; Hoard items reuse
   `schemas/backpack-item.schema.json` (per follow-up #3, 2026-04-29:
   the optional `aged_out_at` field marks an item as aged-out into
   Hoard, while Backpack items live without it). The doctrine schema
   and the backpack-item schema define disjoint required fields, so
   crossing between layers still requires explicit transformation, not
   a flag flip.

2. **Doctrine has seven kinds; Hoard has eleven (and counting).** The
   Doctrine kinds (`identity`, `defaults`, `workflow`, `routing-rule`,
   `voice-rule`, `evergreen-reference`, `team-roster`/`jira-boards` as
   evergreen-reference variants) are the full taxonomy and grow only
   through deliberate schema change. The Hoard kinds — transcript, scrap,
   summary, screenshot, log, and so on — are an open set.

3. **Storage is layer-specific.** Doctrine lives in `doctrine/<kind>/<id>.md`
   with frontmatter. Hoard lives in `hoard/YYYY/MM/DD/<id>.md` (also
   markdown with frontmatter, per follow-up #3, 2026-04-29) plus a
   generated `_hoard.jsonl` index. Indexes regenerate independently. A
   renderer that reads only Doctrine never touches Hoard's directory
   tree, and the inverse holds.

4. **Doctrine writes are user-mediated. Hoard writes are not.** Adapters
   that detect potential Doctrine changes emit
   `kind: doctrine-proposed` ingestion events with diffs and an evidence
   pointer to the Hoard items that motivated the proposal. The operator
   approves; only then does the Doctrine file change. Hoard adapters
   write the moment they have a validated record.

5. **Doctrine never demotes; Hoard never promotes itself.** Doctrine
   entries are retired (frontmatter `status: retired`, file kept). Hoard
   items are promoted to Backpack by the rules in ADR 0001 and
   [docs/ingestion/05-promotion-demotion.md](../ingestion/05-promotion-demotion.md);
   they are not promoted to Doctrine directly. Doctrine-from-Hoard goes
   through Backpack first, and only if it stabilizes there.

## Consequences

### Positive

- **Trust in Doctrine is preserved.** The operator can read a Doctrine
  entry and rely on it without guessing whether some adapter quietly
  rewrote it overnight. Every change has an event, a diff, and an
  approval.
- **Hoard stays cheap to write.** Capture-everything is a viable strategy
  for Hoard precisely because no review gate sits between the adapter and
  the file system.
- **Renderers stay simple.** Each renderer states which layers it reads.
  None has to disambiguate "is this stable enough to be Doctrine?" at
  render time — that question is answered at write time, in advance.
- **Provenance is recoverable.** Because Doctrine changes are proposed
  with evidence (Hoard ids), it's always possible to reconstruct the
  reasoning behind a Doctrine entry from its history.

### Negative

- **Two physical stores must stay coherent.** A Doctrine entry referring
  to a project name and a Hoard transcript referring to the same project
  can drift. Mitigation: cross-references use stable ids, and
  `bp build` lints for orphaned references.
- **Some content is genuinely on the boundary.** "How I run a Q2 roadmap
  sync" might be a workflow (Doctrine) or a transcript summary (Hoard) or
  both. The convention: Hoard captures the specific instance; Doctrine
  captures the pattern only after multiple instances exist. Operator
  decides; nothing is automatic.
- **Operator overhead at the Doctrine boundary.** Approving proposed
  changes is real work. The mitigation is that there should be very few
  such proposals — Doctrine grows slowly. If proposals are arriving
  weekly, an adapter is over-eager and needs a stricter trigger.

### Neutral

- The two layers can be backed up, version-controlled, and synced
  independently. This is mostly a convenience but does occasionally
  matter (e.g. a corrupted Hoard day file does not threaten Doctrine).

## Alternatives considered

### A. One physical store, view-typed

Single `entries/` directory; each file has `layer: doctrine | hoard`.
Renderers filter on the field. Rejected: collapses the write-semantics
distinction. There is no clean way to enforce "this write needs operator
approval" when the path is the same as an unmoderated write. The flag
becomes advisory and silently rots.

### B. Hoard with a "stable" tag

Hoard is the truth; Doctrine is `tags: [stable, doctrine]` over Hoard.
Rejected: a stable record is still a record of a moment. Doctrine entries
are not snapshots — they are operator-asserted invariants. The narrator
skin does not say "as of 2026-03-12 your name was Kayla"; it says "your
name is Kayla." Different semantics need different physical homes.

### C. Doctrine as a wiki

Markdown wiki linked from Hoard. Rejected: wikis don't validate. The
operator wants Doctrine entries to enforce shape (workflows have steps,
team-roster has members, voice-rule has scope). Schemas are the cheapest
way to keep that shape; a wiki gives them up.

### D. Hoard subsumes Doctrine via "summary of summaries"

Iteratively summarize Hoard into stable beliefs. Rejected: this is in the spirit of the
[deprecated chronicle branch](https://github.com/snackdriven/operator-core-mini/blob/main/docs/03-repo-map.md)
and what the upstream docs already chose against. Summary chains
are lossy and untrustworthy in subtle ways; operator-asserted Doctrine
isn't.

## References

- [docs/02-system-architecture.md](https://github.com/snackdriven/operator-core-mini/blob/main/docs/02-system-architecture.md) — upstream three-layer model.
- [docs/03-repo-map.md](https://github.com/snackdriven/operator-core-mini/blob/main/docs/03-repo-map.md) — chronicle history (the rejected unification).
- `schemas/doctrine-entry.schema.json`, `schemas/backpack-item.schema.json` (now also covers Hoard items per follow-up #3, 2026-04-29).
- [docs/ingestion/02-narrator.md](../ingestion/02-narrator.md) — Doctrine-proposed gating.
- [docs/ingestion/05-promotion-demotion.md](../ingestion/05-promotion-demotion.md) — lifecycle.
