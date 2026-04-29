# Ingestion — Promotion, Demotion, Retirement

Once items exist in the substrate, they sometimes need to move between layers.
This doc specifies when and how that happens. It covers the cross-cutting
operations the four pathway docs reference but don't own.

## The four lifecycle operations

| Operation | Direction | Trigger |
|---|---|---|
| **Promotion** | Hoard → Backpack | Hoard summary becomes relevant to current work |
| **Replacement** | Backpack → Backpack `_replaced/` | New version of a current item |
| **Demotion** | Backpack → Hoard | Backpack item ages out without being touched |
| **Promotion to Doctrine** | Backpack → Doctrine (proposed) | A Backpack item proves stable for long enough |

There is no operation that moves things *out* of Hoard. Hoard is write-once.

## Promotion: Hoard → Backpack

### When

- Per pathway-specific rules. See:
  - [04-transcripts.md](./04-transcripts.md) — transcript-summary promotion rules.
  - [01-scratch-pad.md](./01-scratch-pad.md) — dashboard-manifest promotion rules.
- A user explicitly tags a Hoard item `tags: [promote]`.
- A scheduled "weekly carry-state review" (Phase 4 renderer concern, not
  covered here) suggests promotions; user accepts.

### How

1. New file at `backpack/<freshness>/<id>.md`.
2. Frontmatter `hoard_refs: [<hoard-id>]` set.
3. Hoard item's `promoted_to_backpack` field updated to the new Backpack id.
4. Index regenerated.
5. Event emitted: `kind: promote`, `from: hoard/<id>`, `to: backpack/<id>`.

### Constraints

- Promotion does not modify the Hoard item beyond setting
  `promoted_to_backpack`. The Hoard content is unchanged.
- Promoted items inherit `tags`, `people`, `projects` from the source.
- A single Hoard item can be promoted at most once. Re-promoting requires
  retiring the existing Backpack item first (see Replacement).

## Replacement: Backpack → Backpack `_replaced/`

### When

- A new version of an existing item is being written. This is the
  replace-in-place behavior expressed at the file system level.

### How

1. Pre-conditions: the new item's `replaces` field must point to the
   existing item's `id`.
2. The existing file is moved from its current freshness folder
   (`backpack/<freshness>/`) to `backpack/_replaced/`.
3. The moved file's frontmatter is updated: `freshness_class: removed`,
   `renderer_hints.never_surface_in: [dashboard, daily-brief, session-primer]`.
   Body is preserved verbatim. (This is the only sanctioned in-place
   modification of a Backpack file outside hand-edits.)
4. The new file lands at `backpack/<freshness>/<new-id>.md`.
5. Index regenerated.
6. Event emitted: `kind: replace`, `from: backpack/<old-id>`,
   `to: backpack/<new-id>`.

### Why move to `_replaced/` instead of deleting

Three reasons:

1. **Git history alone is fragile** — a renamed file's edit history can be
   broken by tooling. Keeping the file on disk preserves it explicitly.
2. **Search across `backpack/_replaced/`** is sometimes useful for "what
   did we believe last sprint?" answers without a full Hoard query.
3. **Auditability.** The retirement is visible without `git log`.

### When predecessors are NOT moved

If the predecessor was never written as a file (e.g. legacy `backpack.json`
migration with no per-file emission), the replacement is logged in the
event stream only. No phantom file is created.

## Demotion: Backpack → Hoard

### When

- A Backpack item has not been touched (no edit, no `replaces` chain
  extension, not pinned) for `freshness-policy.rules.demote_to_hoard_after_days`
  days. Default 60.
- Pinned items are NEVER auto-demoted. Removal of pinned status is a hand-
  edit by the user.

### How

1. The Backpack item's content + frontmatter is captured as a Hoard
   `imported-memory` record with `source.kind: import`,
   `source.ref: backpack/_replaced/<id>.md` (or the demotion path).
2. The Backpack file is moved to `backpack/_replaced/` with
   `freshness_class: removed` (same as replacement, but no successor exists).
3. Event emitted: `kind: demote`, `from: backpack/<id>`,
   `to: hoard/<new-id>`, `reason: aged-out` (or `reason: manual` if user-
   triggered).

### Demotion preserves continuity

Demotion is not deletion. The item remains accessible to Hoard search and
to renderers that explicitly include `_replaced/`. It just stops being
"near."

## Promotion to Doctrine (proposed-only)

### When

- A Backpack item with `memory_class: pinned-doctrine` or
  `evergreen-reference` survives unchanged for
  `freshness-policy.rules.promote_to_doctrine_after_days` days. Default 90.
- The user explicitly invokes "promote to doctrine."
- A narrator adapter detects a stable theme/identity assertion that
  belongs in Doctrine.

### How

This is the only lifecycle operation that does NOT execute automatically.

1. Adapter emits a `doctrine-proposed` event with a unified diff showing
   the proposed Doctrine entry.
2. The user reviews and accepts or rejects.
3. On accept: the new Doctrine entry is written, the source Backpack item's
   `doctrine_ref` field is set, and the Backpack item is left in place
   (Backpack still carries the working version; Doctrine carries the canonical).
4. Event emitted: `kind: promote-to-doctrine`, `from: backpack/<id>`,
   `to: doctrine/<id>`.

This deliberate friction is what protects Doctrine from drift.

## Pin / unpin

### When

- User wants an item to ignore freshness rules entirely.

### How

1. User edits `policy/freshness.json#pinned_keys` OR sets
   `freshness_class: pinned` on the item's frontmatter.
2. Index regeneration computes the union and persists it.
3. Event: `kind: pin` or `kind: unpin`.

Pinning does not change the item's `memory_class`. A pinned tactical item
is still tactical; pin just suppresses TTL-driven demotion.

## What never moves

- **Hoard items never leave Hoard.** Errata create new Hoard records that
  reference the original. The original is never altered.
- **Doctrine entries never demote to Backpack.** If a doctrine entry stops
  being true, it is marked `stability: deprecated` and remains. Removal is
  a manual deletion, logged via git.

## Index regeneration

Every lifecycle operation ends with index regeneration. The `bp build`
step (or equivalent) reads the per-file source of truth and rewrites:

- `backpack/_index.json`
- `doctrine/doctrine.lock.json`
- `hoard/_hoard.jsonl` (append-only; never rewritten)
- `hoard/_ingestion-events.jsonl` (append-only)

Renderers consume the indexes; ingestion never updates renderers directly.

## Event log: the audit trail

All lifecycle operations emit ingestion events to
`hoard/_ingestion-events.jsonl`. Each event validates against
`schemas/ingestion-event.schema.json`. The event log is the answer to
"why did this item appear / disappear?" without resorting to git
forensics.
