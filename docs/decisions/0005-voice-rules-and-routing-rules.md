# ADR 0005 — Voice rules and routing rules are Doctrine, selected by contract

- **Status:** Accepted
- **Date:** 2026-04-29
- **Deciders:** operator-core-mini owner
- **Supersedes:** —
- **Superseded by:** —
- **Related:** [0003 — Renderers over one truth layer](./0003-renderers-over-one-truth-layer.md), [0004 — Consent posture is Doctrine](./0004-consent-posture-is-doctrine.md)

## Context

ADR 0003 established that the substrate carries one set of facts and many
renderers project them. The Phase 4 narrator brief ([renderers/narrator_brief.py](../../renderers/narrator_brief.py))
is the first surface that demonstrates the **facts-stable / framing-adapts**
property: the same fact bundle, rendered twice with different voices.

That demonstration leans on two existing Doctrine kinds:

- `kind: voice-rule` — declares a tonal envelope (skin id, register,
  do/avoid lists, scope of renderers it applies to).
- `kind: routing-rule` — declares conditional preferences (when, prefer\_renderer,
  narrator, tone) that select a voice or renderer based on state.

The schema for both has been in place since Phase 1, but the **selection
algorithm** — how a renderer at runtime picks which voice-rule applies, and
how routing-rules override the default — has lived only inside
`renderers/_common.py`. Without writing it down, every new renderer or skin
risks re-inventing a slightly different selection order, and we lose the
guarantee that two renderers asked for "the narrator skin right now" agree
on the answer.

We need a written contract.

## Decision

**Voice-rule and routing-rule selection is a contract enforced by
`renderers/_common.py`. All renderers MUST use that module's selectors;
they MUST NOT re-implement selection logic.**

The selectors are:

```python
select_voice_rule(doctrine, renderer_id, skin_override=None) -> dict | None
select_routing_rule(doctrine, when=None) -> dict | None
```

### Voice-rule selection order

When a renderer needs a voice, it MUST resolve in this order, stopping at
the first match:

1. **Caller override.** If the caller passes `skin_override` (e.g. via a
   `--skin` CLI flag), match by `voice.skin` exactly and return that
   rule. If no rule has that skin, return None — never silently fall back.
   Caller overrides are a deliberate operator action; downgrading them
   would hide drift.
2. **Routing-rule preference.** If the caller passes a state token (e.g.
   `--energy low-energy`), the renderer SHOULD first call
   `select_routing_rule(doctrine, when=state)`. If the matched
   routing-rule has `routing.narrator`, that skin is then resolved
   through step 1 against the routing-rule's chosen skin. If no
   routing-rule matches the state token, fall through to step 3.
3. **Default voice-rule.** Among `kind: voice-rule` entries whose
   `voice.scope` either contains `renderer_id` or is empty
   (applies-anywhere), select by:
   1. higher `renderer_hints.priority` first (default 50);
   2. on tie, prefer the rule with a non-empty `voice.scope` (more
      specific) over the applies-anywhere rule;
   3. on further tie, prefer the lexicographically smaller `voice.skin`
      so selection is deterministic.

If no voice-rule matches at any step, the renderer MUST render in a
documented neutral fallback skin (`renderers/narrator_brief.py`'s
`DEFAULT_SKIN = "neutral"`) rather than crash. The neutral skin's
templates live alongside the renderer; they are the renderer's
responsibility, not Doctrine's.

### Routing-rule selection order

`select_routing_rule(doctrine, when=...)` MUST:

1. Return None if `when` is None or empty.
2. Return the first `kind: routing-rule` whose `routing.when` equals
   `when` exactly (no predicate language today). Iteration order
   follows the Doctrine load order, which is filesystem-sorted; this is
   deterministic.
3. Never combine multiple routing-rules. A single state token resolves
   to at most one routing-rule; conflicts are written-down decisions, not
   merged at runtime.

A richer predicate language (boolean expressions over life-state) is
explicitly **deferred** until at least three live routing-rules exist.
Before then we'd be designing for hypothetical cases.

### Facts stability

A voice-rule MUST set `voice.facts_stable: true` (the schema default) for
its rendered output to be considered a valid projection. Renderers MUST
NOT alter the underlying fact bundle when applying a voice — only the
opener, section leads, and closer are skin-specific. The fact bundle
itself is the same one a non-voiced renderer (e.g. daily-brief) would
read for the same `now`.

If a future skin needs to drop or reorder facts, that's a different
renderer, not a voice-rule.

### Where templates live

Skin-specific opener / section-lead / closer strings live **inside the
renderer that consumes them** (e.g. `renderers/narrator_brief.py`'s
`SKIN_TEMPLATES`), not in Doctrine. Rationale:

- Templates are renderer-shaped. Two renderers consuming the same skin
  would still need different templates.
- Doctrine carries the *intent* of a voice (do/avoid, register); the
  renderer carries the *execution*.
- Putting templates in Doctrine would make adding a renderer require a
  Doctrine edit, which inverts the "renderers compete for attention"
  property of ADR 0003.

If a template needs to vary per operator (different opener phrasing per
person), that's a new field on the voice-rule schema, not a template-in-
Doctrine workaround.

## Alternatives considered

- **Letting each renderer pick its own selection algorithm.** Rejected:
  the whole point of voice-rules being Doctrine is that "the narrator"
  is one stable thing across surfaces. Per-renderer algorithms would
  reproduce the one-truth-per-surface trap ADR 0003 rejects.
- **Storing skin templates in Doctrine.** Rejected above.
- **Using a real predicate language for `routing.when`.** Deferred until
  three live rules exist. Premature DSLs are a known anti-pattern in
  this repo (see ADR 0002 on Doctrine vs Hoard's deliberate flatness).
- **Making `facts_stable` optional.** Rejected: the projection contract
  is meaningless without it. A "voice" that drops facts is a renderer
  with a bug.

## Consequences

**Positive.**

- One place — `_common.py` — to read or change selection logic.
- Adding a skin is a fixture/Doctrine edit plus an opener/closer template
  in the renderer; no selection code changes required.
- Two renderers asked for "the narrator skin right now" with the same
  state always get the same answer.
- `--skin` is honored as a real override, with explicit failure when no
  matching rule exists, instead of silently falling back to the default.
- `voice.facts_stable` is enforceable: golden tests can compare the
  fact-bundle portion of two voiced renders and require equality.

**Negative / costs.**

- Selection order is more rules to remember than "first one wins."
  Mitigation: it's encoded in `_common.py` and exercised by the
  golden tests under `examples/operator-root-fixture/`.
- Renderers that want bespoke selection logic now need an ADR amendment.
  This is by design; bespoke selection is what we are preventing.
- The neutral fallback skin lives in renderer code, not Doctrine, which
  splits "what voices exist" across two places. Acceptable until the
  fallback's behavior needs to vary by operator (it doesn't yet).

## Implementation notes

- Selectors are implemented in
  [`renderers/_common.py`](../../renderers/_common.py): `select_voice_rule`,
  `select_routing_rule`.
- The narrator brief is the reference consumer:
  [`renderers/narrator_brief.py`](../../renderers/narrator_brief.py).
- Golden tests in [`tools/test_renderers.py`](../../tools/test_renderers.py)
  cover the default-voice path and the `--skin mass-effect` override.
  Adding the `--energy low-energy` routing path is a follow-up once a
  second routing-rule exists in the fixture.
- A future Phase 4 follow-up: a renderer MAY assert that its fact
  bundle equals daily-brief's bundle for the same `now`, as a CI-time
  facts-stable check. Today this is enforced by inspection.
