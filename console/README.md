# console/ — three-pane operator console (v0)

A scaffold of "The Console" from the brainstorm: command-palette-first dashboard
over an operator-root, with a live multi-renderer preview.

Ships with a **Carry** todo app at [`/carry`](static/carry/index.html), which
uses the same HTTP API to write `memory_class: expiring-tactical` backpack
items, pin them, and "complete" them by demoting to Hoard (where they live
forever — Hoard is write-once).

```
+------------------------------------------------------------------+
| operator console     energy [ ]  skin [ ]  now [ ]  ⌘K  status  |
+--------+------------------------+--------------------------------+
| tree   | editor                 | preview ([tabs])               |
| layer  |   <markdown w/         |   session-primer / daily-brief |
|  ...   |    yaml frontmatter>   |   / statusline / narrator-list |
|        |                        |   / narrator-brief             |
+--------+------------------------+--------------------------------+
```

## Run

Stdlib only on the server side; no pip installs required beyond what the
renderers already need (`pyyaml`).

```bash
python console/server.py                              # serves examples/operator-root-fixture
python console/server.py /path/to/your/operator-root  # serve any operator-root
python console/server.py /path/to/root --port 9000
```

Open `http://127.0.0.1:8765/` (or the port you passed). The todo app is at
`http://127.0.0.1:8765/carry`.

## Architecture

* **`server.py`** — stdlib `http.server.ThreadingHTTPServer`. Exposes:

  | endpoint            | method | purpose                                         |
  |---------------------|--------|-------------------------------------------------|
  | `/`                 | GET    | static SPA shell                                |
  | `/static/<path>`    | GET    | other static assets                             |
  | `/api/tree`         | GET    | substrate file tree by layer                    |
  | `/api/items`        | GET    | derived item list (id, freshness, TTL, stale…)  |
  | `/api/file`         | GET    | read a file (text)                              |
  | `/api/file`         | PUT    | write a file (atomic; tmp + `os.replace`)       |
  | `/api/render`       | POST   | run a renderer subprocess; return its stdout    |
  | `/api/verb`         | POST   | execute a substrate verb (`verbs.py`)           |

* **`verbs.py`** — the *only* code path that mutates files. v0 ships:

  | verb     | effect                                                              |
  |----------|---------------------------------------------------------------------|
  | `verify` | sets `created_at` on the matching item; resets TTL math             |
  | `pin`    | sets `freshness_class: pinned`                                      |
  | `unpin`  | reverts `freshness_class` to `current` (aging takes over)           |
  | `snooze` | resets `created_at`, ensures `ttl_seconds >= days*86400`. Defaults to 7d. |
  | `update` | edits mutable fields in place (v0: `summary` only)                  |
  | `demote` | stamps `aged_out_at`, moves the file to `hoard/YYYY/MM/DD/<name>.md`|

  All writes go through `atomic_write` (tempfile + `os.replace`) and respect
  the YAML frontmatter shape used by `renderers/_common.py:load_frontmatter`.
  Shared primitives live in [`tools/substrate.py`](../tools/substrate.py) so
  this module and the nightly TTL daemon ([`tools/expire.py`](../tools/expire.py))
  agree on what "expired" means and on how to perform a demote.

* **`static/index.html` + `style.css`** — 3-pane CSS-grid shell.

* **`static/app.js`** — file tree, editor (textarea, monospace, Tab-aware),
  ⌘S save, `now`/`energy`/`skin` controls. Re-runs the active renderer after
  every save and after every palette verb.

* **`static/palette.js`** — ⌘K command palette. Three input shapes:

  - `>verb [arg]` — verbs against an item id, plus `>render <id>`,
    `>skin <id>`, `>energy <level>`, `>now <iso>`.
  - `@today` / `@stale` / `@aged` / `@pinned` / `@area:work` — derived filters.
  - `#tag` — tag filter. Composes with `@filters` and free text.

  Anything else is a fuzzy substring search across `id`, `summary`, `path`,
  `area`, `freshness_class`, and `tags`.

## Killer feature

Edit any backpack file → save → all five renderer outputs re-render against the
new state. **One edit, five surfaces ripple.** This is "facts stable, framing
adapts" (ADR 0003) made tactile.

## Safety

* The server resolves every requested path against `operator_root.resolve()`
  and rejects anything that escapes it. No `..`, no absolute paths.
* Verbs only touch `backpack/` and `hoard/`; doctrine and policy are
  edit-via-editor only (no automated mutation in v0).
* Renderers are subprocessed; they remain pure (read-only) per ADR 0003.
* Bind defaults to `127.0.0.1`. Pass `--host 0.0.0.0` knowingly.

## Nightly TTL daemon

Carry items default to `ttl_seconds: 604800` (1 week). Without something
moving the cursor forward, expired items would just accumulate in `current/`
amber-tinted but never actually leave. [`tools/expire.py`](../tools/expire.py)
is that something:

```bash
python tools/expire.py /path/to/operator-root              # apply
python tools/expire.py /path/to/operator-root --dry-run    # preview only
python tools/expire.py /path/to/operator-root --verbose    # also list kept items
python tools/expire.py /path/to/operator-root --now ISO    # pin clock for tests
```

Behavior: walks `backpack/**/*.md` (skipping `_replaced/`); demotes items whose
`created_at + ttl_seconds < now`; never touches pinned items; never touches
items without `ttl_seconds`. Idempotent (second run does nothing).

Wire it into your existing `tools/weaver.py` schedule for nightly runs:

```python
import subprocess, sys
schedule.every().day.at("23:55").do(
    lambda: subprocess.run([sys.executable, "tools/expire.py", str(OP_ROOT)])
)
```

Or use cron / a launchd LaunchAgent / systemd timer — the script is plain CLI.

## Not yet wired (intentional v0 cuts)

* `>replace <id>` — drafts a successor file with `replaces:` set. Currently
  only the safe verbs ship; `replace` will land alongside a templated
  diff editor.
* CodeMirror / schema-aware editor. v0 uses a styled `<textarea>`. Frontmatter
  validation against `schemas/backpack-item.schema.json` is on the roadmap.
* Live FS watcher → push tree refreshes via SSE/WebSocket. Today the client
  re-fetches `/api/tree` and `/api/items` after every verb or save.
* Promote-to-doctrine, replaces-chain visualizer, consent-gate badge in tree.
* Snooze duration picker. Today snooze is fixed at 1 week from Carry; the
  underlying verb already accepts arbitrary `days`.

## Hotkeys

| key            | action                                |
|----------------|---------------------------------------|
| `⌘K` / `Ctrl+K`| open palette                          |
| `⌘S` / `Ctrl+S`| save current file                     |
| `Esc`          | close palette                         |
| `↑` / `↓`      | navigate palette results              |
| `Enter`        | run highlighted palette row           |

## Smoke test

```bash
python console/server.py examples/operator-root-fixture --port 8765 &
curl -s localhost:8765/api/tree | head -c 400
curl -s localhost:8765/api/items | head -c 400
curl -s -X POST localhost:8765/api/render \
     -H 'content-type: application/json' \
     -d '{"renderer":"daily-brief","now":"2026-04-29T14:00:00Z"}' | head
```
