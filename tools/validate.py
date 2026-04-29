#!/usr/bin/env python3
"""
validate.py — run the operator-core-schemas validation suite.

Self-validates every schema, then validates every example payload against
its declared schema. Mirrors the CI loop described in CONTRIBUTING.md.

Usage:
    python tools/validate.py [repo-root]

Exits 0 on full success, 1 on any failure (prints the offender).
Requires: jsonschema, pyyaml.
"""
from __future__ import annotations

import json
import glob
import os
import re
import sys
import warnings
from pathlib import Path

warnings.filterwarnings("ignore", category=DeprecationWarning)

import yaml  # type: ignore
from jsonschema import Draft202012Validator, RefResolver  # type: ignore


# ---------------------------------------------------------------------------
# Schema loading
# ---------------------------------------------------------------------------

def load_schemas(repo_root: Path) -> tuple[dict, dict]:
    schemas: dict[str, dict] = {}
    store: dict[str, dict] = {}
    for f in sorted(glob.glob(str(repo_root / "schemas" / "*.schema.json"))):
        s = json.load(open(f))
        Draft202012Validator.check_schema(s)
        rel = os.path.relpath(f, repo_root)
        schemas[rel] = s
        if "$id" in s:
            store[s["$id"]] = s
            store[s["$id"].rsplit("/", 1)[-1]] = s
        store[rel] = s
    return schemas, store


def make_validator(schema_rel: str, schemas: dict, store: dict) -> Draft202012Validator:
    """Fresh resolver per validation; RefResolver caches can leak otherwise."""
    s = schemas[schema_rel]
    base = s.get("$id", f"file:///{schema_rel}")
    resolver = RefResolver(base_uri=base, referrer=s, store=store)
    return Draft202012Validator(s, resolver=resolver)


# ---------------------------------------------------------------------------
# Frontmatter loader
# ---------------------------------------------------------------------------

class _StringDateLoader(yaml.SafeLoader):
    """Keep ISO date strings as strings instead of converting to date objects."""


_StringDateLoader.add_constructor(
    "tag:yaml.org,2002:timestamp",
    lambda loader, node: loader.construct_scalar(node),
)


def load_frontmatter(path: Path) -> dict:
    """Read a markdown file with YAML frontmatter and merge body into 'value' if absent."""
    text = path.read_text(encoding="utf-8")
    m = re.match(r"---\n(.*?)\n---\n?(.*)", text, re.S)
    if not m:
        raise ValueError(f"no frontmatter in {path}")
    fm = yaml.load(m.group(1), Loader=_StringDateLoader) or {}
    body = m.group(2).strip()
    if isinstance(fm, dict) and "value" not in fm and body:
        fm["value"] = body
    return fm


# ---------------------------------------------------------------------------
# Suite
# ---------------------------------------------------------------------------

def run(repo_root: Path) -> bool:
    schemas, store = load_schemas(repo_root)
    print(f"[OK] {len(schemas)} schemas self-valid.")
    ok = True

    def validate(data, schema_rel: str, label: str) -> None:
        nonlocal ok
        try:
            make_validator(schema_rel, schemas, store).validate(data)
            print(f"[OK] {label}")
        except Exception as exc:
            ok = False
            print(f"[FAIL] {label}: {str(exc).splitlines()[0]}")

    # Single-file examples
    for example_rel, schema_rel, kind in [
        ("examples/backpack.sample.json",         "schemas/backpack.schema.json",         "json"),
        ("examples/backpack-item.sample.json",    "schemas/backpack-item.schema.json",    "json"),
        ("examples/backpack-item.frontmatter.md", "schemas/backpack-item.schema.json",    "fm"),
        ("examples/backpack-index.sample.json",   "schemas/index.schema.json",            "json"),
        ("examples/doctrine.sample.json",         "schemas/doctrine.schema.json",         "json"),
        ("examples/doctrine-entry.sample.json",   "schemas/doctrine-entry.schema.json",   "json"),
        ("examples/freshness-policy.sample.json", "schemas/freshness-policy.schema.json", "json"),
    ]:
        path = repo_root / example_rel
        try:
            data = json.load(open(path)) if kind == "json" else load_frontmatter(path)
        except Exception as exc:
            ok = False
            print(f"[FAIL] {example_rel}: {exc}")
            continue
        validate(data, schema_rel, example_rel)

    # JSONL examples
    for jsonl_rel, schema_rel in [
        ("examples/hoard-sample.jsonl", "schemas/hoard-item.schema.json"),
        ("examples/ingestion-trace/events/events.jsonl", "schemas/ingestion-event.schema.json"),
    ]:
        path = repo_root / jsonl_rel
        n = 0
        for i, line in enumerate(open(path), 1):
            line = line.strip()
            if not line:
                continue
            try:
                make_validator(schema_rel, schemas, store).validate(json.loads(line))
                n += 1
            except Exception as exc:
                ok = False
                print(f"[FAIL] {jsonl_rel}:{i}: {str(exc).splitlines()[0]}")
        print(f"[OK] {jsonl_rel} ({n} records valid)")

    # Trace files
    for hf in sorted(glob.glob(str(repo_root / "examples/ingestion-trace/hoard/*.json"))):
        rel = os.path.relpath(hf, repo_root)
        try:
            data = json.load(open(hf))
        except Exception as exc:
            ok = False
            print(f"[FAIL] {rel}: {exc}")
            continue
        validate(data, "schemas/hoard-item.schema.json", rel)

    for bf in sorted(glob.glob(str(repo_root / "examples/ingestion-trace/backpack/**/*.md"), recursive=True)):
        rel = os.path.relpath(bf, repo_root)
        try:
            data = load_frontmatter(Path(bf))
        except Exception as exc:
            ok = False
            print(f"[FAIL] {rel}: {exc}")
            continue
        validate(data, "schemas/backpack-item.schema.json", rel)

    # Structural lint (delegates to tools/lint.py).
    print()
    try:
        import lint  # type: ignore
    except ImportError:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import lint  # type: ignore
    lint_ok = lint.run(repo_root)
    if not lint_ok:
        ok = False

    print()
    print("ALL PASSED" if ok else "FAILURES PRESENT")
    return ok


def main(argv: list[str]) -> int:
    repo_root = Path(argv[1]) if len(argv) > 1 else Path(__file__).resolve().parent.parent
    if not (repo_root / "schemas").is_dir():
        print(f"not a repo root (no schemas/): {repo_root}", file=sys.stderr)
        return 1
    return 0 if run(repo_root) else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
