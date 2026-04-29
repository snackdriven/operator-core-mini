# ADR 0004 — Consent posture is Doctrine, not infrastructure

- **Status:** Accepted
- **Date:** 2026-04-29
- **Deciders:** operator-core-mini owner
- **Supersedes:** —
- **Superseded by:** —
- **Related:** [0001 — Backpack is active carry-state](./0001-backpack-is-active-carry-state.md), [0002 — Doctrine vs Hoard](./0002-doctrine-vs-hoard.md), [0003 — Renderers over one truth layer](./0003-renderers-over-one-truth-layer.md)

## Context

Phase 3 ingestion docs repeatedly reference "consent gates" — places where a
pathway must check whether ingesting a particular kind of material is
permitted before writing to any layer. Examples:

- Health data must never enter the substrate from any pathway
  (medication names, provider names, lab results, mental-health session notes).
- Work-channel meeting transcripts may be ingested only when the meeting
  body explicitly opts in.
- The narrator vault is opt-out at file or path level: ingest by default,
  honor a `ingest: false` frontmatter key or a `_private/` path prefix.

Three places these consent gates could plausibly live:

1. **Hard-coded in pathway adapters.** Each adapter knows its own consent
   rules. Pro: simple. Con: invisible — the rules can drift between adapters,
   are not auditable in one place, and changing a rule requires changing
   code, not data.

2. **A separate `policy/consent.json` schema and aggregate file.** A new
   top-level schema and file dedicated to consent. Pro: explicitly named,
   easy to find. Con: introduces a fourth layer-ish concept (alongside
   Backpack/Doctrine/Hoard) that has to be loaded, indexed, and reasoned
   about by every renderer and every adapter. The system already has a
   layer for "stable, low-churn rules that govern behavior."

3. **A `consent` object on Doctrine `policy` entries.** Consent postures
   are themselves Doctrine: stable, low-churn, proposed-then-approved,
   keyed by id. The existing `policy` kind already covers
   "stable behavioral rules"; consent is a sub-kind of that.

## Decision

**Consent posture is encoded in Doctrine `policy` entries.** Adapters and
renderers consult Doctrine to learn the consent posture for a given scope;
they do not embed consent logic of their own.

Concretely:

1. **The `consent` object on `doctrine-entry.schema.json`** carries the
   posture. It is permitted only when `kind = "policy"`. Required fields:
   `scope` (e.g. `health-records`, `work-channel-transcripts`), `posture`
   (`opt-in` / `opt-out` / `forbidden` / `allow`). Optional: which
   pathways and which renderers it governs, what preconditions are required
   when posture allows ingestion, and a one-sentence rationale.

2. **Pathways read consent from Doctrine before writing.** Every adapter,
   before emitting an `ingested` event, queries Doctrine for policies whose
   `consent.applies_to_pathways` includes its own id. The first matching
   `posture = "forbidden"` MUST short-circuit the ingestion. An `opt-in`
   posture requires the adapter to confirm the explicit signal listed in
   `consent.requires` is present. An `opt-out` posture requires the
   adapter to honor the documented exclusion mechanism. `allow` requires
   nothing additional; it exists to make explicit that a scope was
   considered and gated open.

3. **Renderers read consent from Doctrine before exposing.** Even when
   material has already been ingested into Hoard or Backpack, renderers
   that surface it MUST consult Doctrine policies whose
   `consent.applies_to_renderers` matches their own id. This is the second
   line of defense — ingestion gates are not assumed perfect.

4. **Consent-violation rejections do not preserve source content.** When a
   pathway rejects ingestion on consent grounds, the resulting quarantine
   record MUST NOT contain the raw payload. Only the source pointer (e.g.
   calendar-event id) is retained for audit. This is a consequence of the
   policy itself: a quarantine that preserves the content would defeat
   `posture = "forbidden"`. See
   [examples/ingestion-trace/quarantine/01HW-EVT-0012-rejected.json](../../examples/ingestion-trace/quarantine/01HW-EVT-0012-rejected.json)
   for the worked example.

5. **Changing a consent posture is a Doctrine change.** It follows the
   same `doctrine-proposed` → operator approval → write path as any other
   Doctrine update (see
   [docs/ingestion/05-promotion-demotion.md](../ingestion/05-promotion-demotion.md)).
   No adapter or renderer can silently relax a posture.

## Consequences

### Positive

- **One place to audit consent.** Reading
  [examples/doctrine.sample.json](../../examples/doctrine.sample.json)
  shows every posture in effect. There is no second file or hidden
  adapter constant.
- **Posture changes are reviewable.** Tightening or relaxing a consent
  rule produces a Doctrine diff in `doctrine-proposals/` that the
  operator approves explicitly. Adapters cannot silently broaden their
  intake.
- **Renderers and pathways share the same vocabulary.** `posture`,
  `scope`, `requires` mean the same thing on both sides of the substrate.
  This is the same property that makes ADR 0003's "framing adapts, facts
  stable" claim hold for voice-rules; it now holds for consent too.
- **Reusing the existing `policy` kind costs almost nothing.** No new
  schema, no new aggregate file, no new index. The validation suite
  already covers `policy` entries.

