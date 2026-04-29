# tools/

Reference-implementation scripts that demonstrate how the file-system-as-database
layout is produced and maintained. These are **sketches**, not a production
toolchain. They exist so the schemas and the recommended layout in
[../schemas/README.md](../schemas/README.md) are anchored to runnable code.

## Scripts

| Script | Purpose |
|---|---|
| `validate.py` | Run the full validation suite: schemas self-valid + every example payload + delegates to `lint.py` + delegates to `test_renderers.py`. This is what CI runs. |
| `lint.py` | Structural lint that JSON Schema can't express: 2-space indent, trailing newlines, JSONL one-record-per-line, ULID-shaped trace filenames, frontmatter parses, internal markdown links resolve, no TODO markers in schemas. Also a warn-only check (`hoard-aged-out-at`) that flags hoard markdown files missing `aged_out_at`; warnings print but never affect exit status. |
| `test_renderers.py` | Golden-output tests for `renderers/`. Two-tier: deterministic surfaces (session-primer, daily-brief, statusline, narrator-brief prompt) must match snapshots byte-for-byte; voice-aware surfaces (narrator-list, energy-routed narrator-brief) require the structural fingerprint (section order + bolded fact ids) to match while snapshot drift surfaces as `[ADVISORY]`. |
| `migrate.py` | Convert a legacy single-file `backpack.json` into the per-item markdown-with-frontmatter layout. Writes a freshness-policy skeleton. |
| `bp_build.py` | Walk the operator root and regenerate the machine-written indexes (`backpack/_index.json`, `doctrine/doctrine.lock.json`, `hoard/_hoard.jsonl`). |

## Usage — validate + lint

```bash
pip install jsonschema pyyaml
python tools/validate.py    # full suite (recommended)
python tools/lint.py        # lint only (faster, when iterating on file layout)
```

Both exit non-zero on any failure. Run from any directory; both scripts
resolve the repo root from their own location.

## Usage — migrate + build

### One-shot migration

```bash
# Source: a legacy backpack.json from snackdriven/scratch-pad
python tools/migrate.py /path/to/backpack.json /path/to/operator-root
```

This produces:

```
operator-root/
├── backpack/
│   ├── current/<id>.md          # YAML frontmatter validates against backpack-item.schema.json
│   ├── pinned/<id>.md
│   ├── evergreen/<id>.md
│   └── _replaced/<id>.md        # only for items whose value declared replaces=...
└── policy/
    └── freshness.json           # validates against freshness-policy.schema.json (skeleton; hand-edit)
```

After migration, run the index build (below) so renderers can do one read.

### Index regeneration

```bash
python tools/bp_build.py /path/to/operator-root [--source-commit <git-sha>]
```

Idempotent. Reads every `*.md` under `backpack/` and `doctrine/`, parses
frontmatter, and writes the corresponding `_index.json` /
`doctrine.lock.json`. For Hoard it concatenates per-day JSON records into
`_hoard.jsonl` for stream reads.

The indexes always validate against `schemas/index.schema.json`.

## What these scripts deliberately don't do

- **Validate per-item content.** That's the contributor's job (see
  [../CONTRIBUTING.md](../CONTRIBUTING.md)). Frontmatter that fails its
  schema will still be indexed; downstream consumers should reject it.
- **Promote, demote, retire.** Lifecycle ops belong to the ingestion
  pathways (`docs/ingestion/`). Build is a pure projection over current
  on-disk state.
- **Touch Hoard semantics.** Hoard is already file-per-record; build only
  stitches the JSONL view.
- **Run continuously.** Trigger `bp_build.py` after each ingestion event
  via a hook, cron, or save action — not as a daemon.

## When to rewrite these

If real usage shows the scripts make the wrong assumption (e.g. the
freshness-policy skeleton is consistently hand-thrown-away, or the build
walk gets too slow on a real corpus), rewrite them. The schemas are the
contract; the tools are not.
