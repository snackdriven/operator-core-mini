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
| `session-primer`    | `session_primer.py`   | Markdown briefing at session start: who you are, what's pinned, what's near, what to verify. |

Run any renderer directly:

```bash
python renderers/session_primer.py examples/operator-root-fixture \
    --now 2026-04-29T14:00:00Z
```

The fixture's expected output for the example clock above is committed at
`examples/operator-root-fixture/expected-session-primer.md` and serves as a
golden reference.

## Adding a renderer

1. Pick a kebab-case `RENDERER_ID` and create `renderers/<id>.py`.
2. Implement the contract above. Reuse `tools/validate.py`'s frontmatter
   loader pattern; do not introduce a new YAML dialect.
3. Add an entry to the table above.
4. Add a fixture pass in `examples/operator-root-fixture/expected-<id>.md`
   (or appropriate extension) so CI catches accidental output drift.
5. If you need new fields on `renderer-hints.schema.json` or a new consent
   posture, write an ADR first — renderers should not push schema changes
   under the radar.

## What renderers are NOT

- **Not a router.** Pathways decide what gets ingested into Backpack. Renderers
  decide what gets surfaced. They are different roles.
- **Not a cache.** A renderer's output is disposable. Re-run any time.
- **Not a UI framework.** Each renderer owns its own format. There is no
  shared layout engine on purpose — see ADR 0003.
- **Not a place to encode policy.** Consent posture, freshness bands, and
  scope rules live in Doctrine and `policy/`. Renderers read them; they
  don't define them.