### Negative

- **`policy` entries now carry behavioral semantics that some readers
  expect from code.** A reader who sees a Doctrine policy file might not
  realize that adapters and renderers actively consult it. This is
  documented in [CONTRIBUTING.md](../../CONTRIBUTING.md) and called out
  in `schemas/README.md`, but the surface area for misreading is real.
- **Consent enforcement now depends on adapters and renderers actually
  reading Doctrine.** A pathway that forgets to consult Doctrine ships a
  silent consent bypass. This is mitigated by Phase 4 renderers having
  the consent check as a shared library function (planned, not yet
  built); it is not eliminated.
- **The `policy` kind is now overloaded.** It carries both consent
  postures and other policy-flavored doctrine ("GitHub is the source of
  truth"). The schema permits but does not require the `consent` object,
  which may invite confusion. If the overload becomes painful, splitting
  out a dedicated `consent` kind is a small additive change to the enum;
  the data model would not move.

### Neutral

- The `consent` object is optional on `policy` entries. Existing
  policies that aren't about consent (e.g. `github-source-of-truth`)
  do not need to change.
- The four postures (`opt-in`, `opt-out`, `forbidden`, `allow`) are a
  closed enum. Adding a fifth (e.g. `delegated-to-third-party`) is a
  schema change, not a data change.

## Alternatives considered

### A. Hard-coded consent in pathway adapters

Rejected. Each adapter making its own decisions produces drift between
adapters and makes audit impossible. The system already chose Doctrine
as the home for stable behavioral rules; consent is one.

### B. Separate `policy/consent.json` schema and aggregate file

Rejected. This was the most plausible alternative and was the assumption
of the earlier "policy/consent.json schema gap" item in the gap audit.
The objection: a fourth top-level concept that every renderer and every
pathway must load is an over-correction. Doctrine already has `policy`
as a kind; consent fits there. If consent grows enough to dominate the
`policy` namespace, splitting it into its own kind on
`doctrine-entry.schema.json` is an additive change. Splitting into a
top-level schema/file is not — it would change ingestion and rendering
APIs.

### C. Encode consent only at the renderer layer

A "redact at output" model: ingest everything, redact at render time per
surface. Rejected for two reasons. (1) Some material — health records,
private vault entries — should not be in the substrate at all; redacting
at output assumes ingestion already happened, which is the failure case.
(2) Per-surface redaction multiplies consent rules across renderers and
re-introduces the drift problem this ADR exists to prevent.

### D. Encode consent only at the pathway layer

The dual of C. Pathways check consent; renderers don't. Rejected because
ingestion gates are imperfect — a pathway adapter could be added later
without consent checks, and the system needs defense-in-depth. Also,
some legitimate ingestions still need rendering-time gates (e.g. "this
is in Hoard for audit but never surface in shared screens"). Both layers
need to read the same posture.

## References

- `schemas/doctrine-entry.schema.json` — the `consent` object definition.
- [examples/doctrine.sample.json](../../examples/doctrine.sample.json) —
  the three worked consent policies (`consent-health-data`,
  `consent-work-transcripts`, `consent-narrator-vault`).
- [examples/ingestion-trace/quarantine/01HW-EVT-0012-rejected.json](../../examples/ingestion-trace/quarantine/01HW-EVT-0012-rejected.json)
  — consent-violation rejection with content deliberately not stored.
- [docs/ingestion/00-overview.md](../ingestion/00-overview.md) — universal
  ingestion contract; consent is one of its invariants.
- [ADR 0002 — Doctrine vs Hoard](./0002-doctrine-vs-hoard.md) — why
  Doctrine is the right home for low-churn stable rules.
- [ADR 0003 — Renderers over one truth layer](./0003-renderers-over-one-truth-layer.md)
  — same shape: renderers read shared rules, do not embed their own.

## Follow-ups

- **Doctrine-driven gate wording (2026-04-29).** The `consent` object now
  also accepts optional `gate_message` and `gate_message_short` template
  strings (with `{count}` substitution). Renderers SHOULD use them when
  a policy fires; otherwise they fall back to a generic count-only line.
  This keeps banner wording a policy-level choice instead of a renderer
  detail. Implementation: `renderers/_common.py:consent_filter` returns a
  `gate_messages` list, and `consent_gate_short` returns the compact form
  for ambient surfaces. The contract is documented in
  [renderers/README.md](../../renderers/README.md#consent-gate-banners-adr-0004-follow-up).

- **`backpack-item.scope` → `area` (2026-04-29).** The Backpack/Hoard
  enum field for lifecycle classification (work / life / assistant /
  identity / meta) was originally named `scope`, the same word the
  consent object uses for its free-string field (e.g. `health-records`).
  The two are unrelated concepts and never share values, but they shared
  a name, which led to a silently dead clause in the consent matcher
  (`policy.scope == item.scope` could never fire). The enum has been
  renamed to `area`. Consent matching is now unambiguously by tags.
  Migration script: [tools/rename_scope_to_area.py](../../tools/rename_scope_to_area.py).
  This is the resolution of follow-up #7 in
  [PLAN-followups-2026-04-29.md](../PLAN-followups-2026-04-29.md).
