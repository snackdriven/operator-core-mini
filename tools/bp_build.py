#!/usr/bin/env python3
"""
bp_build.py — regenerate the machine-written indexes that renderers consume.

Sketch / reference implementation. Not a production tool. Intent:
  - Walk backpack/, doctrine/, hoard/ in the operator root.
  - For each markdown file with YAML frontmatter, parse the frontmatter and
    treat it as a per-item record (validates against backpack-item.schema.json
    or doctrine-entry.schema.json elsewhere).
  - Emit:
      backpack/_index.json           kind: backpack-index, items: object-of-id
      doctrine/doctrine.lock.json    kind: doctrine-index, items: object-of-id
      hoard/_hoard.jsonl             one record per line (already-flat Hoard)
  - Indexes validate against schemas/index.schema.json (kind enum constrains).

Non-goals: validation of per-item content, demotion, promotion, ingestion.
Those are in pathway adapters and the renderer layer, not here.

Usage:
    python tools/bp_build.py path/to/operator-root [--source-commit <sha>]

Exit 0 on success; 1 on missing root; 2 on bad frontmatter found
(prints the offending file and continues).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover
    sys.exit("PyYAML required: pip install pyyaml")


INDEX_VERSION = "0.1.0"


# ---------------------------------------------------------------------------
# Frontmatter parsing
# ---------------------------------------------------------------------------

def split_frontmatter(text: str) -> tuple[dict, str]:
    """Return (frontmatter_dict, body). Empty dict if no frontmatter."""
    if not text.startswith("---"):
        return {}, text
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}, text
    _, fm_text, body = parts
    fm = yaml.safe_load(fm_text) or {}
    if not isinstance(fm, dict):
        raise ValueError("frontmatter is not a mapping")
    return fm, body.strip()


def iter_md(root: Path):
    for path in root.rglob("*.md"):
        if any(part.startswith(".") for part in path.parts):
            continue
        yield path


# ---------------------------------------------------------------------------
# Per-layer build steps
# ---------------------------------------------------------------------------

def build_backpack_index(operator_root: Path, source_commit: str | None) -> dict | None:
    bp_root = operator_root / "backpack"
    if not bp_root.exists():
        return None

    items: dict[str, dict] = {}
    by_freshness: dict[str, int] = {}
    by_scope: dict[str, int] = {}
    pinned_keys: list[str] = []

    for path in iter_md(bp_root):
        # Skip _replaced/ — retired items don't surface in indexes.
        if "_replaced" in path.parts:
            continue
        try:
            fm, _ = split_frontmatter(path.read_text(encoding="utf-8"))
        except (ValueError, yaml.YAMLError) as exc:
            print(f"bad frontmatter in {path}: {exc}", file=sys.stderr)
            continue
        item_id = fm.get("id")
        if not item_id:
            print(f"no id in {path}", file=sys.stderr)
            continue
        items[item_id] = fm
        fc = fm.get("freshness_class") or "current"
        by_freshness[fc] = by_freshness.get(fc, 0) + 1
        scope = fm.get("scope") or "work"
        by_scope[scope] = by_scope.get(scope, 0) + 1
        if fm.get("pinned"):
            pinned_keys.append(item_id)

    return {
        "kind": "backpack-index",
        "version": INDEX_VERSION,
        "generated_at": _now(),
        **({"source_commit": source_commit} if source_commit else {}),
        "source_root": "backpack/",
        "pinned_keys": pinned_keys,
        "items": items,
        "stats": {
            "count": len(items),
            "by_freshness": by_freshness,
            "by_scope": by_scope,
            "stale_count": 0,  # caller wires demotion sweeps; build does not.
        },
    }


def build_doctrine_index(operator_root: Path, source_commit: str | None) -> dict | None:
    d_root = operator_root / "doctrine"
    if not d_root.exists():
        return None

    items: dict[str, dict] = {}
    by_kind: dict[str, int] = {}

    for path in iter_md(d_root):
        try:
            fm, _ = split_frontmatter(path.read_text(encoding="utf-8"))
        except (ValueError, yaml.YAMLError) as exc:
            print(f"bad frontmatter in {path}: {exc}", file=sys.stderr)
            continue
        if not fm.get("id"):
            continue
        items[fm["id"]] = fm
        k = fm.get("kind") or "unspecified"
        by_kind[k] = by_kind.get(k, 0) + 1

    return {
        "kind": "doctrine-index",
        "version": INDEX_VERSION,
        "generated_at": _now(),
        **({"source_commit": source_commit} if source_commit else {}),
        "source_root": "doctrine/",
        "items": items,
        "stats": {
            "count": len(items),
            "by_scope": by_kind,  # piggyback the by_scope slot
        },
    }


def build_hoard_jsonl(operator_root: Path) -> int:
    """
    Hoard is already JSONL-shaped on disk: hoard/YYYY/MM/DD/<id>.json plus
    blob attachments. The 'index' is a single concatenated _hoard.jsonl that
    renderers stream-read. Returns the count written.
    """
    h_root = operator_root / "hoard"
    if not h_root.exists():
        return 0

    out = h_root / "_hoard.jsonl"
    count = 0
    with out.open("w", encoding="utf-8") as f:
        for path in sorted(h_root.rglob("*.json")):
            if path.name == "_hoard.jsonl":
                continue
            if path.parent.name == "blobs":
                continue
            try:
                rec = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                print(f"bad hoard record {path}: {exc}", file=sys.stderr)
                continue
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            count += 1
    return count


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operator_root")
    parser.add_argument("--source-commit", default=None)
    args = parser.parse_args(argv[1:])

    root = Path(args.operator_root)
    if not root.exists():
        print(f"not found: {root}", file=sys.stderr)
        return 1

    # Backpack index
    bp_index = build_backpack_index(root, args.source_commit)
    if bp_index is not None:
        out = root / "backpack" / "_index.json"
        out.write_text(json.dumps(bp_index, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"wrote {out} ({bp_index['stats']['count']} items)")

    # Doctrine index
    d_index = build_doctrine_index(root, args.source_commit)
    if d_index is not None:
        out = root / "doctrine" / "doctrine.lock.json"
        out.write_text(json.dumps(d_index, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"wrote {out} ({d_index['stats']['count']} items)")

    # Hoard JSONL
    h_count = build_hoard_jsonl(root)
    if h_count:
        print(f"wrote {root / 'hoard' / '_hoard.jsonl'} ({h_count} records)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
