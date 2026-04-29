# renderers/

Renderers are **pure projections** over Backpack + Doctrine. They never mutate
state, never write back to the operator root, and never invent fields. They
read the source files and produce a surface (text, markdown, JSON, etc.) for a
specific use case — a session primer, an ambient ticker, a daily brief.

This directory exists because of [ADR 0003 — Renderers over a one-truth
layer](../docs/decisions/0003-renderers-over-one-truth-layer.md). Rather than
forcing one canonical "what should be on screen right now" view, we keep the
substrate (Backpack + Doctrine + Hoard) as the source of truth and let
renderers compete for the operator's attention through their own selection
logic.

## Contract

Every renderer in this directory MUST:

1. **Read-only.** Never write, mutate, or delete files in the operator root.
   No side effects beyond stdout / the returned string.
2. **Declare an ID.** Set `RENDERER_ID = "<kebab-case-name>"`. This is what
   `renderer_hints.surfaces`, `renderer_hints.never_surface_in`, and consent
   policies' `applies_to_renderers` match against.
3. **Honor consent.** Before including a Doctrine or Backpack item, check
   whether any `kind: policy` Doctrine entry with a `consent` block forbids
   surfacing it on this renderer (by tag, scope, or `applies_to_renderers`
   listing this `RENDERER_ID`). Suppressed counts MAY be reported in aggregate
   ("3 items suppressed by consent gate") but suppressed items MUST NOT be
   named.
4. **Honor renderer hints.** Respect `renderer_hints.surfaces` (allowlist),
   `renderer_hints.never_surface_in` (denylist), `renderer_hints.priority`
   (sort key, higher first), and `renderer_hints.max_chars_in.<surface>` if
   present.
5. **Be idempotent.** Same inputs → same output, modulo the `--now` clock.
6. **Take the operator root as input.** A single positional argument pointing
   at a directory shaped like `examples/operator-root-fixture/`. Optional
   `--now ISO-8601` for deterministic time-dependent rendering.

## Currently shipped

| Renderer            | File                  | Purpose                                                  |
|---------------------|-----------------------|----------------------------------------------------------|
| `session-primer`    | `session_primer.py`   | Session-start markdown briefing: identity, pinned doctrine, what's near, what to verify. |
| `daily-brief`       | `daily_brief.py`      | Morning resumption surface: today's shape, near-today items, verify nudges, overnight diff. |
| `statusline`        | `statusline.py`       | Single-line ambient cue: date · top current item · today's event · stale count · private count. |
| `narrator-brief`    | `narrator_brief.py`   | Same facts as daily-brief, framed by an active voice-rule (skin) from Doctrine. Demonstrates ADR 0003's facts-stable / framing-adapts property. |

Shared loaders, the consent gate, and voice/routing-rule selection live in
`_common.py`. New renderers should import from there rather than re-implementing
frontmatter parsing or consent logic.

Run any renderer directly:

```bash
python renderers/session_primer.py examples/operator-root-fixture \
    --now 2026-04-29T14:00:00Z
python renderers/daily_brief.py    examples/operator-root-fixture --now 2026-04-29T14:00:00Z
python renderers/statusline.py     examples/operator-root-fixture --now 2026-04-29T14:00:00Z
python renderers/narrator_brief.py examples/operator-root-fixture --now 2026-04-29T14:00:00Z
python renderers/narrator_brief.py examples/operator-root-fixture --now 2026-04-29T14:00:00Z \
    --skin mass-effect
```

The fixture's expected outputs are committed alongside it as
`expected-session-primer.md`, `expected-daily-brief.md`,
`expected-statusline.txt`, `expected-narrator-brief.md`, and
`expected-narrator-brief.mass-effect.md`. `tools/test_renderers.py` diffs
actual against expected for every case and is invoked by
`tools/validate.py` so CI catches drift.

## Adding a renderer

1. Pick a kebab-case `RENDERER_ID` and create `renderers/<id>.py`.
2. Import shared helpers from `renderers/_common.py` (frontmatter loader,
   `consent_filter`, `applies_here`, `by_priority`, voice-rule and
   routing-rule selectors). Do not re-implement them.
3. Add an entry to the table above.
4. Add a fixture pass in `examples/operator-root-fixture/expected-<id>.md`
   (or appropriate extension) and a row in `tools/test_renderers.py:CASES`
   so CI catches accidental output drift.
5. If you need new fields on `renderer-hints.schema.json` or a new consent
   posture, write an ADR first — renderers should not push schema changes
   under the radar.

## Voice rules and routing rules

The narrator brief introduces two Doctrine kinds renderers can lean on:

- **`kind: voice-rule`** declares a tonal envelope (skin id, register,
  do/avoid lists, scope of renderers it applies to). Renderers pick one
  via `_common.select_voice_rule`. Multiple voice-rules can coexist; the
  highest-priority rule whose scope matches wins, with `--skin` and
  routing-rules overriding.
- **`kind: routing-rule`** declares conditional preferences (`when`,
  `prefer_renderer`, `narrator`, `tone`). The narrator brief consults
  `_common.select_routing_rule(when=energy)` to pick a skin when the
  operator passes `--energy low-energy` or similar. Routing rule
  conditions are matched by exact equality today; a richer predicate
  language is deferred until we have at least three live rules.

Both kinds are pure data — renderers consume them, never write to them.

## Consent gate banners (ADR 0004 follow-up)

When the consent gate fires (one or more items suppressed for this
renderer), the renderer MUST report it. Two helpers control the wording:

- `_common.consent_filter(items, doctrine, renderer_id)` returns a
  `gate_messages` list — one entry per *forbidding policy that actually
  fired*, with `{count}` already substituted. Each entry comes from the
  policy's `consent.gate_message` field, falling back to a generic
  count-only line when absent.
- `_common.consent_gate_short(doctrine, omissions, renderer_id)` returns
  the same set in compact form for ambient surfaces (e.g. statusline).
  Each entry comes from `consent.gate_message_short`, falling back to
  `"{count} private"`.

Rationale: the wording of a consent banner is a policy-level decision
("how do we want this surface to talk about its limits?"). Hard-coding
it in the renderer would either drift across renderers or drift across
operators. The schema lives in
[`schemas/doctrine-entry.schema.json`](../schemas/doctrine-entry.schema.json)
under `consent.gate_message` / `consent.gate_message_short`. Renderers
MUST NOT name suppressed items in either form.

## What renderers are NOT

- **Not a router.** Pathways decide what gets ingested into Backpack. Renderers
  decide what gets surfaced. They are different roles.
- **Not a cache.** A renderer's output is disposable. Re-run any time.
- **Not a UI framework.** Each renderer owns its own format. There is no
  shared layout engine on purpose — see ADR 0003.
- **Not a place to encode policy.** Consent posture, freshness bands, and
  scope rules live in Doctrine and `policy/`. Renderers read them; they
  don't define them.
