# Narrator Brief — 2026-04-29 (Mass Effect skin)

> Narrator: **Mass Effect** (terse, mission-brief register). Selected to
> demonstrate facts-stable / framing-adapts: the underlying state is
> identical to `narrator-brief.sample.md`; only the voice rule changes.
> See `narrator-mass-effect-skin` in `doctrine.sample.json`.

---

**Mission:** Wednesday, 29 April. One sync at 14:00. Otherwise: async.

**Status report.**

QA queue, four objectives:

- **TTOAD-367** — primary. Code review pending; auth audit complete. Ready
  for merge on commander's mark.
- **TTOAD-221** — secondary. Repro on the v2 endpoint; legacy clean.
  Working hypothesis: token scope narrower than `patients:read.discharged`.
  Verification required before commit.
- **TTOAD-19** — closed. Duplicate, CCC Heber billing.
- **TTOAD-51** — closed. Site mapping verified upstream.

**Standing orders.** Q2 scope locked yesterday. NHHA RCM phase 2 pushed to
June. Jira migration cleanup carried over; misnamed-PR follow-up unassigned
and parked.

**Standby items.** Two carry-state entries flagged for verification before
use:

- `bug-referral-setup-2026-04-09` — TTL expired 0915 local. Confirm
  the receiving party is still active before routing.
- `ttoad-367-final-results` — seven days old. Treat the PR as ground truth.

**Intel update.** `ttoad-221-discharge-filter-bug-2026-04-09` demoted to
the archive overnight. Pattern preserved in `hunches-and-open-bugs`.

**SitRep.** Meeting at 1400. No further objectives queued. Proceed at
your own pace, Commander.

— *the narrator*
