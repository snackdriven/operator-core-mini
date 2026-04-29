# Operator Core

This is the design documentation for a local, inspectable side-brain: something that carries the right context forward, keeps important state visible, and gives back reality in a usable form.

It's not a single app. It captures what's consistent across `scratch-pad`, `qa-brain`, `narrator`, Backpack, life-state tools, and Claude continuity experiments, then documents the architecture those experiments point toward.

## What lives here

- `MANIFESTO.md`: why this work exists and what it keeps trying to solve.
- `docs/01-manifesto.md`: the longer version, included for internal continuity.
- `docs/02-system-architecture.md`: the Backpack / Doctrine / Hoard model and how renderers fit in.
- `docs/03-repo-map.md`: how existing repos map onto the architecture.
- `docs/04-backpack-analysis.md`: a close read of `backpack.json` and what it implies for working memory design.
- `docs/05-narrator-analysis.md`: how narrator, workspace-narrator, and the vault files fit in.
- `docs/06-design-principles.md`: design and UX principles that show up consistently across the work.
- `docs/07-future-direction.md`: what to build next without losing the thread.

## Core idea

Three layers of memory, plus renderers on top.

- Backpack: active carry-state, freshness-managed. What stays near.
- Doctrine: stable truths, defaults, routing rules, identity. What stays true.
- Hoard: transcripts, scraps, notes, history, artifacts. What stays kept.

Dashboards, narrators, Claude bootstraps, statuslines, daily briefs, future UIs are all renderers over that substrate.

## Status

Documentation and design only. The point is to have the synthesis written down so future implementation has something real to aim at.
