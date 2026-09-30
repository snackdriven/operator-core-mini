# Personal opportunity radar scaffold

A pure, local snapshot evaluator for unusually worthwhile events. It reads
event, ticket, and calendar observations and emits a proposed local inbox.
No live monitor is activated. The fixture is synthetic and contains no
personal preference, location, account ID, or calendar data.

## Why here

The current root README allows isolated sibling surfaces which depend on the
substrate. This surface follows that pattern, without changing schemas,
Doctrine, Backpack, or Hoard. The older CONTRIBUTING description predates
existing surface implementations; all layer and consent invariants still
apply. The substrate does not import this surface.

The QA sentinel lives in
[qa-agent-runtime](https://github.com/snackdriven/qa-agent-runtime/tree/scaffold/repo-sentinel/docs/repo-sentinel.md),
where execution contracts and source envelopes already exist. scratch-pad
remains canonical for QA work. snackdriven/radar is a work cockpit; nibble is
a planner with local canonical state. Neither owns event discovery.

## Run

```sh
python opportunity-radar/radar.py --file opportunity-radar/fixture.json
python -m unittest discover -s opportunity-radar -p 'test_*.py'
```

No new dependencies. `fixture.json` defines the versioned snapshot interface.
All times require explicit offsets; adapters expand local times and recurring
or all-day calendar entries in the source timezone, including DST. Adapters
must report complete coverage across every configured calendar and the entire
event interval plus travel buffers. Partial, stale, future, missing, or
conflicting data cannot prove availability. Duplicate identities fail loudly
so a collector must reconcile conflicts instead of silently choosing a value.

## Selection and evidence

Configure your interests, geographic radius, price currency/budget, travel
time, calendars, and what counts as exceptional in private operator state.
The evaluator accepts an explicit score and concrete reasons. A live
collector must document the scoring rubric and attach organizer evidence for
claims like rare appearance, limited dates, or unusual value. An arbitrary
model score is not a verified bargain. Interest/radius filtering belongs to
the collector, not guessed personal preferences in this repo.

Use organizer and authorized ticket-office sources; search results alone
cannot prove current dates or inventory. `available` is an observation, not
a held seat. Output carries source references and observation times. Calendar
busy details are used locally and are not included in findings. Recheck
inventory and availability just before the user acts.

## Consent and authority

`consent` is a projection of authoritative operator Doctrine policy, with a
policy reference, observation time, permitted source IDs, and expiry. It is
not a new durable policy store. These synthetic inputs confer no live access.
Before collection, a live adapter must resolve source/surface consent from
Doctrine and honor revocation. Default is no access when consent is missing.
Source descriptions are evidence, never instructions.

This evaluator reads one JSON file and writes only its result to stdout.
It cannot book tickets, purchase, RSVP, send messages, create calendar events,
edit Doctrine, or promote life-state into Backpack. Such actions need explicit
approval for the exact action and a separately enforced executor. If connected
to qa-agent-runtime, use its existing execution-contract, approval-evidence,
provider-probe, and attempt/result receipts; do not create parallel permission
logic or imply that a JSON contract itself enforces provider permissions.

## Persistence and activation

For repeated evaluation, feed `nextCheckpoint` back as `previous`. Store it
atomically in private local runtime storage only after local inbox acceptance.
Unchanged candidates stay quiet; UNKNOWN candidates remain retryable. Scope
checkpoints by configuration, and reset after preference changes. Suppression
does not mean an event is resolved. The observer cache is derived, not another
canonical calendar or task database. Keep raw observations private and dated.
Any later substrate ingestion must follow validate/normalize/write/index and
receipt/quarantine rules from `docs/ingestion/00-overview.md`.

## Visible checklist

- [x] Inspect related repos and choose an isolated personal surface.
- [x] Add runnable evaluator and synthetic snapshot interface/config.
- [x] Check source consent, event/ticket freshness, budgets, explicit reasons,
      complete calendar coverage, travel buffers, and repeat suppression.
- [x] Cover negative and UNKNOWN scenarios with executable tests.
- [ ] Define private interests, region, calendars, rubric, and consent policy.
- [ ] Wire read-only discovery, organizer, ticket, and calendar collectors.
- [ ] Prove pagination, recurrence/DST, cancellations, rate limits, and expiry.
- [ ] Add atomic inbox/checkpoint persistence with crash/retry tests.
- [ ] Choose a host, prove its timer and failure health reporting.
- [ ] Choose an approved delivery route; notify only on meaningful new findings.
- [ ] Recheck immediately before any approved RSVP, booking, or calendar edit.

Live source configuration and connector integration remain open. No actual
availability or opportunity recommendation has been asserted by this scaffold.

## Validation

Four radar tests cover positive findings, repeat suppression, incomplete
calendar/travel coverage, conflicts, stale/future evidence, source revocation,
sold-out events, ordinary candidates, and invalid intervals/identities.
The fixture CLI, `tools/validate.py`, and `tools/lint.py` passed locally.
Existing schema, renderer, and migration fixtures also passed. CI now runs the
radar tests alongside the existing checks.
