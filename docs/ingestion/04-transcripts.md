# Ingestion — transcripts and session summaries → Hoard (and sometimes Backpack)

Transcripts (meetings, Claude sessions) and session summaries are the
highest-volume source. They live primarily in **Hoard** (write-once, searchable)
and promote selectively into **Backpack** only when a summary actually matters
to current work.

## What these sources contain

Verified from `scratch-pad/dailies/YYYY-MM-DD/transcripts/`:

- `<YYYY-MM-DD>_<HH-MM>-<label>.txt` — raw verbatim transcript
- `<YYYY-MM-DD>_<HH-MM>-<label>.md` — markdown summary produced by a
  transcription or summarization step
- `meeting-summaries.md` — the day's per-meeting rollup

Plus Claude-session sources:

- `.claude/hooks/pre-compact-auto-save.cjs` output — a distilled
  session-summary payload
- EOD scratch-pad files (`eod-YYYY-MM-DD`)

## Four categories, three destinations

| Category | Hoard kind | Promoted to Backpack? |
|---|---|---|
| Raw verbatim transcript | `transcript` | No. Never. |
| Transcript summary | `transcript-summary` | Sometimes — see promotion rules. |
| Claude session summary | `session-summary` | Sometimes — when session advanced a current work item. |
| Meeting rollup (`meeting-summaries.md`) | `note` (kind: note, `tags: [rollup]`) | No. Rollup is a convenience read, not carry-state. |

## The transcript adapter

### Step 1 — always capture both `.txt` and `.md` as separate Hoard items

Both sides of the transcript are valuable. The raw `.txt` preserves exact
wording; the `.md` summary is what humans re-read. Writing both:

- `hoard/YYYY/MM/DD/<ulid>-transcript.json` → `kind: transcript`,
  `content` = verbatim text (up to a size limit — see attachments below),
  `attachment.path` = pointer to the raw file.
- `hoard/YYYY/MM/DD/<ulid>-transcript-summary.json` →
  `kind: transcript-summary`, `content` = the summary markdown,
  `hoard_refs` (reverse: the summary's `content` references the verbatim by
  id in its frontmatter, not schema-enforced but conventional).

### Step 2 — size rules

Transcripts can be long. The adapter applies:

- If the verbatim `.txt` is > 64 KB, `content` is truncated to the first
  N bytes + a `[transcript continues ... turns]` tail, and
  `attachment.path` points at the full file. The schema's
  `attachment.sha256` is computed over the full file.
- Summaries are never truncated.

### Step 3 — PII and redactions

The adapter runs a conservative redaction pass over transcript `.txt`
content before storage:

- Email addresses, phone numbers, full home addresses → redacted, logged in
  `redactions: [...]`.
- Proper nouns are NOT redacted; they are preserved because they're the
  point of the transcript.
- Medical details spoken in the meeting are NOT auto-redacted (over-
  redaction would damage continuity), but the item gets
  `tags: [health]` and `requires_consent: true` added.

If the user opts out of redaction entirely, the adapter writes the raw
`.txt` verbatim but still stamps `tags: [unredacted]` so renderers and
search can filter.

### Step 4 — dedup

Transcripts are deduped by `sha256(attachment)`. Re-importing the same file
is a no-op. The adapter emits an `ingested-duplicate` event so the user
knows an attempted re-import occurred.

### Step 5 — metadata extraction

The adapter extracts (best-effort, non-schema-enforced):

- `people` from a leading "Attendees:" line if present, or from
  speaker labels (`Jamie:`, `Ishan:`).
- `occurred_at` from the filename timestamp (`YYYY-MM-DD_HH-MM`).
- `projects` from known tags in the summary body (e.g. `nhha-rcm`).

## The session-summary adapter

Claude sessions end with a pre-compact hook that emits a distilled summary.
Adapter writes:

- `hoard/YYYY/MM/DD/<ulid>-session-summary.json`,
  `kind: session-summary`, `scope: work` or `assistant` depending on the
  session's tag, `source.kind: scratch-pad` (because the hook lives there)
  or `manual` (if the user pasted).
- No attachment; the summary is the content.

Session summaries are content-addressed by `(session_id, captured_at)` so
multiple compactions within one session produce distinct records.

## Promotion rules — when a summary becomes a Backpack item

Most transcript-summaries stay in Hoard. A summary is promoted into Backpack
only when at least one of these conditions holds:

1. **Supersedes a current Backpack item.** The summary's `projects` or
   `tags` overlap with an existing Backpack item marked
   `memory_class: expiring-tactical`, AND the summary's `occurred_at` is
   newer than the Backpack item's `created_at`. In that case: write a new
   Backpack item with `replaces` set to the old, mark `hoard_refs` to the
   summary, and retire the predecessor to `_replaced/`.
2. **The user explicitly tags it `promote`.** `tags: [promote]` in the
   transcript-summary frontmatter triggers promotion.
3. **It contains an action item for the user.** Detection is conservative:
   only when the summary's body contains a pattern like "Kayla: <verb>" or
   "[action] Kayla" AND the due date is within 7 days. Low recall on
   purpose — false-positive promotions pollute Backpack worse than false-
   negative ones do.

Promotion never happens for `scope: life` transcripts. Those stay in Hoard
under the life-state consent gate.

## What Backpack items derived from transcripts look like

```yaml
id: meetings-YYYY-MM-DD-<label>
freshness_class: current
memory_class: expiring-tactical
scope: work
dated: YYYY-MM-DD
created_at: <ISO-8601>
ttl_seconds: 1209600   # 2 weeks default for meeting summaries
source:
  kind: transcript
  ref: dailies/YYYY-MM-DD/transcripts/<file>.md
hoard_refs:
  - <hoard-id of the transcript-summary>
  - <hoard-id of the raw transcript>
tags: [meeting, <project>]
```

Body is the summary content, not the verbatim.

## Chunking long transcripts

For transcripts over ~30 minutes of speech, the summary is typically
sectional (by topic or by agenda). The adapter does NOT automatically split
these into multiple transcript-summary records; one summary = one Hoard
item. Chunking is a search concern, solved by the embedding index, not by
ingestion fragmentation.

## Transcripts as Hoard citizens

Transcripts are the paradigmatic Hoard material: write-once, append-heavy,
not required to be tidy, searchable via ripgrep or the optional embedding
index. They never decay, never expire, and never leave Hoard. Even if a
Backpack item derived from one is retired, the transcript remains.

## Failure modes this pathway guards against

- **Transcript flood in Backpack.** The default is Hoard-only; promotion
  requires a concrete trigger. Raw transcript imports never touch Backpack.
- **Silent PII retention.** Redactions are recorded per item so a search
  for "what was redacted from Monday's meeting?" is answerable.
- **Duplicate transcripts.** sha256 dedup + `ingested-duplicate` event.
- **Loss of verbatim.** The `.txt` is always preserved even when content is
  truncated in the Hoard record itself, via the attachment pointer.
- **Accidental inclusion of health material in session primers.** `tags:
  [health]` and `requires_consent: true` are added when medical terms are
  detected, so renderer consent gating catches them.
