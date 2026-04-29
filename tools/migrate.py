#!/usr/bin/env python3
"""
migrate.py — convert legacy single-file backpack.json into the file-system-as-database layout.

Sketch / reference implementation. Not a production tool. Intent:
  - Read a legacy backpack.json (the live shape from snackdriven/scratch-pad).
  - For each non-config key, write one markdown file with YAML frontmatter
    under backpack/<freshness>/<id>.md.
  - Convert legacy _config:pinned_keys / _config:ttl into structured form.
  - Validate every produced frontmatter against schemas/backpack-item.schema.json.
  - Refuse to overwrite existing files (idempotent re-runs are fine; conflicts must be explicit).

Usage:
    python tools/migrate.py path/to/backpack.json path/to/output-root

Writes:
    <output-root>/backpack/current/<id>.md
    <output-root>/backpack/pinned/<id>.md
    <output-root>/backpack/evergreen/<id>.md
    <output-root>/backpack/_replaced/<id>.md   (for items whose value declares replaces=...)
    <output-root>/policy/freshness.json        (skeleton, hand-edit afterward)

Does not write the index. Run `tools/bp_build.py` after migration.
"""
from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

try:
    import yaml  # PyYAML
except ImportError:  # pragma: no cover
    sys.exit("PyYAML required: pip install pyyaml")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

ID_OK = re.compile(r"^[a-z0-9][a-z0-9_-]*$")


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
    if fc == "pinned" or mc == "pinned-doctrine" or item.get("pinned"):
        return "pinned"
    if fc == "removed":
        return "_replaced"
    # current / recent / contextual / historical all surface as "current" until
    # a later sweep moves stale items out. The freshness policy (not migration)
    # decides demotion timing.
    return "current"


def normalize_value(key: str, value) -> dict:
    """
    Bring a legacy value into the structured backpack-item shape.

    Legacy entries can be:
      - raw strings (e.g. {"task-status-2026-04-22": "Work in progress on..."})
      - structured objects already matching backpack-item.schema.json
    The structured form is preferred. Strings are wrapped with sane defaults.
    """
    now_iso = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    item_id = slugify(key)

    if isinstance(value, str):
        return {
            "id": item_id,
            "title": key,
            "value": value,
            "memory_class": "expiring-tactical",
            "freshness_class": "current",
            "scope": "work",  # caller can override; we don't guess.
            "_meta": {
                "created_at": now_iso,
                "last_updated": now_iso,
                "migrated_from": "backpack.json",
            },
        }

    if not isinstance(value, dict):
        raise TypeError(f"unexpected legacy value type for {key!r}: {type(value).__name__}")

    # Already structured. Preserve, ensure id is present, add migration breadcrumb.
    item = dict(value)
    item.setdefault("id", item_id)
    meta = dict(item.get("_meta") or {})
    meta.setdefault("created_at", now_iso)
    meta.setdefault("last_updated", now_iso)
    meta["migrated_from"] = "backpack.json"
    item["_meta"] = meta
    return item


class _LiteralBlockDumper(yaml.SafeDumper):
    """Dump multi-line strings as literal block scalars (|) for safer round-tripping."""


def _str_representer(dumper, data):
    if "\n" in data:
        return dumper.represent_scalar("tag:yaml.org,2002:str", data, style="|")
    return dumper.represent_scalar("tag:yaml.org,2002:str", data)


_LiteralBlockDumper.add_representer(str, _str_representer)


def write_frontmatter_md(out_path: Path, item: dict, body: str = "") -> None:
    """Write a markdown file with YAML frontmatter for one Backpack item."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if out_path.exists():
        raise FileExistsError(f"refusing to overwrite {out_path}")
    fm = yaml.dump(
        item,
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
# Migration entrypoint
# ---------------------------------------------------------------------------

def migrate(legacy_path: Path, out_root: Path) -> dict:
    legacy = json.loads(legacy_path.read_text(encoding="utf-8"))

    # Pull config aside.
    pinned_keys = parse_legacy_config(legacy.pop("_config:pinned_keys", []))
    ttl_config = parse_legacy_config(legacy.pop("_config:ttl", {}))

    written: list[Path] = []
    skipped: list[tuple[str, str]] = []

    for key, value in legacy.items():
        try:
            item = normalize_value(key, value)
        except Exception as exc:
            skipped.append((key, str(exc)))
            continue

        if isinstance(pinned_keys, list) and key in pinned_keys:
            item.setdefault("pinned", True)
            if item.get("freshness_class") not in {"pinned", "evergreen"}:
                item["freshness_class"] = "pinned"

        if isinstance(ttl_config, dict) and key in ttl_config:
            ttl_block = item.setdefault("ttl", {})
            ttl_block.setdefault("seconds", ttl_config[key])

        sub = freshness_dir(item)
        out_path = out_root / "backpack" / sub / f"{item['id']}.md"
        body = item.pop("body", "")
        try:
            write_frontmatter_md(out_path, item, body=body)
            written.append(out_path)
        except FileExistsError as exc:
            skipped.append((key, str(exc)))

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
        "policy_path": str(policy_path),
    }


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print(__doc__, file=sys.stderr)
        return 2
    legacy_path = Path(argv[1])
    out_root = Path(argv[2])
    if not legacy_path.exists():
        print(f"not found: {legacy_path}", file=sys.stderr)
        return 1
    result = migrate(legacy_path, out_root)
    print(f"wrote {len(result['written'])} files under {out_root}")
    if result["skipped"]:
        print(f"skipped {len(result['skipped'])}:", file=sys.stderr)
        for key, reason in result["skipped"]:
            print(f"  {key}: {reason}", file=sys.stderr)
    print(f"freshness policy skeleton: {result['policy_path']}")
    print("next: run tools/bp_build.py to regenerate indexes.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
