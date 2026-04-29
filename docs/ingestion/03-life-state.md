# Ingestion — life-state tools → Hoard (and Backpack, gated)

The life-state cluster — `inside-weather`, `margin`, `meat-suit`,
`dysfunction-center` — captures mood, body, executive function, and "internal
weather." Per
[docs/06-design-principles.md](https://github.com/snackdriven/operator-core-mini/blob/main/docs/06-design-principles.md):

> **Support over surveillance.** The goal is accompaniment, continuity, and
> reduced reconstruction cost, not punishment or gamified control.

Ingestion from life-state tools is the most careful pathway. Defaults bias
toward Hoard (preservation), not Backpack (active surfacing), and any flow
into Backpack is consent-gated per surface.

## What life-state tools contain

Verified against the connected repos:

- **inside-weather** — mood, habit, task tracker (SQLite + Drizzle, web UI).
- **margin** — chatbot that builds your journal while you talk (Python
  backend, JS frontend).
- **meat-suit** — zero-demand journaling companion for AUDHD/PDA brains
  (`meat_suit/`, `legacy/`, `data/`, design doc).
- **dysfunction-center** — executive dysfunction productivity platform.

Each owns its own database or filestore. The operator-core ingestion does NOT
take ownership of those stores. It reads exports.

## The three categories of life-state material

Different material gets different default handling:

| Category | Examples | Default destination | Default consent |
|---|---|---|---|
| **Internal weather** | morning energy, mood, body load, sleep, "spoons" | Hoard `journal-entry` | `requires_consent: true`, `ambient_only: true` |
| **Behavioral signal** | streak counts, missed habits, completed tasks | Hoard `log` | `requires_consent: true`, surface only on user request |
| **Self-narrative** | journal entries written through margin or meat-suit | Hoard `journal-entry` | `requires_consent: true`, never promoted automatically |

Note what's missing from this table: **none of these default into Backpack**.
Life-state lives in Hoard by default. Backpack inclusion is opt-in per item
or per pattern, never blanket.

## The four life-state adapters

### A. inside-weather adapter

**Source:** export from inside-weather's SQLite (`data.db` shape suggests
Drizzle migrations).

**Maps to:**
- Each mood/habit row → Hoard `journal-entry` with `scope: life`,
  `source.kind: journal`, `source.ref: inside-weather/<table>/<row-id>`.
- An optional **daily weather rollup** Hoard `journal-entry` keyed
  `weather-YYYY-MM-DD` summarizing sleep, mood, body load.
- **No Backpack write by default.**

**Opt-in to Backpack:** if the user has set
`policy/life-state-policy.json#promote_daily_weather: true`, the daily
rollup is also written to Backpack as id `weather-YYYY-MM-DD` with
`scope: life`, `requires_consent: true`, `ambient_only: true`,
`memory_class: expiring-tactical`, `ttl_seconds: 86400` (1 day —
expires by tomorrow morning's rollup).

### B. margin adapter

**Source:** journal text built incrementally during chat with margin.

**Maps to:**
- One Hoard `journal-entry` per session, with `content` = the journal text,
  `occurred_at` = session end, `source.kind: journal`,
  `source.ref: margin/<session-id>`.
- People mentioned in the journal become `people: [...]` entries.
- **No Backpack write. Ever, by default.** Margin's whole point is zero-
  demand journaling; auto-surfacing journal text in dashboards or session
  primers would defeat that.

**Opt-in to Backpack:** there is no blanket opt-in. If the user wants a
specific journal entry to be carried forward, they tag it explicitly
(`tags: [carry]`) and that single entry is written to Backpack with
`requires_consent: true`. There is no "promote all margin entries" mode.

### C. meat-suit adapter

**Source:** meat-suit's journal/data store (`data/`, `meat_suit/`).

**Maps to:**
- Each entry → Hoard `journal-entry`, `scope: life`,
  `source.kind: journal`, `source.ref: meat-suit/<entry-id>`.
- Body-state cues (e.g. "body 4/10", "pain spike", "fatigue heavy") become
  separate Hoard `note` entries with `tags: [body, signal]` so they are
  searchable but never aggregated into Backpack.
- **No Backpack write. No exceptions.** Meat-suit's premise is zero-demand;
  ingestion respects that absolutely.

A consequence: meat-suit material can be read by renderers only via Hoard
search, never via the Backpack index. Renderers are responsible for honoring
`requires_consent` and `ambient_only` even on Hoard reads.

### D. dysfunction-center adapter

**Source:** dysfunction-center's tracking store. Mixed: some entries are
behavioral (task done / missed) and some are self-narrative.

**Maps to:**
- Behavioral signals → Hoard `log`. Aggregations live in dysfunction-center's
  own UI; ingestion never aggregates here.
- Self-narrative entries → Hoard `journal-entry`, treated like margin.
- **No Backpack write.** Dysfunction-center owns its own surfacing; operator-
  core does not surface its data ambient.

## Consent gating: how it works in practice

`renderer-hints.requires_consent: true` does NOT mean "ask the user every
time." It means "do not include this item in a renderer's output unless the
renderer has been granted explicit consent for life-state surfacing."

Consent is per-surface, recorded in `policy/consent.json`:

```json
{
  "session-primer": { "life_state": false },
  "daily-brief":    { "life_state": true,  "scope": ["weather"] },
  "narrator":       { "life_state": true,  "scope": ["weather", "energy"] },
  "statusline":     { "life_state": false },
  "dashboard":      { "life_state": false }
}
```

Renderers consult this file before pulling life-state items from the index.
Ingestion only writes the items and the consent flag; renderers enforce.

The default config has `life_state: false` on every surface. The user opts
in surface by surface. There is no "global enable."

## What the adapters NEVER do

- They never aggregate mood data into a "score" or "trend" surfaced to
  another system. The number stays in inside-weather where the user looks at
  it on purpose.
- They never write a Backpack entry summarizing the user's "state" or
  "condition." There is no `today-i-am` Backpack key. That would be
  surveillance.
- They never feed life-state into narrator routing automatically. The
  `narrator-low-energy-routing` doctrine rule has to be explicitly bound by
  the user to a life-state tag for that to happen.
- They never expose life-state to Claude bootstraps unless the user has
  explicitly opted in. The session-primer renderer's default for
  `life_state` is `false`.

## Frontmatter defaults

```yaml
scope: life
source:
  kind: journal
renderer_hints:
  requires_consent: true
  ambient_only: true
  decay: fade
  never_surface_in: [statusline, session-primer, dashboard]
```

The `never_surface_in` list is set by the adapter and can be relaxed only
by editing the item by hand or by changing the policy file. Ingestion does
not relax it.

## Patterns vs. specifics

A pattern observed over weeks ("body load tends to be higher on Mondays")
is potentially useful. A specific data point ("body 4/10 today") is mostly
private. The adapters MUST NOT auto-derive patterns and write them anywhere;
pattern derivation is a separate, explicitly-invoked task that the user
runs when they want to look. This rule exists because automated pattern
derivation is the on-ramp to surveillance and the architecture refuses to
go there.

## Failure mode this pathway prevents

"You haven't logged your mood in 4 days" is not a feature operator-core
ingests, computes, or surfaces. Life-state tools may produce such reminders
themselves; that's their domain. Operator-core does not take such signals,
re-surface them, or route them through narrator. The architecture is for
**continuity with dignity**, not nagging.
