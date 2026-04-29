---
event_id: 01HW-EVT-0009
proposed_at: 2026-04-29T16:00:00Z
adapter: narrator.user-profile
target_layer: doctrine
target_id: user-profile
target_path: doctrine/identity/user-profile.md
status: proposed
evidence:
  - 01HW4Z9D0E1F2G3H4I5J6K7L8M  # session-summary mentioning post-wedding context
  - workspace-narrator/USER.md
review_due_by: 2026-05-06T16:00:00Z
---

# Proposed Doctrine change: `user-profile`

The `narrator.user-profile` adapter detected that `workspace-narrator/USER.md`
was updated and the diff falls inside a Doctrine entry. Because Doctrine
changes affect identity framing across all renderers, the file is **not**
modified automatically. This proposal sits here until the operator
approves, edits, or rejects it.

## Diff

```diff
@@ doctrine/identity/user-profile.md @@
 ---
 id: user-profile
 kind: identity
 title: User profile
 ---

-Bentonville, AR. AUDHD/PDA-aware support style.
+Bentonville, AR. AUDHD/PDA-aware support style. Post-wedding April 2026.
```

## Why now

The line addition was first observed in the session summary
`01HW4Z9D0E1F2G3H4I5J6K7L8M` (2026-04-28 EOD note) and is consistent with
two earlier journal entries in March 2026. The narrator adapter's
threshold for proposing an identity change (3+ corroborating Hoard
records over 14+ days) is met.

## Approval

To accept:

```bash
# overwrite the doctrine entry with the proposed body, then re-build the index
patch -p1 < this-file.diff
python tools/bp_build.py /path/to/operator-root
```

Then append a `kind: promote-to-doctrine` event referencing this proposal's
`event_id`.

To reject: delete this file. No event is required; the proposal expires
silently.

To edit: revise the proposed body inline, then accept as above.

## What this is not

This file is **not** part of the Doctrine layer. It lives under
`examples/ingestion-trace/doctrine-proposals/` for reference; in a real
deployment it would live under `policy/doctrine-proposals/` or wherever
the operator routes pending changes. Renderers MUST NOT read from this
location.
