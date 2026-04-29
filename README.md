# Operator Core

Operator Core is the documentation and design spine for a humane side-brain: a local, inspectable system that carries forward the right context, keeps important state visible, and returns reality in a form that can actually be used.[cite:1][cite:2][code_file:213][code_file:214][web:105]

It does not define a single monolithic app. It captures the throughline across existing projects such as `scratch-pad`, `qa-brain`, `narrator`, Backpack, life-state tools, and Claude continuity experiments, then defines the architecture those experiments suggest.[cite:1][cite:2][cite:32][cite:37][cite:156]

## What lives here

- `MANIFESTO.md` — high-level statement of purpose and what this body of work keeps solving for.[cite:1][cite:2][code_file:213]
- `docs/01-manifesto.md` — the longer manifesto, included in the docs set for internal continuity.[cite:1]
- `docs/02-system-architecture.md` — the Backpack / Doctrine / Hoard model and the role of renderers.[cite:1][code_file:210][code_file:214][web:105]
- `docs/03-repo-map.md` — how the known repos and clusters map onto the architecture.[cite:1][cite:2][cite:32][cite:37][cite:156]
- `docs/04-backpack-analysis.md` — detailed read of `backpack.json` and what it implies about working memory design.[cite:1]
- `docs/05-narrator-analysis.md` — how narrator, workspace-narrator, and the vault files fit into the system.[code_file:210][code_file:213][code_file:214]
- `docs/06-design-principles.md` — recurring philosophical and UX principles visible across the work.[cite:1][cite:2][code_file:214][cite:37]
- `docs/07-future-direction.md` — a practical direction for what to build next without losing the core philosophy.[cite:1][cite:2][web:4][web:105]

## Core idea

The strongest synthesis is a three-layer memory ecology plus multiple renderers.[cite:1][code_file:213][web:105]

- **Backpack** — active, curated, freshness-managed carry-state; what should stay near.[cite:1]
- **Doctrine** — stable truths, defaults, workflows, identity, and routing rules; what should stay true.[cite:1][code_file:214]
- **Hoard** — deep archive of transcripts, scraps, notes, history, and artifacts; what should stay kept.[cite:1][web:105]

Everything else — dashboards, narrators, Claude session bootstraps, statuslines, daily briefs, journals, and future UIs — are renderers over this substrate.[cite:1][cite:2][code_file:213][web:4]

## Status

Design and documentation only. The purpose of this repo is to save the synthesis so future implementation work has a clear North Star.[cite:1][cite:2][web:105]
