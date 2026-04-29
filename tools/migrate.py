#!/usr/bin/env python3
"""
migrate.py — convert legacy single-file backpack.json into the file-system-as-database layout.

Production-quality migrator for snackdriven/scratch-pad's `backpack.json`.

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

Usage:
    python tools/migrate.py path/to/backpack.json path/to/output-root
    python tools/migrate.py path/to/backpack.json path/to/output-root \
        --with-hoard path/to/scratch-pad-root [--now 2026-04-29T14:00:00Z]

With ``--with-hoard`` pointing at the scratch-pad root (the directory that
contains ``dailies/`` and the loose ``*.html`` reports alongside
``backpack.json``) the migrator ALSO populates ``<output-root>/hoard/`` from
three sources:

  1. ``_config:ttl`` entries whose ``created_at + ttl_seconds`` has passed
     ``--now`` (or wall-clock UTC if omitted). Those items are written to
     hoard/ instead of backpack/, with ``aged_out_at`` stamped accordingly.
  2. Every file under ``dailies/YYYY-MM-DD/`` becomes a hoard entry under
     ``hoard/YYYY/MM/DD/<slug>.md`` with ``aged_out_at`` set to
     ``YYYY-MM-DDT12:00:00Z``.
  3. Loose ``*.html`` reports at the scratch-pad root become hoard entries
     whose ``value`` points back to the on-disk file (the migrator does not
     inline large HTML).

Writes:
    <output-root>/backpack/current/<id>.md
    <output-root>/backpack/pinned/<id>.md
    <output-root>/backpack/evergreen/<id>.md
    <output-root>/backpack/_replaced/<id>.md   (for items whose value declares replaces=...)
    <output-root>/policy/freshness.json        (skeleton, hand-edit afterward)

Does not write the index. Run `tools/bp_build.py` after migration.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

try:
    import yaml  # PyYAML
except ImportError:  # pragma: no cover
    sys.exit("PyYAML required: pip install pyyaml")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

ID_OK = re.compile(r"^[a-z0-9][a-z0-9_-]*$")

# Date extraction patterns, in priority order.
_RE_ISO_DATE = re.compile(r"\b(20\d{2})-(\d{2})-(\d{2})\b")
_RE_AS_OF = re.compile(
    r"as of\s+(20\d{2})-(\d{2})-(\d{2})", re.IGNORECASE
)


def slugify(key: str) -> str:
    """Make a legacy key safe for use as a filesystem id."""
    s = key.lower()
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    if not s:
        raise ValueError(f"empty slug from key {key!r}")
    if not ID_OK.match(s):
        raise ValueError(f"slug {s!r} from {key!r} fails id pattern")
    return s


def parse_legacy_config(value):
    """_config:pinned_keys / _config:ttl land as either JSON-encoded strings (legacy) or already-parsed objects."""
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


# ---------------------------------------------------------------------------
# Date and title mining
# ---------------------------------------------------------------------------

def extract_dated(key: str, value: str) -> str | None:
    """
    Mine a YYYY-MM-DD date from the legacy key + value text.

    Priority:
      1. `as of YYYY-MM-DD` anywhere in value
      2. Last YYYY-MM-DD in the id/key (e.g. `dsu-2026-04-07`)
      3. First YYYY-MM-DD in the value's first non-empty line
      4. Last YYYY-MM-DD anywhere in value
      5. None — caller decides fallback.
    """
    candidates: list[tuple[int, str]] = []

    # 1. "as of YYYY-MM-DD"
    if m := _RE_AS_OF.search(value):
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"

    # 2. Date in id (most reliable — operator deliberately stamped it)
    id_dates = _RE_ISO_DATE.findall(key)
    if id_dates:
        y, mo, d = id_dates[-1]
        return f"{y}-{mo}-{d}"

    # 3. First line of value
    first_line = next((ln for ln in value.splitlines() if ln.strip()), "")
    if m := _RE_ISO_DATE.search(first_line):
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"

    # 4. Anywhere in value (last wins — usually the most recent reference)
    body_dates = _RE_ISO_DATE.findall(value)
    if body_dates:
        y, mo, d = body_dates[-1]
        return f"{y}-{mo}-{d}"

    return None


def derive_summary(value: str) -> str | None:
    """
    Compress the first non-empty line into a short renderer-friendly summary.

    Returns None if nothing usable. Renderers fall back to `value` when
    summary is missing, so this is purely an optimization for surfaces
    that show a lot of items at once (statusline, daily-brief).
    """
    first = next((ln.strip() for ln in value.splitlines() if ln.strip()), "")
    if not first:
        return None

    # Sentence-end heuristic. Period + space, colon, or em-dash all reasonable.
    # Take whichever cut produces something compact.
    cuts = []
    for sep in (". ", ": ", " — ", " - "):
        idx = first.find(sep)
        if 10 <= idx <= 120:
            cuts.append(idx)
    if cuts:
        first = first[: min(cuts)].rstrip(" -—:.")

    # Hard cap.
    if len(first) > 140:
        first = first[:137].rstrip() + "…"
    if len(first) < 8:
        return None
    return first


def to_iso_z(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


# ---------------------------------------------------------------------------
# Item normalization
# ---------------------------------------------------------------------------

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
# Frontmatter writer
# ---------------------------------------------------------------------------

class _LiteralBlockDumper(yaml.SafeDumper):
    """Dump multi-line strings as literal block scalars (|) for safer round-tripping."""


def _str_representer(dumper, data):
    if "\n" in data:
        return dumper.represent_scalar("tag:yaml.org,2002:str", data, style="|")
    return dumper.represent_scalar("tag:yaml.org,2002:str", data)


_LiteralBlockDumper.add_representer(str, _str_representer)


# Stable key order for human readability of generated frontmatter.
_KEY_ORDER = [
    "id",
    "freshness_class",
    "memory_class",
    "area",
    "dated",
    "created_at",
    "ttl_seconds",
    "tags",
    "source",
    "renderer_hints",
    "doctrine_ref",
    "hoard_refs",
    "replaces",
    "summary",
    "value",
]


def _ordered(item: dict) -> dict:
    out = {}
    for k in _KEY_ORDER:
        if k in item:
            out[k] = item[k]
    # Anything not in the canonical list goes after (shouldn't happen post-normalize).
    for k, v in item.items():
        if k not in out:
            out[k] = v
    return out


def write_frontmatter_md(out_path: Path, item: dict, body: str = "") -> None:
    """Write a markdown file with YAML frontmatter for one Backpack item."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if out_path.exists():
        raise FileExistsError(f"refusing to overwrite {out_path}")
    fm = yaml.dump(
        _ordered(item),
        Dumper=_LiteralBlockDumper,
        sort_keys=False,
        allow_unicode=True,
        width=10**9,
        default_flow_style=False,
    ).strip()
    body = body.strip()
    if body:
        out_path.write_text(f"---\n{fm}\n---\n\n{body}\n", encoding="utf-8")
    else:
        out_path.write_text(f"---\n{fm}\n---\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# Hoard helpers
# ---------------------------------------------------------------------------

def _parse_iso(s: str) -> datetime | None:
    if not isinstance(s, str) or not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return None


def _hoard_path_for(out_root: Path, dated: str, item_id: str) -> Path:
    """Compose hoard/<YYYY>/<MM>/<DD>/<id>.md."""
    y, mo, d = dated.split("-")
    return out_root / "hoard" / y / mo / d / f"{item_id}.md"


def _ttl_eligible(ttl_value: dict, now: datetime) -> tuple[bool, str | None]:
    """True if `created_at + ttl_seconds <= now`. Returns expiry ISO too."""
    created = _parse_iso(ttl_value.get("created_at", ""))
    ttl_seconds = ttl_value.get("ttl_seconds")
    if created is None or not isinstance(ttl_seconds, (int, float)):
        return False, None
    expires = created + timedelta(seconds=int(ttl_seconds))
    if expires > now:
        return False, None
    return True, to_iso_z(expires)


def _slug_relpath(rel: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", rel.lower()).strip("-")
    return re.sub(r"-+", "-", s) or "item"


def _hoard_entry_for_file(
    file_path: Path,
    *,
    dated: str,
    aged_out_at: str,
    source_ref: str,
    area: str = "work",
) -> dict:
    """Build a backpack-item-shaped frontmatter dict pointing at the source file.

    Hoard files share schemas/backpack-item.schema.json per follow-up #3
    (2026-04-29) — the optional `aged_out_at` field flips the entry into
    the aged-out window for renderers. We do NOT inline large HTML; the
    `value` field carries a short pointer to the source-of-truth path.
    """
    name = file_path.name
    suffix = file_path.suffix.lower()
    if suffix == ".md":
        kind_hint = "note"
    elif suffix == ".html":
        kind_hint = "artifact"
    elif suffix in {".png", ".jpg", ".jpeg", ".gif", ".webp"}:
        kind_hint = "screenshot"
    else:
        kind_hint = "scrap"

    summary = f"{kind_hint} from {dated}: {name}"
    if len(summary) > 140:
        summary = summary[:137] + "…"

    # Include full relative path + extension so sibling files with the
    # same stem (e.g. .html vs .md) and same-name files under different
    # subdirs (transcripts/foo.md vs videos/foo.md, both `.gitkeep`, etc.)
    # don't collide on id.
    item_id = _slug_relpath(f"{dated}-{source_ref}")
    value_lines = [
        f"{dated} — {name}",
        "",
        f"Hoard pointer to source-of-truth file: `{source_ref}`.",
        "",
        "Aged out of active backpack carry-state. Open the source file for",
        "the full content (not inlined here to keep hoard files small).",
    ]

    return {
        "id": item_id,
        "value": "\n".join(value_lines),
        "summary": summary,
        "freshness_class": "historical",
        "memory_class": "timeline",
        "area": area,
        "source": {"kind": "scratch-pad", "ref": source_ref},
        "dated": dated,
        "created_at": f"{dated}T12:00:00Z",
        "aged_out_at": aged_out_at,
        "tags": ["hoard", "scratch-pad-import"],
    }


def _migrate_dailies(scratch_root: Path, out_root: Path) -> tuple[int, list[str]]:
    written = 0
    skipped: list[str] = []
    dailies = scratch_root / "dailies"
    if not dailies.is_dir():
        return 0, ["dailies/ not found"]

    date_re = re.compile(r"^(20\d{2})-(\d{2})-(\d{2})$")
    for day_dir in sorted(dailies.iterdir()):
        if not day_dir.is_dir():
            continue
        if not date_re.match(day_dir.name):
            continue
        dated = day_dir.name
        aged_out_at = f"{dated}T23:59:59Z"
        for f in sorted(day_dir.rglob("*")):
            if not f.is_file():
                continue
            if f.suffix.lower() in {".pyc", ".ds_store"}:
                continue
            rel = f.relative_to(scratch_root).as_posix()
            entry = _hoard_entry_for_file(
                f, dated=dated, aged_out_at=aged_out_at, source_ref=rel,
            )
            out_path = _hoard_path_for(out_root, dated, entry["id"])
            try:
                write_frontmatter_md(out_path, entry)
                written += 1
            except FileExistsError as exc:
                skipped.append(str(exc))
    return written, skipped


def _migrate_loose_artifacts(
    scratch_root: Path, out_root: Path, *, now: datetime
) -> tuple[int, list[str]]:
    """Hoard loose *.html / *.md / image files at the scratch-pad root."""
    written = 0
    skipped: list[str] = []
    today_iso = now.date().isoformat()
    today_aged = to_iso_z(now)

    skip_names = {
        "backpack.json", "README.md", "CLAUDE.md", "AGENTS.md",
        "package.json", "qa-onboarding-guide.md",
        "platform-dev-staging-access.md",
    }
    for f in sorted(scratch_root.iterdir()):
        if not f.is_file():
            continue
        if f.suffix.lower() not in {".html", ".md", ".png", ".jpg", ".jpeg"}:
            continue
        if f.name in skip_names:
            continue
        m = _RE_ISO_DATE.search(f.stem)
        if m:
            dated = f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
            aged_out_at = f"{dated}T23:59:59Z"
        else:
            dated = today_iso
            aged_out_at = today_aged
        rel = f.relative_to(scratch_root).as_posix()
        entry = _hoard_entry_for_file(
            f, dated=dated, aged_out_at=aged_out_at, source_ref=rel,
        )
        out_path = _hoard_path_for(out_root, dated, entry["id"])
        try:
            write_frontmatter_md(out_path, entry)
            written += 1
        except FileExistsError as exc:
            skipped.append(str(exc))
    return written, skipped


# ---------------------------------------------------------------------------
# Migration entrypoint
# ---------------------------------------------------------------------------

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

        if isinstance(pinned_keys, list) and key in pinned_keys:
            # Schema has no `pinned` field — express pinning via freshness_class.
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
            # explicitly chosen to keep them visible.
            if item.get("freshness_class") != "pinned":
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
            out_path = _hoard_path_for(out_root, dated, item["id"])
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
        d_w, d_s = _migrate_dailies(scratch_root, out_root)
        l_w, l_s = _migrate_loose_artifacts(scratch_root, out_root, now=now)
        hoard_stats["dailies"] = d_w
        hoard_stats["loose"] = l_w
        for reason in d_s + l_s:
            skipped.append(("hoard", reason))

    # Skeleton freshness policy. Hand-edit afterward.
    freshness_skeleton = {
        "version": "0.1.0",
        "generated_from": "backpack.json (migration)",
        "ttl_presets": {
            "1w": 604800,
            "2w": 1209600,
            "30d": 2592000,
            "90d": 7776000,
        },
        "bands": [
            {"name": "current", "ttl_default_seconds": 1209600},
            {"name": "recent", "ttl_default_seconds": 2592000},
            {"name": "contextual", "ttl_default_seconds": 7776000},
            {"name": "evergreen", "ttl_default_seconds": None},
        ],
        "ttl_overrides": ttl_config if isinstance(ttl_config, dict) else {},
        "pinned_keys": pinned_keys if isinstance(pinned_keys, list) else [],
    }
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
        parsed = _parse_iso(args.now)
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
