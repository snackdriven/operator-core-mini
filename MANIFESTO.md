# Manifesto

This body of work is not a pile of unrelated apps, dashboards, bots, trackers, or experiments. It is a long-running attempt to build a humane side-brain: a local, inspectable system that carries forward the right context, keeps important state visible, and returns reality in a form that can actually be used.[cite:1][cite:2][cite:32][cite:37][cite:156]

It is not fundamentally about productivity. It is about continuity with dignity.[code_file:213][code_file:214][cite:37]

## What this work is for

Too much important state has to be reconstructed by hand: work state, emotional state, body state, unfinished threads, project context, assistant context, and pattern memory all fall out of view unless something external holds them.[cite:1][cite:2][code_file:209][web:105]

The goal is to reduce that reconstruction cost. The system should make it easier to resume life and work without starting from zero whenever a day ends, a repo changes, a ticket gets interrupted, or an assistant session forgets what was already known.[cite:1][cite:2][web:105]

## The core model

The strongest current model is a three-layer memory ecology.[cite:1][code_file:213][web:105]

- **Backpack** — active carry-state: curated, freshness-aware, replace-in-place, small enough to trust.[cite:1]
- **Doctrine** — stable truths: defaults, identity, workflows, routing rules, and evergreen references.[cite:1][code_file:214]
- **Hoard** — deep archive: transcripts, notes, scraps, timelines, history, and artifacts.[cite:1][web:105]

Backpack protects against overload. Hoard protects against loss. Doctrine protects against drift.[cite:1][code_file:213]

## What keeps being solved for

- Reduce context loss and restart cost.[cite:1][cite:2][web:105]
- Preserve continuity across mood shifts, interruptions, bad brain days, and health fluctuations.[code_file:209][code_file:213][cite:37]
- Keep support ambient instead of punitive.[cite:2][code_file:214][cite:37]
- Make AI continuity local and inspectable rather than hidden and magical.[cite:32][web:105][web:228]
- Return reality in the voice most likely to make action possible.[code_file:212][code_file:213][code_file:214]

## What this repo should do

Operator Core should act as the design spine for future implementation work. The implementation repos should converge around this shared model rather than each inventing their own incompatible approach to continuity, memory, and adaptive rendering.[cite:1][cite:2][code_file:213][web:105]

The system being built is not one app to rule everything. It is a local operator environment with one truth layer and many gentle surfaces.[cite:1][cite:2][code_file:213]
