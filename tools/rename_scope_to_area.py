#!/usr/bin/env python3
"""
rename_scope_to_area.py — one-shot migration for follow-up #7 (2026-04-29).

Renames the ``scope:`` frontmatter key on Backpack and Hoard items to
``area:``. Per ADR follow-up #7, ``scope`` was an enum-classification field
that had nothing to do with consent; ``consent.scope`` is the free-string
field used by consent policies. Conflating the two led to a silently dead
clause in ``consent_filter``. The enum is now ``area`` everywhere.

Files touched:
  * ``examples/backpack*.json`` — JSON value rewrites.
  * ``examples/backpack-item.frontmatter.md`` — frontmatter key rewrite.
  * ``examples/operator-root-fixture/backpack/**/*.md`` — frontmatter.
  * ``examples/operator-root-fixture/hoard/**/*.md`` — frontmatter.
  * ``examples/ingestion-trace/hoard/*.json`` — JSON value rewrites.
  * ``examples/ingestion-trace/backpack/**/*.md`` — frontmatter.
  * ``examples/ingestion-trace/quarantine/*.json`` — JSON value rewrites
    that target the operator's own enum, NOT the rejected free-string
    consent.scope payloads.

Files NOT touched:
  * ``schemas/*.schema.json`` — already manually updated.
  * ``examples/doctrine.sample.json`` — Doctrine entries use
    ``consent.scope`` (free string) and ``voice.scope`` /
    ``routing.scope`` (different concept entirely). Keep those alone.

Idempotent. Runs from the repo root by default.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path


ENUM_VALUES = {"work", "life", "assistant", "identity", "meta"}


def migrate_frontmatter(path: Path) -> bool:
    """Rewrite ``scope: <enum>`` \u2192 ``area: <enum>`` inside a markdown
    file's YAML frontmatter. Return True if changed."""
    text = path.read_text(encoding="utf-8")
    m = re.match(r"(---\n)(.*?)(\n---\n?)(.*)", text, re.S)
    if not m:
        return False
    fm_text = m.group(2)
    new_fm = re.sub(
        r"^(\s*)scope:\s*(work|life|assistant|identity|meta)\s*$",
        r"\1area: \2",
        fm_text,
        flags=re.M,
    )
    if new_fm == fm_text:
        return False
    path.write_text(m.group(1) + new_fm + m.group(3) + m.group(4), encoding="utf-8")
    return True


def migrate_json(path: Path) -> bool:
    """In a JSON file, rewrite top-level or nested ``"scope": "<enum>"`` \u2192
    ``"area": "<enum>"``. Conservative: only renames when the value is one
    of the enum strings, so consent.scope and voice.scope (which use
    free strings or arrays) are left alone."""
    text = path.read_text(encoding="utf-8")
    # Match `"scope": "<enum>"` patterns specifically; this dodges the
    # consent free-strings ('health-records', 'work-channel-transcripts')
    # and voice arrays ('scope': ['narrator-brief']).
    enum_pat = "|".join(sorted(ENUM_VALUES))
    new = re.sub(
        rf'"scope":\s*"({enum_pat})"',
        r'"area": "\1"',
        text,
    )
    # Index sample uses scope as an enum value too.
    new = re.sub(
        rf'"by_scope":', r'"by_area":', new,
    )
    if new == text:
        return False
    # Sanity-check it's still valid JSON.
    json.loads(new)
    path.write_text(new, encoding="utf-8")
    return True


def main(argv: list[str]) -> int:
    repo_root = Path(argv[1]) if len(argv) > 1 else Path(__file__).resolve().parent.parent
    if not (repo_root / "schemas").is_dir():
        print(f"not a repo root: {repo_root}", file=sys.stderr)
        return 1

    changed = 0

    # Markdown frontmatter targets.
    md_targets: list[Path] = []
    md_targets.append(repo_root / "examples/backpack-item.frontmatter.md")
    md_targets.extend((repo_root / "examples/operator-root-fixture/backpack").rglob("*.md"))
    md_targets.extend((repo_root / "examples/operator-root-fixture/hoard").rglob("*.md"))
    md_targets.extend((repo_root / "examples/ingestion-trace/backpack").rglob("*.md"))

    for p in md_targets:
        if not p.is_file():
            continue
        if migrate_frontmatter(p):
            changed += 1
            print(f"[ok] {p.relative_to(repo_root)}")

    # JSON targets where the value really is the enum.
    json_targets: list[Path] = []
    json_targets.append(repo_root / "examples/backpack.sample.json")
    json_targets.append(repo_root / "examples/backpack-item.sample.json")
    json_targets.append(repo_root / "examples/backpack-index.sample.json")
    json_targets.extend((repo_root / "examples/ingestion-trace/hoard").glob("*.json"))
    json_targets.extend((repo_root / "examples/ingestion-trace/quarantine").glob("*.json"))

    # JSONL targets — hoard records use the enum directly. Treat each line
    # as its own JSON for validation; the regex is the same.
    jsonl_targets: list[Path] = []
    jsonl_targets.append(repo_root / "examples/hoard-sample.jsonl")

    enum_pat = "|".join(sorted(ENUM_VALUES))
    for p in jsonl_targets:
        if not p.is_file():
            continue
        text = p.read_text(encoding="utf-8")
        new = re.sub(rf'"scope":\s*"({enum_pat})"', r'"area": "\1"', text)
        if new != text:
            for ln in new.strip().split("\n"):
                json.loads(ln)  # sanity
            p.write_text(new, encoding="utf-8")
            changed += 1
            print(f"[ok] {p.relative_to(repo_root)}")

    for p in json_targets:
        if not p.is_file():
            continue
        if migrate_json(p):
            changed += 1
            print(f"[ok] {p.relative_to(repo_root)}")

    print(f"\n{changed} file(s) migrated.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
