# Shared state for the four renderer samples

All four sample renderers below read from the same hypothetical state on the
morning of **Wednesday, 2026-04-29, 09:00 CDT**. This file documents the inputs
so the "one truth layer, many renderers" claim is verifiable.

## Doctrine entries in scope

| id | kind | matters because |
|---|---|---|
| `user-profile` | identity | Identity, support style. |
| `writing-preferences` | default | Tone constraints across all surfaces. |
| `qa-bug-investigation-protocol` | workflow | Pinned to session-primer and dashboard. |
| `github-source-of-truth` | policy | Drives "verify before acting" framing. |
| `narrator-low-energy-routing` | routing-rule | Selects narrator skin if energy is low. |
| `team-roster` | evergreen-reference | Resolves names in renders. |

## Backpack state

Pinned: `default-bug-investigation-protocol`, `writing-preferences`,
`user-profile`, `github-source-of-truth`.

Current (today / yesterday — trust):
- `qa-queue-snapshot-2026-04-29` — 4 in-flight TTOAD tickets.
- `meetings-2026-04-29-q2-roadmap` — Q2 sync; replaces `meetings-2026-04-06-q2-roadmap`.
- `nhha-rcm-active-board-2026-04-29` — replaces `nhha-rcm-active-board-4-2`.

Recent (verify specifics):
- `ttoad-367-final-results` (dated 2026-04-22, ~7 days, TTL 1209600).
- `bug-referral-setup-2026-04-09` (TTL 604800 — **expired this morning**, flagged).

Timeline:
- `april-2026-timeline` — month rollup.

Evergreen:
- `team-roster`, `nhha-architecture`, `jira-boards`, `e2e-testing`.

Aged out overnight:
- `ttoad-221-discharge-filter-bug-2026-04-09` (TTL 604800, exceeded by 13 days). Demoted to Hoard.

## Life-state (consent-gated)

`weather-2026-04-29` (journal entry): sleep 6h, body 4/10, mood mild. One real
meeting today, otherwise async. `requires_consent: true`,
`ambient_only: true`. Only renderers with consent and ambient capability include
this; others MUST omit it.

## Renderer outputs in this folder

- `session-brief.sample.md` — assistant bootstrap context.
- `daily-brief.sample.md` — morning resumption surface.
- `narrator-brief.sample.md` — narrator-rendered version (Good Place skin).
- `narrator-brief.mass-effect.sample.md` — same facts, Mass Effect skin
  (proves facts-stable / framing-adapts: only the `voice-rule` differs).
- `statusline.sample.txt` — single-line ambient cue.
