# Decisions

Lightweight Architecture Decision Records (ADRs) for the operator-core
substrate. Each entry captures a load-bearing choice, the alternatives that
were considered, and the consequences accepted in making it.

## Index

| # | Title | Status | Date |
|---|---|---|---|
| [0001](./0001-backpack-is-active-carry-state.md) | Backpack is active carry-state, not "recent memory" | Accepted | 2026-04-29 |
| [0002](./0002-doctrine-vs-hoard.md) | Doctrine and Hoard are different layers, not different views | Accepted | 2026-04-29 |
| [0003](./0003-renderers-over-one-truth-layer.md) | Renderers over one truth layer; not one truth per surface | Accepted | 2026-04-29 |

## How to add an ADR

1. Pick the next four-digit number (`0004-…`).
2. Use a short, declarative title — what was decided, in one line.
3. Follow the section structure of the existing ADRs:
   - **Status / Date / Deciders / Supersedes / Superseded by / Related**
   - **Context** — what made this decision necessary; what was unclear.
   - **Decision** — what was chosen, in normative language.
   - **Consequences** — split into Positive, Negative, Neutral.
   - **Alternatives considered** — A, B, C with brief rejection reasons.
   - **References** — links into the substrate, schemas, or upstream docs.
4. Keep ADRs short. If one approaches 10 KB, it probably contains two
   decisions; split it.
5. Update this index. Update any cross-references in sibling ADRs
   (`Related:` line at the top).
6. Don't edit accepted ADRs in place except for typos and broken links.
   To revisit a decision, write a new ADR that supersedes it; mark the
   old one `Superseded by: NNNN`.

## What belongs in an ADR

- Choices that constrain future implementations (schema shape, layer
  boundaries, write semantics).
- Choices that have a tempting but wrong alternative — the ADR exists
  partly to prevent re-introducing it.
- Choices that affect more than one repo or pathway.

## What doesn't belong

- Renderer styling, copy choices, voice-rule contents — those live in
  Doctrine.
- Implementation details (which library, which file format inside a
  layer) unless they have substrate-level consequences.
- Day-to-day operator preferences — those are personal Doctrine,
  not architectural decisions.
