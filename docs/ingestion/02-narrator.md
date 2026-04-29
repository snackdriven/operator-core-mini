# Ingestion — narrator / workspace-narrator → Doctrine (and Backpack)

Narrator and workspace-narrator contribute the interpretation layer. Per
[docs/05-narrator-analysis.md](https://github.com/snackdriven/operator-core-mini/blob/main/docs/05-narrator-analysis.md),
narrator is a renderer, not the center. Ingestion from narrator sources
therefore feeds primarily **Doctrine** (stable identity, routing rules,
narrator definitions, theme casts) and only secondarily **Backpack** (current
active-theme state, today's narrator selection).

## What narrator sources contain

Per [CITATIONS.md](https://github.com/snackdriven/operator-core-mini/blob/main/CITATIONS.md):

**narrator repo:**
- `README.md` — framing
- `narrator_system_design.md` — lens / world-state / dynamic label model
- `Kayla_Memory_Vault_v1.0.2.md` — HUD rules, active theme casts, passive cueing
- `Narrators.md` — narrator role definitions
- `Health_Log.md` — health context (see gating notes below)
- theme files (Borderlands, Emperor's New Groove, Fallout, Futurama,
  Mass Effect, Max Headroom, Spongebob, The Good Place)

**workspace-narrator repo:**
- `AGENTS.md` — runtime boundaries
- `HEARTBEAT.md` — liveness signal
- `IDENTITY.md` — identity facts
- `SOUL.md` — voice and values
- `TOOLS.md` — tool inventory
- `USER.md` — user profile

## Split rule: Doctrine vs. Backpack

The narrator system holds two different kinds of information, and they belong
in different layers:

| Narrator information | Layer | Reason |
|---|---|---|
| Identity, user profile, voice, values, narrator role definitions, theme casts, routing rules | **Doctrine** | Low-churn, cross-session, pinned. |
| Today's active theme, today's active narrator, HUD state, current mood routing result, ephemeral dynamic labels | **Backpack** | Current, replace-in-place, freshness-aware. |
| Raw theme files imported verbatim, session-level narrator transcripts, heartbeat logs | **Hoard** | Preserves provenance, allows theme-file diffs over time. |

The anti-pattern Phase 3 guards against: dumping the entire narrator vault
into Backpack. That would flood active carry-state with evergreen material
and defeat the whole "small enough to trust" discipline.

## The four narrator adapters

### A. Identity / USER.md / user-profile adapter

**Source:** `workspace-narrator/USER.md`, `workspace-narrator/IDENTITY.md`,
narrator repo's user profile sections.

**Maps to a single Doctrine entry:**

```yaml
id: user-profile
kind: identity
pinned: true
stability: stable
```

If the source changes, this is treated as a Doctrine update. Because
Doctrine is low-churn, the adapter does NOT write directly. It emits a
`doctrine-proposed` event with a diff; the user approves or rejects. On
approval, the adapter writes `doctrine/identity/user-profile.md` with the
new body and bumps `updated_at`. Prior versions remain in git history.

Writing preferences, support-style notes, and PDA/AUDHD-aware cues from
`USER.md` go into separate entries:

- `doctrine/defaults/writing-preferences.md`
- `doctrine/defaults/support-style.md`

Keeping them independent lets routing rules target one without reloading all.

### B. Narrator role adapter (`Narrators.md`)

**Source:** `Narrators.md` — one entry per narrator role (e.g. `critical`,
`warm`, `comic`, `analytic`, `low-demand`).

**Maps to Doctrine entries of kind `routing-rule` OR `evergreen-reference`:**

- Each narrator role becomes a `doctrine/narrators/<role>.md` with
  `kind: evergreen-reference`. The body is the role definition.
- Cross-cutting routing rules (e.g. "on low-energy days prefer warm over
  critical") are extracted to separate `doctrine/routing/<rule>.md` entries
  of `kind: routing-rule` with a populated `routing` block.

**Role first, skin second.** Per
[docs/07-future-direction.md](https://github.com/snackdriven/operator-core-mini/blob/main/docs/07-future-direction.md),
narrator routing is role-first. That means the adapter MUST emit routing
rules keyed on role (`warm`, `comic`), not on theme skin (`good-place`,
`borderlands`). Theme skins apply on top of selected roles; see theme adapter
next.

### C. Theme adapter

**Source:** theme files (Borderlands, Emperor's New Groove, Fallout, Futurama,
Mass Effect, Max Headroom, Spongebob, The Good Place).

**Maps to:**
- One `doctrine/themes/<theme>.md` per theme with
  `kind: evergreen-reference`. Body is the theme cast, vocabulary, and
  skin-specific labeling rules.
- A single `doctrine/themes/_index.md` with `kind: evergreen-reference`
  listing available themes so routing rules can enumerate.
- The **raw theme file** is also captured to Hoard as
  `kind: imported-memory` with `source.kind: narrator` so historical diffs
  survive if a theme is retired.

**What the theme adapter does NOT do:** it does not write anything to
Backpack. Today's active theme is an instruction from the user, not an
ingestion result; see the HUD-state adapter next.

### D. HUD-state / Memory Vault adapter

**Source:** `Kayla_Memory_Vault_v1.0.2.md` (or current version),
`workspace-narrator/HEARTBEAT.md`.

**Maps to:**

The Memory Vault is a mixed document: pinned HUD rules + time-aware active
state + passive cueing logic. The adapter SPLITS it:

- **Pinned HUD rules** (how HUDs should behave, passive cueing grammar) →
  `doctrine/hud/*.md` with `kind: policy`.
- **Current active theme cast** (today's selected narrator + theme) →
  one Backpack item: id `narrator-active-state`,
  `memory_class: replaceable-truth`, `scope: assistant`,
  `ttl_seconds: 86400` (1 day — HUD state expires daily and must be
  re-asserted). `replaces` chain the predecessor each day.
- **Heartbeat payloads** → Hoard `log` records. Never Backpack.

The vault doc is large and changes across versions; the adapter emits one
`vault-version-imported` event per ingestion and the full file goes to Hoard
as `kind: imported-memory` so diffs across vault versions remain inspectable.

## Health_Log.md — special case

Narrator's `Health_Log.md` contains health-adjacent material. Per the
design principle "support over surveillance," this file is treated under the
**life-state rules** in [03-life-state.md](./03-life-state.md), not under
narrator rules. Specifically:

- It is captured to Hoard with `requires_consent: true` and
  `ambient_only: true`.
- It is NEVER promoted to Backpack by narrator ingestion.
- It does NOT feed narrator routing automatically; if the user wants narrator
  routing to adapt to health state, they explicitly enable the
  `narrator-low-energy-routing` doctrine rule's bindings to life-state tags.

## Runtime-boundary file handling (AGENTS.md, SOUL.md, TOOLS.md)

These files specify *how narrator should behave at runtime*. They are
Doctrine, not Backpack.

- `AGENTS.md` → `doctrine/policy/agent-runtime-boundaries.md`, `kind: policy`
- `SOUL.md` → `doctrine/identity/voice-values.md`, `kind: identity`
- `TOOLS.md` → `doctrine/reference/narrator-tools.md`, `kind: evergreen-reference`

## Doctrine-proposed gate (why automated writes to Doctrine are dangerous)

Doctrine protects against drift. An adapter that silently rewrites doctrine
entries as source files change will produce exactly the drift the layer
exists to prevent. Therefore, narrator adapters:

- MUST emit `doctrine-proposed` events containing a unified diff of the
  proposed change.
- MUST NOT write to `doctrine/` directly unless the target entry has
  `stability: evolving` set AND an `applies_to` list restricting its scope.
- MUST produce a rejection note in the event stream for any change that
  would alter an entry with `stability: stable`.

This turns Doctrine updates into a review step. In practice the reviewer is
the user, and review can be as lightweight as glancing at the diff and
clicking accept. The important thing is that doctrine never changes silently.

## Frontmatter defaults for narrator-sourced items

```yaml
source:
  kind: narrator
  ref: <path within narrator repo or workspace-narrator repo>
tags: [narrator, <role>, <theme>]
```

Doctrine entries from narrator sources additionally set
`applies_to: [narrator]` unless the entry is cross-cutting (e.g.
`writing-preferences`, which applies broadly).

## Idempotency and replay

- Theme files are content-addressed by `sha256`. Re-importing an unchanged
  theme is a no-op.
- Memory Vault ingestion keys on vault version string in the filename. New
  version = new ingestion; old version's Hoard record is preserved.
- `narrator-active-state` in Backpack keys on the date; one entry per day.

## What this pathway does NOT do

- It does not cause renderers to switch narrators. Ingestion writes Doctrine
  and Backpack; renderers read them. Switching a narrator is a user action
  that writes a new `narrator-active-state` entry.
- It does not import past conversation transcripts voiced by a narrator.
  Transcripts go through [04-transcripts.md](./04-transcripts.md).
- It does not pull from workspace-narrator's `HEARTBEAT.md` to power
  renderer statuslines. Statuslines are renderers; they read
  `narrator-active-state` plus current Backpack, not the raw heartbeat.
