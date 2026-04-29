# System Architecture

## Core model

The clearest synthesis is a three-layer memory ecology plus multiple renderers.

| Layer | Purpose | Key traits |
|---|---|---|
| **Backpack** | Active carry-state for current reality. | Curated, freshness-aware, replace-in-place, assistant-readable, small enough to trust. |
| **Doctrine** | Stable truths, defaults, workflows, identity, routing rules, and evergreen references. | Persistent, pinned, low-churn, cross-session. |
| **Hoard** | Deep archive of transcripts, scraps, notes, timelines, artifacts, and history. | Append-heavy, searchable, indexable, not required to be tidy. |

This architecture works because it separates three different jobs: what should stay near, what should stay true, and what should stay kept.

## Why this split matters

Backpack protects against overload by keeping the active carry-state small and current. Doctrine protects against drift by preserving stable truths, identity, workflows, defaults, and routing rules across sessions. Hoard protects against loss by allowing the system to keep far more than should ever be carried day to day.

Without this split, the system collapses into sludge: too much current context, too much stale context, too many hidden assumptions, and no clear distinction between immediate truth and deep history.

## Renderers

The center should not be a monolithic app. It should feed multiple surfaces.

- Dashboard renderer, descended from `qa-brain`, for work-state and ambient visibility.
- Narrator renderer, descended from `narrator` and `workspace-narrator`, for adaptive emotional framing.
- Claude bootstrap / buddy renderer, for session continuity and context loading.
- Statusline renderer, for small ambient cues inside Claude Code or terminal workflows.
- Daily brief renderer, for morning/evening resumption.
- Journal / weather renderer, for life-state and internal weather.

## Proposed flow

A healthy future system would probably work like this:

1. Raw notes, transcripts, artifacts, logs, and imported context go into Hoard by default when they are worth preserving but not worth carrying.
2. Stable truths, recurring defaults, narrator routing, identity, and workflow principles live in Doctrine.
3. A smaller active subset is promoted into Backpack when it matters for current work, life, or assistant continuity.
4. Renderers read from the appropriate layer: Backpack first, Doctrine second, Hoard only when retrieval is needed.

## Design rules

- One truth layer, many renderers.
- Facts stay stable; framing can adapt.
- Carry-state should be curated, not exhaustive.
- Archive should be searchable, not required to be tidy.
- Local ownership and editability are non-negotiable.
