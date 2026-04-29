# Follow-ups plan — 2026-04-29

Status: **Executed 2026-04-29**. All seven follow-ups landed in this
repo, plus the catch-all two-tier goldens, the hoard `aged_out_at`
lint warning, and an energy-routing regression test. The upstream
`snackdriven/operator-core-mini` ROADMAP Phase 4 row is bumped via
[PR #1](https://github.com/snackdriven/operator-core-mini/pull/1).
Status markers next to each section show what shipped vs what was
deferred. `python tools/validate.py` ends in `ALL PASSED` twice
(validator + lint, then renderer goldens). Catch-all caveats: the
`additionalProperties: false` migration template shipped in
`CONTRIBUTING.md`; two-tier goldens and the hoard `aged_out_at` warn
shipped 2026-04-29; `indexes/` remains deferred per the plan rationale
below.

This file captures the seven follow-ups surfaced by the
"challenge the assumptions" pass at the end of the Phase 4 renderer
work, plus dependencies, sequencing, file-level diffs, validation
strategy, and rollback / open questions per item. The information
flow diagram lives at [`docs/diagrams/information-flow.dot`](diagrams/information-flow.dot)
(rendered to `.png` and `.svg`); read it alongside this plan because
several follow-ups touch the same edges.

---

## TL;DR — sequencing

The seven items are not independent. Several depend on a shared fact
bundle existing; others depend on Hoard being readable; the
narrator-brief contract decision has knock-on schema and ADR work. The
proposed order minimises rework:

| Order | Item | Status | Why this slot |
|-------|------|--------|---------------|
| 1 | **#2 — Centralize fact bundle** | ✅ done | Foundation for #3, #4, #5, #6, parts of #1. Without it, every other renderer change has to be made in N places. |
| 2 | **#3 — Hoard vs `_replaced`** | ✅ done | Adds a new loader (`read_hoard()`); folds neatly into the new fact bundle. Establishes what "aged out overnight" means before #6 references it. |
| 3 | **#4 — Drop pinned+applies_to redundancy** | ✅ done | One-line fix in `session_primer`. Cheap; do it while the bundle work is fresh. |
| 4 | **#5 — Cosmetic title fix** | ✅ done | One-line markdown change + one expected-output update. Trivial; ride along with #4 in the same commit. |
| 5 | **#6 — Routing hints + Open threads sections** | ✅ done | Depends on bundle exposing `voice` and `routing`; depends on the session-primer title fix being already in. |
| 6 | **#7 — consent.scope vs item.scope contract** | ✅ done (Option A: scope→area rename) | Schema/doc clarification. Independent of the others but lower stakes; fixes a silent half-broken matcher. Best done in its own commit so the schema migration is reviewable. |
| 7 | **#1 — Narrator-brief contract** | ✅ done (two surfaces) | Largest design call (rename + new prompt-renderer + ADR amendment). Touch this *after* the bundle exists so the new prompt-renderer can consume `build_fact_bundle()` directly. Has its own staged plan below. |

After all seven, the catch-all caveats from the analysis (golden-test
brittleness, full-walk performance, `additionalProperties: false` trap)
get a separate, smaller follow-up section below.

Each numbered section uses the same template:

* **Status today** — what the code/spec currently does.
* **Target** — what we want it to do.
* **Files touched** — concrete paths.
* **Validation** — how we know it worked.
* **Rollback** — how to undo if it goes sideways.
* **Open question / risk** — anything I'm not sure about.

---

## #2 · Centralize the fact bundle  — ✅ **shipped 2026-04-29**

*Outcome:* `FactBundle` (frozen dataclass) and
`build_fact_bundle(operator_root, now, renderer_id, *, voice_skin_override=None,
energy=None, aged_out_window_hours=36)` live in
[`renderers/_common.py`](../renderers/_common.py). All four renderers
(`session_primer`, `daily_brief`, `statusline`, `narrator_brief` —
later split into `narrator_list` + `narrator_brief`) consume the
bundle and no longer call substrate loaders directly. `read_replaced`
moved into `_common`. The bundle exposes a `pinned_doctrine_by_kind()`
method, plus `omitted_for_consent / gate_messages /
gate_messages_short` so renderers don't re-run consent themselves.
The additional structural-equality check from the plan is deferred
into the catch-all (two-tier goldens) section.

**Status today.**
Each of the four renderers calls `read_doctrine`, `read_backpack`,
`read_freshness_policy`, and `consent_filter` independently. They each
re-derive `current_bp`, `recent_bp`, `verify_items`, `near_today`, and
each makes its own decision about what "applies here" means. This is
why the narrator-brief and daily-brief silently diverge whenever a
backpack item lists only one of `daily-brief` or `narrator-brief` in
its `surfaces` array — there is no single point that says "for time T,
here is the set of facts."

**Target.**
A single `build_fact_bundle(operator_root: Path, now: datetime,
renderer_id: str) -> FactBundle` lives in `_common.py` and is the only
place that calls the loaders + selectors. Renderers receive it
pre-built and only decide *which* slices to render and *how*. This
makes "facts stable across renderers" (the ADR 0003 promise) a
mechanical truth, not a coincidence.

The bundle is per-renderer because consent gating and `applies_here`
filtering are renderer-scoped — the bundle is the *projection* for
this renderer, not a global fact store.

```python
@dataclass(frozen=True)
class FactBundle:
    now: datetime
    renderer_id: str
    doctrine: list[dict]               # all doctrine entries (unfiltered)
    pinned_doctrine_by_kind: dict[str, list[dict]]  # for session-primer
    backpack_all: list[dict]           # post-consent, post-applies_here
    pinned_bp:    list[dict]
    current_bp:   list[dict]
    recent_bp:    list[dict]
    near_today:   list[dict]           # current_bp minus verify_items
    verify_items: list[dict]
    this_week:    list[dict]           # recent_bp minus verify_items
    aged_out:     list[dict]           # from Hoard; see #3
    replaced:     list[dict]           # from _replaced/; for diff-style surfaces
    today_lifestate: dict | None
    voice:        dict | None          # selected voice rule
    routing:      dict | None          # active routing rule (for energy-aware)
    omitted_for_consent: list[str]
    gate_messages: list[str]
    gate_messages_short: list[str]
    freshness_policy: dict | None
```

Renderers shrink to pure layout. For example, `session_primer.render()`
becomes `bundle = build_fact_bundle(...); return _layout(bundle)`.

**Files touched.**

* `renderers/_common.py` — add the `FactBundle` dataclass + builder.
  Move `read_replaced` (currently inside `daily_brief.py`) into
  `_common.py`. Wire all selection helpers into the builder.
* `renderers/session_primer.py` — replace inline reads with bundle.
* `renderers/daily_brief.py` — same.
* `renderers/statusline.py` — same.
* `renderers/narrator_brief.py` — same; this is also the prep for #1.

**Validation.**

1. Run `python tools/validate.py` — both passes must end in `ALL PASSED`.
2. Golden tests in `tools/test_renderers.py` are unchanged; their
   `expected-*` outputs must not move. Any drift is a bug in the
   refactor and gets fixed before merge.
3. Add one new golden case: `narrator_brief` and `daily_brief` rendered
   from the same fixture must reference the *same set* of backpack ids
   (modulo the ones each chooses to display) — a structural assert in
   the test file rather than a string-compare. This is the durable
   test that #2 is doing its job.

**Rollback.**
The refactor is mechanical and lives in a single commit. Revert.

**Open question / risk.**
The `applies_here` filter is currently applied *inside* each renderer
because the legacy `applies_to` array still exists alongside
`renderer_hints.surfaces`. The bundle either applies it once
(filtering `backpack_all` per-renderer) or exposes both filtered and
unfiltered views. I lean toward filtering once because the cost of
exposing items that don't apply is *exactly* the bug we're trying to
prevent. Concrete decision: bundle is per-renderer and pre-filtered.

---

## #3 · Stop conflating `_replaced/` with "aged out"  — ✅ **shipped 2026-04-29**

*Outcome:* `read_hoard()` added to `_common.py`; daily-brief now
emits `## Aged out overnight` from `hoard/` and `## Replaced overnight`
from `backpack/_replaced/`. `aged_out_at` (optional ISO-8601) added to
`schemas/backpack-item.schema.json`; `tools/validate.py` walks
`hoard/**/*.md` against the same schema. Default aged-out window is
36 hours (`DEFAULT_AGED_OUT_WINDOW_HOURS`). Items missing
`aged_out_at` still surface (they're already in Hoard — the lint can
warn later without blocking renders). Hoard layout is flat for v1 per
the "open question" call below; partitioning is part of the deferred
`indexes/` work.

**Status today.**
`backpack/_replaced/` holds items that were superseded by a newer item
(same `id` family, with a `replaces:` pointer). `daily_brief` reads
that directory and labels the section "What aged out overnight." That
label is wrong — these items are not aged out, they were replaced.
Real aged-out content lives in Hoard (per ADR 0002), and currently no
renderer reads Hoard.

**Target.**

* Introduce `read_hoard(operator_root) -> list[dict]`. Hoard layout is
  TBD; for v1 assume `hoard/**/*.md` with the same frontmatter loader
  as backpack, plus a required `aged_out_at` ISO timestamp (we filter
  to "since last render" using `now - 24h` as the default window for
  daily_brief).
* Daily-brief renames its existing section "Replaced overnight" (or
  drops it entirely if it stays redundant after Hoard is in) and adds
  a new "Aged out overnight" section sourced from Hoard.
* Add `aged_out` to the FactBundle from #2.
* Schema: `backpack-item.schema.json` already allows `replaces`. Add
  `aged_out_at` as an optional ISO field; only Hoard items use it.
  Lint warns if a file in `hoard/` has no `aged_out_at`.

**Files touched.**

* `renderers/_common.py` — `read_hoard()` + bundle field.
* `renderers/daily_brief.py` — rename + add section.
* `schemas/backpack-item.schema.json` — `aged_out_at` (optional).
* `tools/lint.py` — Hoard-presence check.
* `examples/operator-root-fixture/hoard/` — add 1 fixture item to
  exercise the new section in goldens.
* `examples/operator-root-fixture/expected-daily-brief.md` — updated.

**Validation.**

1. `validate.py` clean.
2. New fixture item shows up in the daily-brief golden under "Aged out
   overnight"; old `_replaced` item shows up under "Replaced overnight"
   (or doesn't show at all if we drop the section).
3. `narrator_brief` golden output also gets a `aged` block populated
   (currently empty in the existing fixture).

**Rollback.**
Drop the new fixture item, revert `daily_brief.py` and `_common.py`,
remove the schema field. The old behaviour is fully preserved by the
existing tests and the schema field is `optional` so dropping it is
non-breaking.

**Open question / risk.**
We have not specified the Hoard layout in any prior ADR. Doing this
work raises the question "should Hoard be partitioned by month, by
scope, or flat?" I propose **flat for v1, with `aged_out_at` doing the
sorting**. Partitioning is a perf concern, deferred to the indexes
work in the catch-all section. If we want to do partitioning at the
same time, it becomes part of #3 and adds about a day.

---

## #4 · Drop pinned+applies_to redundancy in session-primer  — ✅ **shipped 2026-04-29**

*Outcome:* `session_primer` now surfaces a Doctrine entry if it's
pinned **OR** explicitly opts in via `renderer_hints.surfaces` /
`applies_to`. Pinned entries with non-empty surfaces lists that
exclude `session-primer` are still respected (pinning is not
render-everywhere); `never_surface_in` remains a hard denylist.

**Status today.**
`session_primer.render()` requires *both* `pinned == true` *and*
`applies_here(entry, "session-primer")` for a Doctrine entry to
surface in the Defaults/Workflows/Policies block. This means a
non-pinned Doctrine entry that explicitly lists `session-primer` in
its `surfaces` is dropped — even though the operator went out of their
way to opt it in.

**Target.**
Surface a Doctrine entry in session-primer if **either**:

* it is pinned (regardless of `applies_to` / `surfaces`), or
* it explicitly lists `session-primer` in `renderer_hints.surfaces` /
  `applies_to`.

Implementation: `applies_to_session_primer = entry.get("pinned") or
applies_here(entry, RENDERER_ID)`.

**Files touched.**

* `renderers/session_primer.py` — one expression change.
* No fixture changes required, but worth adding a Doctrine entry that
  is *not* pinned and *does* list `session-primer` in `surfaces`,
  purely to lock the new behaviour into the goldens.

**Validation.**
Existing golden output stays stable (because the current fixture
relies on pinned entries). New fixture entry plus an updated expected
output proves the OR semantics.

**Rollback.**
One-line revert.

**Open question / risk.**
None. This is unambiguously a bug.

---

## #5 · Cosmetic title fix (`Session primer` → `Session Brief`)  — ✅ **shipped 2026-04-29**

*Outcome:* Renderer header is now `# Session Brief — <date>`. The
surface ID stays `session-primer` everywhere in substrate, schemas,
and consent rules. Documented in the renderer module docstring so the
next contributor doesn't "fix" the title back to match the surface id.

**Status today.**
Surface ID is `session-primer` everywhere in substrate (schemas,
fixture, ingestion docs, doctrine.sample.json). The Phase 2
hand-written sample is the only artifact that uses the string
"Session Brief", and only as a markdown title and filename
(`session-brief.sample.md`). My current renderer outputs
`# Session primer — <date>`.

**Target.**
The renderer produces `# Session Brief — <date>` to match the
operator-facing nomenclature in the Phase 2 deliverable. The
**surface id stays `session-primer`** — that is the durable identity
that schemas and consent rules reference, and changing it would touch
the whole repo.

**Files touched.**

* `renderers/session_primer.py` — change the literal `# Session
  primer — ` to `# Session Brief — `.
* `examples/operator-root-fixture/expected-session-primer.md` —
  matching one-line update.

**Validation.**
Golden test rerun.

**Rollback.**
One-line revert.

**Open question / risk.**
None — but document this in the renderer module docstring so the next
person doesn't "fix" it back to match the surface id.

---

## #6 · Add "Routing hints" + "Open threads" sections to session-primer  — ✅ **shipped 2026-04-29**

*Outcome:* session-primer now renders both sections. Routing hints
looks up the *narrator's* active voice (session-primer is a meta
surface telling the operator what the narrator will do) and reports
configured routing rules even when not triggered. Surfaces consenting
to life-state are derived from policy entries with
`consent.posture in {opt-in, allow}` and `consent.scope == life-state`.
Open threads come from backpack items tagged `open-thread`; we shipped
option (1) from the plan (tag-only convention) and added a fixture
entry `examples/operator-root-fixture/backpack/recent/misnamed-pr-detection-followup.md`.
Promotion to a first-class `open_thread` field is deferred until the
section is load-bearing.

**Status today.**
The Phase 2 hand-written sample has both a `Routing hints` section
("Narrator: default. Low-energy routing not triggered…") and an
`Open threads worth knowing` section. My session-primer renderer has
neither.

**Target.**
Add two sections, both sourced from the FactBundle:

* **Routing hints** — built from `bundle.voice` and `bundle.routing`
  (already populated for narrator-brief). Lines look like:
  ```
  - Narrator skin: `good-place` (selected via default voice-rule).
  - Energy routing: not triggered.
  - Surfaces consenting to life-state: session-primer, narrator-brief.
  ```
  The "consenting to life-state" line comes from filtering the
  doctrine policies by `consent.posture in {opt-in, allow}` and
  `consent.scope == "life-state"`.
* **Open threads worth knowing** — Backpack items where
  `memory_class == "expiring-tactical"` and `tags` includes
  `open-thread`. (We add a fixture item with that tag.)

**Files touched.**

* `renderers/session_primer.py` — two new section blocks.
* `examples/operator-root-fixture/backpack/recent/<new-item>.md` —
  fixture entry tagged `open-thread`.
* `examples/operator-root-fixture/expected-session-primer.md` —
  updated.

**Validation.**
Golden rerun. Cross-check against the Phase 2 sample to confirm we
match the *spirit* (not the prose) of the original sections.

**Rollback.**
Drop the new sections; remove the fixture entry; restore the old
expected output.

**Open question / risk.**
"Open threads" is a new convention — `tags: open-thread` is not
formally part of the schema. Two ways to handle it:

1. **Tag-only** (what's proposed). Cheap; documented in the renderer
   docstring; lints don't enforce.
2. **First-class field** on backpack-item, e.g. `open_thread: true`.
   Heavier — schema change, migration script (`tools/migrate.py`),
   tighter lint. Worth doing if this section becomes load-bearing.

Default to (1); promote to (2) when we have a real signal.

---

## #7 · Document consent-scope-vs-tag reality (or rename)  — ✅ **shipped 2026-04-29 (Option A)**

*Outcome:* Option A landed. `Scope` enum on backpack-item and
hoard-item is renamed to `Area`; the `additionalProperties: false`
allowlist now lists `area`, not `scope`. `index.schema.json`'s
`by_scope` is renamed to `by_area`. `consent_filter` no longer has
the dead `p["scope"] == item.scope` clause; matching is
unambiguously tag-only. A migration script
[`tools/rename_scope_to_area.py`](../tools/rename_scope_to_area.py)
is idempotent across markdown frontmatter, JSON, and JSONL targets and
migrated 19 substrate files. ADR 0004's Follow-ups section now
records the rename. `consent.scope` keeps its name on policy entries
because that's what consent rules refer to.


**Status today.**
`consent.scope` on a policy is a free-string (e.g. `"health-records"`,
`"health"`). `backpack-item.scope` is a strict enum
(`work | life | assistant | identity | meta`). My matcher in
`consent_filter()` does:

```python
hit_policy = next(
    (p for p in policies if p["scope"] in tags or p["scope"] == scope),
    None,
)
```

The second clause (`p["scope"] == scope`) effectively never fires for
real consent policies, because no enum value matches the strings
operators write into consent policies. We are tag-only matching in
practice.

**Target — pick one:**

**Option A (rename + clarify).** Keep behaviour, fix names.

* Rename `backpack-item.scope` → `backpack-item.area` (or
  `lifecycle_zone`). The enum is about *which slice of life this item
  belongs to*, not about consent.
* Drop the `p["scope"] == item.scope` clause from `consent_filter`.
  Matching is unambiguously by `tags`.
* `consent.scope` keeps its name; that's what consent policies refer
  to.

**Option B (formalise the dual-key match).** Make the second clause
real.

* Keep `backpack-item.scope` enum. Add a field `consent_scope:
  string` that is matched against `consent.scope`.
* `consent_filter` matches if `policy.scope` is in
  `item.tags ∪ {item.consent_scope}`.

**Recommendation.** Option A. The enum was always about
classification, not consent. Conflating the two is the bug. Option B
adds a parallel field that operators will forget to set.

**Files touched (Option A).**

* `schemas/backpack-item.schema.json` — rename `scope` → `area`. Add
  `area` to the `additionalProperties: false` allowlist; remove
  `scope`. Keep the enum values.
* `tools/migrate.py` — adds a `rename-scope-to-area` step that
  rewrites every `scope:` line in `backpack/**/*.md` to `area:`.
  Idempotent; safe to run twice.
* `renderers/_common.py` — drop the second clause in `consent_filter`.
  Update the rationale string.
* `examples/**/*.md` — bulk rename via the migrate script.
* `docs/decisions/0004-consent-posture-is-doctrine.md` — Follow-ups
  section gets a new bullet noting the rename.

**Validation.**

1. Migration script run on the fixture; lint clean; validate clean.
2. Goldens unchanged (matching is identical because the second clause
   never fired in practice).
3. Schema test: a backpack item with the old `scope:` key fails the
   schema (proves the rename is enforced).

**Rollback.**
Migrate script supports a `--reverse` mode that reverses the rename.
Schema rename is in one PR.

**Open question / risk.**
Hidden uses of `scope` as a free string somewhere in the code path
(not just the schema). Search the whole repo for `\.get\("scope"\)`
and `entry\["scope"\]` before merging.

---

## #1 · Fix the narrator-brief contract  — ✅ **shipped 2026-04-29 (two surfaces)**

*Outcome:* Two surfaces per the recommendation, sharing one
voice-rule selection contract.

* `renderers/narrator_list.py` — the renamed original
  `narrator_brief.py`. `RENDERER_ID = "narrator-list"`. Output is the
  deterministic structured markdown list with skin-specific
  opener/section/closer; goldens at
  [`expected-narrator-list.md`](../examples/operator-root-fixture/expected-narrator-list.md)
  and [`expected-narrator-list.mass-effect.md`](../examples/operator-root-fixture/expected-narrator-list.mass-effect.md).
* `renderers/narrator_brief.py` — new prompt-renderer.
  `RENDERER_ID = "narrator-brief"`. Emits a deterministic markdown
  prompt artefact: header + YAML system block (active voice,
  do/avoid, `prompt_version: 1`) + `## Facts` + `## Instruction` +
  footer. The LLM step that turns the prompt into prose is *outside*
  the renderer boundary. Golden at
  [`expected-narrator-brief.prompt.md`](../examples/operator-root-fixture/expected-narrator-brief.prompt.md).
* `tools/test_renderers.py` updated: existing two narrator goldens
  became `narrator-list` cases; new `narrator-brief.prompt` golden
  added. `examples/renders/narrator-brief.sample.md` and the
  mass-effect twin now carry an explicit "this is *expected LLM
  output*, not deterministic renderer output" banner.
* ADR 0005 was **amended** (not superseded) with a
  "Clarification — 2026-04-29 (narrator surfaces split)" section. The
  voice-rule selection contract in 0005 is unchanged and load-bearing
  for both surfaces; voice-rule scope `[narrator-list, narrator-brief]`
  applies to both.
* Fixture `surfaces:` arrays migrated from `narrator-brief` to
  `narrator-list, narrator-brief` so existing items render in both;
  voice-rule scopes and applies_to lists migrated likewise.

*Plan vs reality.* Sequencing held; #1 ran last so the new
prompt-renderer could consume `build_fact_bundle()` directly. The
load-bearing prompt instruction lives in `narrator_brief.render()`
guarded by `prompt_version: 1` so future iteration on prose quality
doesn't silently break the contract.

This is the largest item; it has its own three-stage plan because the
naming, the contract, and the ADR all interact.

### Stage A — name + contract decision

**Status today.**
Phase 2 sample (`examples/renders/narrator-brief.sample.md`) is
clearly LLM prose: "367 is sitting in code review like a polite
library book". My current `narrator_brief.py` produces a structured
template (bullets keyed off `id` and `value`). ADR 0005 codified my
*template-based* interpretation as the contract — meaning ADR 0005
documents the wrong thing relative to the Phase 2 sample.

There are two coherent end-states:

* **Two surfaces.** Keep both. `narrator-list` is the structured
  template renderer (current code, renamed). `narrator-brief` is a
  prompt-renderer: it emits a structured prompt + fact bundle for an
  LLM to render into prose. The LLM step is *outside* the renderer
  boundary (renderers are still pure). This preserves "facts stable,
  framing adapts" because the prompt encodes the same fact bundle.
* **One surface, two implementations.** `narrator-brief` is the LLM
  prose surface (Phase 2 contract). The structured-template variant is
  retired or kept as a fallback when no LLM is available.

**Recommendation.** Two surfaces. We have actual operator-facing reasons
to want both — the structured list is great for headless / no-LLM /
audit contexts; the prose is great for ambient consumption. Renaming
the structured one to `narrator-list` makes the role of each obvious.

### Stage B — implementation

**Files touched.**

* `renderers/narrator_brief.py` — file is renamed (`git mv`) to
  `renderers/narrator_list.py`. `RENDERER_ID` becomes
  `narrator-list`. CLI `--skin` semantics preserved.
* New file `renderers/narrator_brief.py` — prompt-renderer. Output is
  a markdown document containing:
  1. A short header `# Narrator brief prompt — <date>` for human
     readability when piped to a file.
  2. A YAML-frontmatter system block declaring the active voice rule,
     do/avoid lists, and "facts stable, framing adapts" reminder.
  3. A markdown rendering of the FactBundle that the LLM uses as
     ground truth (this is the same `near_today / verify / aged_out`
     content as the daily brief, formatted compact).
  4. A clear instruction: "Render these facts as prose using the voice
     rule above. Do not invent items not in the fact list. Cite each
     prose claim by item id in a trailing comment."
* `tools/test_renderers.py` — golden case for `narrator_list` (renamed
  from existing) plus a *prompt-stability* golden for
  `narrator_brief` (the prompt is deterministic given the bundle, so
  it's testable; the LLM output is not).
* `examples/operator-root-fixture/expected-narrator-list.md` and
  `expected-narrator-list.mass-effect.md` — renamed copies of current
  expected outputs.
* `examples/operator-root-fixture/expected-narrator-brief.prompt.md`
  — new golden, the deterministic prompt artefact.
* `examples/renders/narrator-brief.sample.md` — relabel the YAML
  frontmatter block to make it explicit this is *expected LLM
  output*, not a renderer's deterministic output.
* `schemas/doctrine-entry.schema.json` — add `narrator-list` to the
  conventional renderer-id list in any places that hard-code surfaces.
* All fixture frontmatter `surfaces:` arrays — replace
  `narrator-brief` with the appropriate combination of `narrator-list`
  and `narrator-brief`. Items where the operator only wanted the
  list-style surface should drop `narrator-brief`.

### Stage C — ADR work

ADR 0005 currently documents the (wrong) template-only interpretation.
Two options:

* **Amend.** Add a clarification block at the bottom of ADR 0005
  saying: "The `narrator-list` surface is template-driven. The
  `narrator-brief` surface is prompt-driven and the renderer's output
  is a *prompt*, not the final prose." Keep the ADR otherwise intact.
* **Supersede.** Mark 0005 superseded by a new ADR 0006:
  "Voice rules apply to two narrator surfaces (list + brief)." Move
  the content; add the contract for `narrator-brief`.

**Recommendation.** Amend. The voice-rule selection contract in 0005
is correct and load-bearing for both `narrator-list` and the prompt
renderer. Superseding it would force a reader to chase two ADRs to
understand voice selection. Add a "Clarification — 2026-MM-DD"
section near the end.

### Validation for #1

1. `validate.py` clean after rename + new file.
2. Old golden cases (renamed to `narrator-list`) are byte-identical to
   today's goldens.
3. New `narrator-brief.prompt` golden is stable: re-running the
   renderer on the fixture produces the exact same prompt string.
4. Manual: pipe the new `narrator-brief` output to an LLM, verify the
   prose surface looks like the Phase 2 sample. (Not a CI check;
   smoke test.)

### Rollback for #1

Stages A/B/C are commit-separable. Stage B is the costliest; if it
goes wrong the rollback is `git mv` back + restore goldens. Stage C is
a documentation-only change.

### Open question / risk for #1

* The "render facts as prose" instruction is the load-bearing line in
  the prompt. Iterate on it based on actual LLM output; treat it as
  versioned (e.g., embed `prompt_version: 1` in the prompt
  frontmatter so we can A/B tweaks).
* Prompt templates may want to live in Doctrine alongside voice rules
  rather than in renderer source. Defer that decision until we have
  two prompt-driven renderers.

---

## Catch-all caveats from the analysis (lower priority)

These were raised in the same caveats pass but did not make the
top-7. They get short treatments here so they don't fall on the floor.

*Status as of 2026-04-29:*

* `additionalProperties: false` migration template — ✅ documented in
  [`CONTRIBUTING.md`](../CONTRIBUTING.md#additionalproperties-false-migration-template)
  (canonical four-step recipe).
* Two-tier goldens (structural + snapshot) — ✅ **shipped 2026-04-29**.
  `tools/test_renderers.py` now carries a `Case.voice_aware` flag.
  Voice-aware surfaces (currently both `narrator_list` cases) extract
  a `Fingerprint(sections, ids)` from both expected + actual; structural
  mismatch is a real `[FAIL]`, snapshot mismatch with structural match
  surfaces as `[ADVISORY]` and does **not** fail the run. Deterministic
  surfaces (session-primer, daily-brief, statusline, narrator-brief
  prompt) keep the byte-equal snapshot check.
* Hoard `aged_out_at` lint — ✅ **shipped 2026-04-29**. New
  `check_hoard_aged_out_at` in `tools/lint.py` walks
  `examples/**/hoard/**/*.md`; missing `aged_out_at` produces a
  `[WARN]` line and a trailing `WARNINGS:` block but never affects
  exit status.
* Energy-routing regression test — ✅ **shipped 2026-04-29**. The
  fixture now ships a second routing-rule
  (`narrator-high-energy-routing`, when=`high-energy`) so the
  selector has more than one entry to disambiguate. New golden case
  `narrator_brief --energy low-energy` exercises the routing-driven
  voice flip (good-place → mass-effect) end to end.
* Generated `indexes/` — ⏳ deferred until the substrate has > ~500
  files (per the plan's own explicit deferral).

### Goldens are too rigid for voice-aware surfaces

**Problem.** A voice-rule edit (e.g. swapping a single word in a
do-rule) flips the narrator-brief golden into a regression even though
nothing structural changed.

**Fix.** Two-tier goldens for voice-aware surfaces:

* **Structural golden** — checks the set of fact ids referenced and
  the section ordering. Must match exactly.
* **Snapshot golden** — checks the full text. Treated as advisory;
  diffs surface in CI but do not fail the run unless the structural
  golden also moves.

Implement in `tools/test_renderers.py` as two assertion classes.

### Full filesystem walk per render

**Problem.** Every render walks `backpack/**/*.md` and `doctrine/**/*.md`.
Acceptable for the fixture; potentially slow when an operator's vault
is large.

**Fix.** Generated `indexes/`:
* `indexes/backpack-by-renderer.json` keyed on renderer-id; contains
  pre-computed lists of file paths whose `surfaces:` arrays contain
  that renderer.
* `indexes/doctrine-by-kind.json` keyed on `kind`.
* `tools/build_indexes.py` is the only writer; it's idempotent.
* Loaders prefer indexes when present, fall back to a full walk.
* `validate.py` runs `build_indexes.py` after every other check and
  fails if the result differs from the on-disk index (proves indexes
  are in sync).

This is a perf optimisation; defer until the substrate has > ~500
files.

### `additionalProperties: false` strictness trap

**Problem.** Adding any new optional field to a schema breaks every
existing fixture file unless `additionalProperties: false` is loosened
or every fixture is migrated atomically.

**Fix.** Two-step migration template — `tools/migrate.py` already
exists; document the canonical pattern for "add field X":

1. Loosen `additionalProperties` to `true` (or remove the line).
2. Add the field, ship the schema change.
3. Run the fixture migration to populate the new field.
4. Re-tighten `additionalProperties: false`.

Document this in `CONTRIBUTING.md` so contributors don't get stuck.

---

## Diagram

See [`docs/diagrams/information-flow.dot`](diagrams/information-flow.dot)
(rendered to `.png` and `.svg`). The diagram annotates which boxes /
edges each follow-up moves:

* #2 introduces the **fact bundle** node (green, central).
* #3 introduces the **read_hoard()** loader and the
  `backpack/recent → hoard` edge labelled "TTL expires (real
  aged-out)".
* #1 splits the renderer column into **`narrator_list`** (template,
  current code renamed) and **`narrator_brief`** (prompt-driven,
  dashed because LLM-mediated).
* #4 / #5 / #6 are session-primer-internal and don't change the
  graph topology.
* #7 is a schema/doc rename and also doesn't change topology.

The dashed purple `indexes/` node is the deferred caveat fix; it's in
the diagram so the long-term shape is visible.

---

## What I'm asking for before I start

Three calls, in priority order:

1. **Sequencing OK?** I want to start with #2 (fact bundle) because
   it makes everything else cheaper. If you'd rather see #1 (the
   narrator-brief rename + ADR amendment) first because it's the
   biggest design call, say so.
2. **#7 — Option A or Option B?** A is the recommendation; B is
   defensible. Pick one before I touch the schema.
3. **#1 — Two surfaces or one?** Two is the recommendation. If you
   want one, the prose surface is the default and the structured one
   is dropped (no `narrator-list`).

Once those three are answered, the rest is mechanical.

---

## Phase 5 — migrate hardening (shipped 2026-04-29)

After PR #1 (ADRs/fact-bundle) and PR #2 (two-tier goldens) merged, I
ran the migrator end-to-end against the real `snackdriven/scratch-pad`
repo and filed five bugs. All five are now fixed in this branch.

### Bugs found, in priority order

1. **Bug 0 (underneath, not numbered):** migrate.py emitted fields not
   allowed by the post-#7 `backpack-item.schema.json`
   (`additionalProperties: false`) — `title`, `_meta`, raw `scope`.
   117/117 items failed schema validation.
2. **Bug 2:** no date mined from value-text. Every item missing `dated`
   surfaced in session-primer as `(?)`.
3. **Bug 4:** legacy `title:` heuristic produced garbage
   ("As of 2026-04-07 end-of-session"). Removed schema-illegal field;
   renderers already fall back to `id` or first line.
4. **Bug 1:** no doctrine seed. Rendering a pure migrated tree (no
   fixture overlay) blew up on "an operator root" check.
5. **Bug 5:** no per-surface item budgets. Session-primer was 150 lines
   / 57 KB with 117 items. Statusline truncated but wasn't actually
   budget-aware.
6. **Bug 3:** no hoard. `aged_out` section was perpetually empty because
   the migrator wrote nothing to `hoard/`, even though `_config:ttl`
   encoded which items had expired.

### Fixes

- **tools/migrate.py** — full rewrite. Schema-clean output per
  post-#7 backpack-item schema. Three-tier `dated` mining
  (as-of → id-trailing date → value first line → value last date).
  Legacy `scope` → `area` enum. `source.kind = scratch-pad`. Items with
  no extractable date promoted to evergreen. **New `--with-hoard` flag**
  walks `dailies/YYYY-MM-DD/` and loose `*.html` at scratch-pad root,
  writing one hoard entry per file with `aged_out_at` stamped from the
  dated folder. TTL-expired items (per `_config:ttl[*].created_at +
  ttl_seconds < --now`) are diverted to `hoard/` instead of
  `backpack/current/` with `aged_out_at` = expiry time.
- **tools/bootstrap_doctrine.py** (NEW) — writes 9 starter doctrine
  entries so the renderers start sane without a fixture overlay:
  identity/user-profile, default/writing-preferences, voice/voice-
  good-place, voice/voice-mass-effect, routing/narrator-{low,high}-
  energy, policy/consent-{narrator-vault,health-private,github-source-
  of-truth}. CLI: `--name --summary --force`.
- **renderers/_common.py** — added `DEFAULT_RENDERER_BUDGETS` dict,
  `budget_for()`, `apply_budget()`, `by_priority_then_recency()`.
  Pinned items are never budget-truncated. Budgets per-surface:
  session-primer current=12 / recent=8 / verify=8 / aged_out=8;
  daily-brief 10 / 6 / 8 / 8; narrator-list + narrator-brief
  8 / 4 / 0 / 4; statusline 1 / 0 / 0 / 0. Overridable via
  `policy/freshness.json["renderer_budgets"]`.
- **renderers/{daily_brief,session_primer,narrator_list,narrator_brief}
  .py** — apply `apply_budget()` to current / recent / verify /
  aged_out lists, surface a `+N more … (budgeted)` hint when truncation
  fires. Sort is priority-desc → dated-desc → id-asc.

### Real-data results

Against `snackdriven/scratch-pad@HEAD` with `--now 2026-04-29T20:00:00Z`:

- 117/117 backpack items schema-valid (was 0/117).
- 13 items past TTL → diverted to `hoard/`, leaving 104 in backpack.
- 495 files migrated from `dailies/` into `hoard/YYYY/MM/DD/`.
- 14 loose `*.html` reports migrated into `hoard/`.
- `aged_out` section populates overnight: 11 items inside the
  default 36 h window.
- Budget truncation fires on real data:
  `+44 more current items not shown (budgeted)`,
  `+48 more verify items not shown (budgeted)`.
- Fixture goldens still byte-identical (4-item fixture fits under every
  budget). `tools/validate.py` shows `ALL PASSED` twice.

### Pipeline (for future re-runs)

```bash
rm -rf /tmp/operator-root && \
  python tools/migrate.py /tmp/scratch-pad/backpack.json /tmp/operator-root \
    --with-hoard /tmp/scratch-pad --now 2026-04-29T20:00:00Z && \
  python tools/bootstrap_doctrine.py /tmp/operator-root \
    --name "Kayla" --summary "QA at Tebra/NHHA. Bentonville, AR." && \
  python tools/bp_build.py /tmp/operator-root
for s in session_primer daily_brief statusline narrator_list narrator_brief; do
  python renderers/$s.py /tmp/operator-root --now 2026-04-29T20:00:00Z
done
```


## Phase 6 — PR A: correctness foundation (2026-04-29)

Audit of the post-Phase-5 tree surfaced 12 issues. PR A fixes the five
correctness blockers; PR B (perf/UX) and PR C (data-integrity) are
deferred.

### Fixes shipped

- **`tools/migrate.py` split (706 → 454 lines).** Hoard-walking logic
  extracted into `tools/migrate_hoard.py` (268 lines). Shared helpers
  (slugify, ISO parsing, frontmatter writer, dated-extraction,
  derive_summary) extracted into `tools/_migrate_common.py` (200
  lines). The `migrate.py` CLI signature is unchanged:
  `python tools/migrate.py LEGACY_PATH OUT_ROOT [--with-hoard …]
  [--now …]`. TTL diversion stays in `migrate.py` because it acts on
  backpack items, not hoard items.
- **Freshness-policy migrate output is now schema-valid.** Rewrote
  `_build_freshness_skeleton` to emit the canonical shape
  (`rules` block, bands with `max_age_days` + `treatment`,
  `renderer_budgets`, `tag_overrides`). Added a post-write
  `_validate_freshness_skeleton` assertion using `jsonschema` (best-
  effort — skipped silently if `jsonschema` isn't installed).
- **Hoard storage format locked to `.md` frontmatter.**
  `tools/bp_build.py` now walks `hoard/**/*.md` and serializes via
  `split_frontmatter` into `_hoard.jsonl` (522 records on real data,
  was a 0-byte file before). `schemas/README.md` and
  `docs/ingestion/00-overview.md` updated to describe the same shape.
- **`schemas/hoard-item.schema.json` deleted.** Hoard items now
  validate against `backpack-item.schema.json` (they're just backpack
  items with `aged_out_at` stamped). `tools/validate.py` walks the
  hoard tree as `.md`. `examples/hoard-sample.jsonl` removed.
  `examples/ingestion-trace/hoard/{06,29}.json` rewritten as
  `hoard/2026/04/{06,29}/q2-roadmap-*.md` in backpack-item shape
  (`hoard_refs` array, `aged_out_at`, `freshness_class=historical`,
  `memory_class=timeline`). `decisions/0002-doctrine-vs-hoard.md`
  edited to drop the hoard-item.schema reference.
- **`tools/test_migrate.py` (NEW, 455 lines, 24 tests).** Six classes
  covering: 3-tier date mining; field normalization (scope→area, kind
  defaults, freshness_class fallbacks); freshness-dir derivation;
  TTL-eligibility logic; freshness-skeleton schema-cleanliness; full
  end-to-end migration with and without `--with-hoard`. Wired into
  `tools/validate.py` after the renderer-tests block. **Caught a real
  bug**: pinned-and-expired items were being added to the
  `aged_out_via_ttl` list. Fixed by tracking `is_pinned_key` separately
  and short-circuiting before TTL eligibility is checked.

### Bonus fixes

- **`tools/bp_build.py`** — index keys `by_scope` → `by_area` (matches
  the schema; was schema-invalid against `index.schema.json`).
- **`tools/bootstrap_doctrine.py`** — docstring expanded to clarify the
  9 entries are *seeds*: identity, writing prefs, two voices, two
  routing rules, three consent policies. Some are unused by current
  renderers; they're scaffolding for downstream surfaces.

### Verification

`tools/validate.py` returns `ALL PASSED` **twice** (exit 0). Counts:
8 schemas self-valid, 7 single-file examples valid, 21 ingestion
events valid, 2 ingestion-trace hoard `.md` files valid, all renderer
goldens byte-identical, **24 migrate-tests pass**, 7 lint checks pass.

Real-data run against `/tmp/scratch-pad` produced 117 migrated items
(13 TTL-diverted, 4 evergreen, 104 in backpack), 495 dailies + 14
loose artifacts in hoard, 9 doctrine seeds, `_hoard.jsonl` with 522
records, all 5 renderers clean.

### Deferred

- **PR B (perf + UX):** issues 4, 8, 9, 10 — will batch after PR A
  lands.
- **PR C (data integrity):** issue 11 — separate PR.
- **Doctrine-kind enum simplification (issue 5):** revisit in a future
  ADR; current 9-kind enum is intentional, just under-consumed.
