# Backpack Analysis

## What Backpack is

The public `backpack.json` is a large JSON object functioning as a portable working-memory layer rather than a generic settings file or archival database.

It contains:
- pinned keys via `_config:pinned_keys`,
- TTL metadata via `_config:ttl`,
- tactical snapshots,
- evergreen references,
- freshness guidance,
- replacement chains,
- and dense natural-language operational summaries.

## What this implies

Backpack is optimized for active carry, not exhaustive preservation. It distinguishes between current, recent, contextual, historical, and evergreen material, and it instructs the system to verify old items before acting on specifics and to update stale entries in place.

This makes Backpack a practical working-memory model rather than a passive archive.

## Memory classes suggested by Backpack

| Class | Description |
|---|---|
| Pinned doctrine | Things that should stay surfaced or govern behavior. |
| Expiring tactical memory | Current snapshots, meeting context, bug investigations, release state. |
| Timeline memory | Sequenced situational context like month/week summaries. |
| Evergreen reference | Stable work facts, user profile, workflows, reference knowledge. |
| Replaceable truth | Entries that should be kept current rather than appended forever. |

## Why it matters

Backpack shows that the practical center of the system is not abstract memory storage but curated carry-state.

## Core lesson

The lesson of Backpack is that the system does not need to carry everything all the time. It needs to carry the right things, understand freshness, and remain editable by hand.
