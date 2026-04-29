# System Architecture

## Core model

The clearest synthesis is a three-layer memory ecology plus multiple renderers.[cite:1][code_file:213][web:105]

| Layer | Purpose | Key traits |
|---|---|---|
| **Backpack** | Active carry-state for current reality. | Curated, freshness-aware, replace-in-place, assistant-readable, small enough to trust.[cite:1] |
| **Doctrine** | Stable truths, defaults, workflows, identity, routing rules, and evergreen references. | Persistent, pinned, low-churn, cross-session.[cite:1][code_file:210][code_file:214] |
| **Hoard** | Deep archive of transcripts, scraps, notes, timelines, artifacts, and history. | Append-heavy, searchable, indexable, not required to be tidy.[cite:1][web:105] |

This architecture works because it separates three different jobs: what should stay near, what should stay true, and what should stay kept.[cite:1][code_file:213]

## Why this split matters

Backpack protects against overload by keeping the active carry-state small and current.[cite:1] Doctrine protects against drift by preserving stable truths, identity, workflows, defaults, and routing rules across sessions.[cite:1][code_file:214] Hoard protects against loss by allowing the system to keep far more than should ever be carried day to day.[cite:1][web:105]

Without this split, the system collapses into sludge: too much current context, too much stale context, too many hidden assumptions, and no clear distinction between immediate truth and deep history.[cite:1]

## Renderers

The center should not be a monolithic app. It should feed multiple surfaces.[cite:1][cite:2][code_file:214]

- Dashboard renderer, descended from `qa-brain`, for work-state and ambient visibility.[cite:2]
- Narrator renderer, descended from `narrator` and `workspace-narrator`, for adaptive emotional framing.[code_file:213][code_file:214]
- Claude bootstrap / buddy renderer, for session continuity and context loading.[cite:32][web:105]
- Statusline renderer, for small ambient cues inside Claude Code or terminal workflows.[web:4][web:199]
- Daily brief renderer, for morning/evening resumption.[cite:1][code_file:210]
- Journal / weather renderer, for life-state and internal weather.[cite:37][code_file:209]

## Proposed flow

A healthy future system would probably work like this:

1. Raw notes, transcripts, artifacts, logs, and imported context go into Hoard by default when they are worth preserving but not worth carrying.[web:105][cite:1]
2. Stable truths, recurring defaults, narrator routing, identity, and workflow principles live in Doctrine.[cite:1][code_file:214]
3. A smaller active subset is promoted into Backpack when it matters for current work, life, or assistant continuity.[cite:1]
4. Renderers read from the appropriate layer: Backpack first, Doctrine second, Hoard only when retrieval is needed.[cite:1][code_file:213][web:105]

## Design rules

- One truth layer, many renderers.[cite:1][cite:2][code_file:213][web:105]
- Facts stay stable; framing can adapt.[code_file:213]
- Carry-state should be curated, not exhaustive.[cite:1]
- Archive should be searchable, not required to be tidy.[web:105][cite:1]
- Local ownership and editability are non-negotiable.[cite:1][web:105]
