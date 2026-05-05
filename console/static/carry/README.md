# Carry — todo app over the substrate

A small write-client that turns each todo into a real Backpack item, lives
on the same filesystem as the rest of the operator-root, and disappears
into Hoard (write-once, never deleted) when you check it off.

## What it is

Single-page web app served by [`console/server.py`](../../README.md) at
`http://<host>:<port>/carry`. No build step, no node_modules, no framework.
The file you're reading lives at `console/static/carry/README.md`; the app
is `index.html`, `carry.css`, and `carry.js` next to it.

Carry is *not* its own backend. It uses the console's HTTP API:

- `PUT /api/file?path=…` to create or rewrite an item file
- `POST /api/verb` for `pin` / `unpin` / `verify` / `snooze` / `update` / `demote`
- `GET /api/items` to read the current state (filters client-side to
  `tags` containing `todo`)

Anything Carry can do, the console can do. Carry is the ergonomic skin.

## Run it

```bash
python console/server.py [/path/to/operator-root] [--port 8765]
# open http://127.0.0.1:8765/carry
```

Defaults to `examples/operator-root-fixture/` when no path is given, so
the first run is instant and doesn't require a real operator-root.

## How a Carry todo lands in the substrate

Every "add" writes one Markdown file at
`backpack/current/<slug>-<YYYY-MM-DD>.md` with this frontmatter shape
(schema-clean against `schemas/backpack-item.schema.json`):

```yaml
---
id: pick-up-dry-cleaning-2026-05-05
freshness_class: current
memory_class: expiring-tactical    # TTL-managed, not journal-style
area: life                          # life | work | meta | assistant | identity
source:
  kind: manual
  ref: carry
dated: 2026-05-05
created_at: 2026-05-05T06:34:03Z
ttl_seconds: 604800                 # user picks 1d / 1w / 2w / 30d (default 1w)
tags:
  - todo
summary: pick up dry cleaning
renderer_hints:
  surfaces:
    - session-primer
    - daily-brief
    - narrator-list
    - narrator-brief
  priority: 50
---
2026-05-05 — pick up dry cleaning
```

Because the file is a real Backpack item, **`daily-brief`,
`session-primer`, `narrator-list`, and `narrator-brief` automatically pick
it up** — you'll see it under "Near today" in the daily brief without any
adapter. That's the "facts stable, framing adapts" property of ADR 0003.

## Interactions

| Action          | Verb / endpoint                          | Effect on disk                                                            |
|-----------------|------------------------------------------|---------------------------------------------------------------------------|
| Add (Enter)     | `PUT /api/file`                          | new file under `backpack/current/`                                        |
| Pin (`✦`)       | `POST /api/verb pin` / `unpin`           | sets `freshness_class: pinned`; pinned cards anchor at the top            |
| Click title     | `POST /api/verb update {summary}`        | edits `summary` in place, body untouched                                  |
| `still on it`   | `POST /api/verb verify`                  | resets `created_at` so TTL math starts over                               |
| `snooze`        | `POST /api/verb snooze {days: 7}`        | resets `created_at` + ensures `ttl_seconds ≥ 7d`                          |
| Done (`◯` → ✓)  | `POST /api/verb demote`                  | stamps `aged_out_at`, moves file to `hoard/YYYY/MM/DD/<basename>.md`      |

**Done is not delete.** Hoard is write-once per ADR 0002 and the manifesto
("Hoard protects against loss"). Completed todos remain on disk forever and
are findable via `read_hoard()`. Use `rm` if you actually want them gone.

## States the UI surfaces visually

| State                                     | Visual                                                |
|-------------------------------------------|-------------------------------------------------------|
| Pinned                                    | lavender border + filled `✦`, sorted to top           |
| Stale (`created_at + ttl_seconds < now`)  | amber border, `TTL expired` in the meta line, extra `still on it` button next to `snooze` |
| Just added                                | drop-in animation, status line says "added"           |
| Mid-completion                            | optimistic fade-out; row collapses then refreshes     |
| Editing the title                         | amber outline, `contentEditable` swap, Enter commits  |
| Bag over comfortable budget               | weight gauge in the header turns amber past 8 items   |

## Lifecycle: how Carry items leave on their own

Two paths out:

1. **You check it off.** `demote` verb. Immediate, intentional. Moves to
   `hoard/`.
2. **The TTL daemon sweeps it.** [`tools/expire.py`](../../../tools/README.md)
   walks `backpack/` nightly and demotes any item whose lease has expired.
   Pinned items are exempt; items without `ttl_seconds` are exempt.
   Idempotent. Wire it into `tools/weaver.py` or cron — see
   [`console/README.md`](../../README.md#nightly-ttl-daemon) for the
   one-line schedule entry.

Without the daemon running, expired Carry items just sit there glowing
amber. With it running, the bag self-curates while you sleep.

## What's intentionally minimal

- No notifications, no streaks, no due-by syntax, no recurring builder.
  Recurrence belongs in `doctrine/workflows/<id>.md` (`kind: workflow`),
  not in Carry. A future `>promote-to-recurring` verb will move a Carry
  todo into doctrine; Carry itself stays focused on "today's bag."
- No exclamation points, no streaks, no shame copy — per the fixture's
  `writing-preferences` doctrine and the manifesto's PDA-aware framing.
- The empty state reads `your bag is empty. nice.` because that's the
  honest correct response to an empty bag.

## What's not yet wired (intentional v0 cuts)

- Snooze duration picker. Currently fixed at 1 week from the UI; the
  underlying `snooze` verb already accepts arbitrary `days`.
- Tag chip filter / area filter chips on the Carry page.
- `>promote-to-recurring` verb (move to `doctrine/workflows/`).
- Multi-select / bulk verbs.

## File map

```
console/static/carry/
├── README.md       this file
├── index.html      DOM shell (3-region: header / form / list)
├── carry.css       warm dark palette, 1KB-ish, vars + 12 animations
└── carry.js        ~280 lines: API client, YAML emitter, render loop
```

Everything else Carry depends on lives outside this directory:

- `console/server.py` — HTTP server
- `console/verbs.py` — substrate mutation verbs
- `tools/substrate.py` — frontmatter I/O, `is_expired`, `demote_to_hoard`
- `tools/expire.py` — the nightly daemon (separate process)
- `schemas/backpack-item.schema.json` — the contract Carry's frontmatter
  satisfies; if you rename a field there, this app needs the same edit.
