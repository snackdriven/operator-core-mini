#!/usr/bin/env python3
"""
migrate.py — convert legacy single-file backpack.json into the file-system-as-database layout.

Production-quality migrator for snackdriven/scratch-pad's `backpack.json`.

This file is the BACKPACK migrator. The Hoard side (filesystem walks of
``dailies/`` and loose artifacts) lives in ``tools/migrate_hoard.py``;
shared id/date/yaml helpers live in ``tools/_migrate_common.py``. The
TTL diversion logic stays here because it acts on backpack items, not
filesystem artifacts: when ``_config:ttl`` declares an item is past
expiry, this module writes that item under ``hoard/`` instead of
``backpack/`` so renderers see a properly-stamped ``aged_out_at``.

Behavior:
  - Read a legacy backpack.json (the live shape from snackdriven/scratch-pad).
  - For each non-config key, write one markdown file with YAML frontmatter
    under backpack/<freshness>/<id>.md, schema-clean per
    schemas/backpack-item.schema.json (Phase 4, post-#7-`area` rename).
  - Mine `dated` and `created_at` from the value text (or the id) so the
    aged-out / freshness logic in the renderers actually has signal.
  - Convert legacy _config:pinned_keys / _config:ttl into structured form.
  - Refuse to overwrite existing files (idempotent re-runs are fine; conflicts
    must be explicit).
  - When ``--with-hoard`` is supplied, delegate the filesystem hoard walk
    to ``migrate_hoard.migrate_hoard(...)``.

Usage:
    python tools/migrate.py path/to/backpack.json path/to/output-root
    python tools/migrate.py path/to/backpack.json path/to/output-root \\
        --with-hoard path/to/scratch-pad-root [--now 2026-04-29T14:00:00Z]

Writes:
    <output-root>/backpack/current/<id>.md
    <output-root>/backpack/pinned/<id>.md
    <output-root>/backpack/evergreen/<id>.md
    <output-root>/backpack/_replaced/<id>.md   (for items whose value declares replaces=...)
    <output-root>/hoard/<YYYY>/<MM>/<DD>/<id>.md  (TTL-diverted + --with-hoard sources)
    <output-root>/policy/freshness.json        (skeleton, hand-edit afterward)

Does not write the backpack/_index.json or hoard/_hoard.jsonl. Run
``tools/bp_build.py`` after migration.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Allow `python tools/migrate.py …` to import sibling modules.
_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from _migrate_common import (  # noqa: E402
    parse_iso,
    slugify,
    to_iso_z,
    write_frontmatter_md,
)
from migrate_hoard import (  # noqa: E402
    hoard_path_for,
    migrate_hoard,
)
from _migrate_common import (  # noqa: E402
    derive_summary,
    extract_dated,
)


# ---------------------------------------------------------------------------
# Schema validation (post-write assertion for the freshness skeleton)
# ---------------------------------------------------------------------------

def _validate_freshness_skeleton(skeleton: dict) -> None:
    """Validate the freshness-policy skeleton against its schema.

    Raises ``RuntimeError`` if validation fails. Best-effort: if jsonschema
    is unavailable in the environment, skip silently — the central
    ``tools/validate.py`` suite is the source of truth.
    """
    try:
        from jsonschema import Draft202012Validator  # type: ignore
    except ImportError:  # pragma: no cover
        return
    schema_path = Path(__file__).resolve().parent.parent / "schemas" / "freshness-policy.schema.json"
    if not schema_path.is_file():
        return
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    errors = sorted(
        Draft202012Validator(schema).iter_errors(skeleton),
        key=lambda e: list(e.absolute_path),
    )
    if errors:
        details = "; ".join(
            f"{'/'.join(map(str, e.absolute_path)) or '<root>'}: {e.message}"
            for e in errors[:5]
        )
        raise RuntimeError(
            f"freshness-policy skeleton is schema-invalid ({len(errors)} errors): {details}"
        )


# ---------------------------------------------------------------------------
# Backpack helpers
# ---------------------------------------------------------------------------

def parse_legacy_config(value):
    """``_config:pinned_keys`` / ``_config:ttl`` arrive as JSON strings (legacy)
    or already-parsed objects. Decode strings; pass through dicts/lists."""
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value  # leave as-is; let the validator complain
    return value


def freshness_dir(item: dict) -> str:
    """Map an item to a backpack subdirectory."""
    fc = item.get("freshness_class")
    mc = item.get("memory_class")

    if fc == "evergreen" or mc == "evergreen-reference":
        return "evergreen"
    if fc == "pinned" or mc == "pinned-doctrine":
        return "pinned"
    if fc == "removed":
        return "_replaced"
    # current / recent / contextual / historical all surface as "current" until
    # a later sweep moves stale items out. The freshness policy (not migration)
    # decides demotion timing.
    return "current"


# Legacy "scope" → schema "area" enum mapping. Anything else lands on "work".
_AREA_FALLBACK = {
    "work": "work",
    "life": "life",
    "assistant": "assistant",
    "identity": "identity",
    "meta": "meta",
}


def normalize_value(key: str, value, *, now_iso: str) -> dict:
    """
    Bring a legacy value into the current backpack-item schema shape.

    Schema (post-#7-`area`-rename):
      required: value, freshness_class (id required for standalone files)
      allowed:  id, value, summary, freshness_class, memory_class, area,
                source, dated, created_at, ttl_seconds, review_after, tags,
                renderer_hints, doctrine_ref, hoard_refs, replaces, aged_out_at
      additionalProperties: false  (so no _meta, no scope, no title)
    """
    item_id = slugify(key)

    # Already-structured legacy entry? Pass through, repair as needed.
    if isinstance(value, dict):
        item = dict(value)
        item.setdefault("id", item_id)
        # Legacy entries used `scope` for area. Promote.
        if "scope" in item and "area" not in item:
            item["area"] = _AREA_FALLBACK.get(item.pop("scope"), "work")
        # Strip schema-illegal keys.
        for bad in ("_meta", "title"):
            item.pop(bad, None)
        # Provenance.
        item.setdefault(
            "source",
            {"kind": "scratch-pad", "ref": "backpack.json"},
        )
        item.setdefault("freshness_class", "current")
        return item

    if not isinstance(value, str):
        raise TypeError(f"unexpected legacy value type for {key!r}: {type(value).__name__}")

    # Raw-string entry. Wrap with mined metadata.
    dated = extract_dated(key, value)
    created_at: str
    if dated:
        # Stamp creation at midday on the dated date (avoids 23:59 / 00:00 fenceposts).
        created_at = f"{dated}T12:00:00Z"
    else:
        # Unknown age. Use now so renderers don't crash, but mark as evergreen
        # downstream so it isn't surfaced as "near today".
        created_at = now_iso

    item: dict = {
        "id": item_id,
        "value": value,
        "freshness_class": "current",
        "memory_class": "expiring-tactical",
        "area": "work",
        "source": {"kind": "scratch-pad", "ref": "backpack.json"},
        "created_at": created_at,
    }

    if dated:
        item["dated"] = dated
    else:
        # No date anywhere — best classified as evergreen reference until the
        # operator hand-edits a real `dated:`.
        item["freshness_class"] = "evergreen"
        item["memory_class"] = "evergreen-reference"

    summary = derive_summary(value)
    if summary:
        item["summary"] = summary

    return item


# ---------------------------------------------------------------------------
# TTL diversion (backpack → hoard)
# ---------------------------------------------------------------------------

def _ttl_eligible(ttl_value: dict, now: datetime) -> tuple[bool, str | None]:
    """Return (eligible, expiry_iso). Eligible iff ``created_at + ttl_seconds <= now``."""
    created = parse_iso(ttl_value.get("created_at", ""))
    ttl_seconds = ttl_value.get("ttl_seconds")
    if created is None or not isinstance(ttl_seconds, (int, float)):
        return False, None
    expires = created + timedelta(seconds=int(ttl_seconds))
    if expires > now:
        return False, None
    return True, to_iso_z(expires)


# ---------------------------------------------------------------------------
# Migration entrypoint
# ---------------------------------------------------------------------------

def _build_freshness_skeleton(
    ttl_config, pinned_keys, *, now_iso: str
) -> dict:
    """Return a schema-clean ``freshness-policy.schema.json`` skeleton.

    Emits the required ``rules`` block, ``bands`` with ``max_age_days`` +
    ``treatment`` (NOT ``ttl_default_seconds``), plus optional
    ``ttl_presets`` + ``pinned_keys``. Crucially, the legacy
    ``ttl_overrides`` map is dropped — it has no place in the schema —
    and is reconstructable from the items themselves via
    ``ttl_seconds`` on each backpack-item.
    """
    return {
        "version": "0.1.0",
        "updated_at": now_iso,
        "bands": [
            {"name": "current",    "max_age_days": 1,     "treatment": "trust",                            "renderer_priority": 90},
            {"name": "recent",     "max_age_days": 7,     "treatment": "mostly-reliable-verify-specifics", "renderer_priority": 70},
            {"name": "contextual", "max_age_days": 28,    "treatment": "good-for-patterns-verify-details", "renderer_priority": 50},
            {"name": "historical", "max_age_days": 120,   "treatment": "culture-pattern-only",             "renderer_priority": 25},
            {"name": "evergreen",  "max_age_days": 36500, "treatment": "refresh-periodically",             "renderer_priority": 60},
        ],
        "rules": {
            "verify_after_days": 7,
            "require_dated_entries": True,
            "update_in_place": True,
            "patterns_age_slower_than_tactics": True,
            "promote_to_doctrine_after_days": 90,
            "demote_to_hoard_after_days": 60,
        },
        "ttl_presets": {
            "snapshot": 604800,
            "tactical": 1209600,
            "fix-thread": 2592000,
            "quarter": 7776000,
        },
        "pinned_keys": pinned_keys if isinstance(pinned_keys, list) else [],
    }


def migrate(
    legacy_path: Path,
    out_root: Path,
    *,
    scratch_root: Path | None = None,
    now: datetime | None = None,
) -> dict:
    legacy = json.loads(legacy_path.read_text(encoding="utf-8"))
    if now is None:
        now = datetime.now(timezone.utc)
    now_iso = to_iso_z(now)

    # Pull config aside.
    pinned_keys = parse_legacy_config(legacy.pop("_config:pinned_keys", []))
    ttl_config = parse_legacy_config(legacy.pop("_config:ttl", {}))

    written: list[Path] = []
    skipped: list[tuple[str, str]] = []
    undated: list[str] = []
    aged_out_via_ttl: list[str] = []

    for key, value in legacy.items():
        if key.startswith("_config:"):
            # Defensive: skip any other config keys we didn't pre-extract.
            continue
        try:
            item = normalize_value(key, value, now_iso=now_iso)
        except Exception as exc:
            skipped.append((key, str(exc)))
            continue

        is_pinned_key = isinstance(pinned_keys, list) and key in pinned_keys
        if is_pinned_key:
            # Schema has no `pinned` field — express pinning via freshness_class.
            # Evergreen items are already preserved across surfaces, so we
            # leave that signal intact rather than overwriting with `pinned`.
            if item.get("freshness_class") not in {"pinned", "evergreen"}:
                item["freshness_class"] = "pinned"

        # TTL diversion: if the legacy _config:ttl says this item is already
        # past expiry, write it to hoard/ instead of backpack/ and stamp
        # aged_out_at so renderers pick it up as real aged-out content.
        ttl_value = ttl_config.get(key) if isinstance(ttl_config, dict) else None
        diverted_to_hoard = False
        if isinstance(ttl_value, dict):
            if "created_at" in ttl_value:
                item["created_at"] = ttl_value["created_at"]
            if "ttl_seconds" in ttl_value:
                item["ttl_seconds"] = int(ttl_value["ttl_seconds"])
            # Pinned items are preserved even if stale — the operator has
            # explicitly chosen to keep them visible. We check both the
            # explicit pinned-keys list AND the freshness_class to catch
            # items where pinning is expressed structurally.
            if not is_pinned_key and item.get("freshness_class") != "pinned":
                eligible, aged_out_at = _ttl_eligible(ttl_value, now)
                if eligible and aged_out_at:
                    item["aged_out_at"] = aged_out_at
                    item["freshness_class"] = "historical"
                    item["memory_class"] = "timeline"
                    diverted_to_hoard = True
                    aged_out_via_ttl.append(item["id"])
        elif isinstance(ttl_value, (int, float)):
            item["ttl_seconds"] = int(ttl_value)

        if "dated" not in item and item.get("freshness_class") != "evergreen":
            undated.append(item["id"])

        body = item.pop("body", "") if isinstance(item.get("body"), str) else ""
        if diverted_to_hoard:
            dated = item.get("dated") or now.date().isoformat()
            out_path = hoard_path_for(out_root, dated, item["id"])
        else:
            sub = freshness_dir(item)
            out_path = out_root / "backpack" / sub / f"{item['id']}.md"
        try:
            write_frontmatter_md(out_path, item, body=body)
            written.append(out_path)
        except FileExistsError as exc:
            skipped.append((key, str(exc)))

    # Hoard from scratch-pad filesystem (dailies + loose artifacts).
    hoard_stats = {"dailies": 0, "loose": 0}
    if scratch_root is not None:
        result = migrate_hoard(scratch_root, out_root, now=now)
        hoard_stats["dailies"] = result["dailies_written"]
        hoard_stats["loose"] = result["loose_written"]
        for reason in result["skipped"]:
            skipped.append(("hoard", reason))

    # Schema-clean freshness-policy skeleton. Hand-edit afterward.
    freshness_skeleton = _build_freshness_skeleton(
        ttl_config, pinned_keys, now_iso=now_iso,
    )
    _validate_freshness_skeleton(freshness_skeleton)  # asserts schema-clean
    policy_path = out_root / "policy" / "freshness.json"
    policy_path.parent.mkdir(parents=True, exist_ok=True)
    if not policy_path.exists():
        policy_path.write_text(
            json.dumps(freshness_skeleton, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    return {
        "written": [str(p) for p in written],
        "skipped": skipped,
        "undated": undated,
        "aged_out_via_ttl": aged_out_via_ttl,
        "hoard_stats": hoard_stats,
        "policy_path": str(policy_path),
    }


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="migrate.py",
        description="Migrate legacy scratch-pad backpack.json into the FS-as-DB layout.",
    )
    parser.add_argument("legacy_path", help="Path to backpack.json")
    parser.add_argument("out_root", help="Output operator-root directory")
    parser.add_argument(
        "--with-hoard",
        dest="scratch_root",
        metavar="PATH",
        help="Path to scratch-pad root (containing dailies/ and loose *.html). "
             "If set, populate hoard/ from dailies + loose artifacts.",
    )
    parser.add_argument(
        "--now",
        dest="now",
        metavar="ISO",
        help="Wall-clock 'now' for TTL expiry decisions (ISO-8601). "
             "Defaults to real UTC now.",
    )
    args = parser.parse_args(argv[1:])

    legacy_path = Path(args.legacy_path)
    out_root = Path(args.out_root)
    if not legacy_path.exists():
        print(f"not found: {legacy_path}", file=sys.stderr)
        return 1
    scratch_root: Path | None = None
    if args.scratch_root:
        scratch_root = Path(args.scratch_root)
        if not scratch_root.is_dir():
            print(f"not a directory: {scratch_root}", file=sys.stderr)
            return 1
    now: datetime | None = None
    if args.now:
        parsed = parse_iso(args.now)
        if parsed is None:
            print(f"bad --now: {args.now}", file=sys.stderr)
            return 1
        now = parsed

    result = migrate(legacy_path, out_root, scratch_root=scratch_root, now=now)
    print(f"wrote {len(result['written'])} files under {out_root}")
    if result["undated"]:
        print(
            f"  {len(result['undated'])} item(s) had no extractable date; "
            "promoted to evergreen.",
        )
    if result["aged_out_via_ttl"]:
        print(
            f"  {len(result['aged_out_via_ttl'])} item(s) past TTL expiry; "
            "diverted to hoard/.",
        )
    if result["hoard_stats"]["dailies"] or result["hoard_stats"]["loose"]:
        print(
            f"  hoard additions: {result['hoard_stats']['dailies']} from dailies/, "
            f"{result['hoard_stats']['loose']} from loose artifacts.",
        )
    if result["skipped"]:
        print(f"skipped {len(result['skipped'])}:", file=sys.stderr)
        for key, reason in result["skipped"]:
            print(f"  {key}: {reason}", file=sys.stderr)
    print(f"freshness policy skeleton: {result['policy_path']}")
    print("next: run tools/bp_build.py to regenerate indexes.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
