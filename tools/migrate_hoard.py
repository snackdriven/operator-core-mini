#!/usr/bin/env python3
"""
migrate_hoard.py — populate ``<operator-root>/hoard/`` from a scratch-pad tree.

Hoard sources, in order:

  1. ``dailies/YYYY-MM-DD/<file>`` — every file under a dated folder becomes a
     hoard entry with ``aged_out_at`` set to ``YYYY-MM-DDT23:59:59Z``.
  2. Loose ``*.html`` / ``*.md`` / ``*.png`` at the scratch-pad root — each
     becomes a hoard entry. ``dated`` is mined from the filename (or ``--now``
     if no date is encoded).
  3. **NOT** the ``_config:ttl`` diversion — that is handled by ``migrate.py``
     because it operates on backpack items, not filesystem artifacts.

Hoard files are markdown with YAML frontmatter (per follow-up #3, 2026-04-29:
hoard files share ``schemas/backpack-item.schema.json`` with the optional
``aged_out_at`` field). We do NOT inline large HTML — the ``value`` field
carries a short pointer to the source-of-truth path so the operator can open
the original file.

Usage::

    python tools/migrate_hoard.py path/to/scratch-pad path/to/operator-root
    python tools/migrate_hoard.py path/to/scratch-pad path/to/operator-root \\
        --now 2026-04-29T20:00:00Z
"""
from __future__ import annotations

import argparse
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

# Allow `python tools/migrate_hoard.py …` to import sibling modules.
_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from _migrate_common import (  # noqa: E402
    RE_ISO_DATE,
    parse_iso,
    slug_from_path_fragment,
    to_iso_z,
    write_frontmatter_md,
)


# ---------------------------------------------------------------------------
# Hoard entry shape
# ---------------------------------------------------------------------------

def hoard_path_for(out_root: Path, dated: str, item_id: str) -> Path:
    """Compose ``hoard/<YYYY>/<MM>/<DD>/<id>.md``."""
    y, mo, d = dated.split("-")
    return out_root / "hoard" / y / mo / d / f"{item_id}.md"


def hoard_entry_for_file(
    file_path: Path,
    *,
    dated: str,
    aged_out_at: str,
    source_ref: str,
    area: str = "work",
) -> dict:
    """Build a backpack-item-shaped frontmatter dict pointing at a source file.

    Hoard files share schemas/backpack-item.schema.json — the optional
    ``aged_out_at`` field flips the entry into the aged-out window for
    renderers. We do NOT inline large HTML; the ``value`` field carries a
    short pointer to the source-of-truth path.
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

    # Include full relative path + extension so sibling files with the same
    # stem (e.g. .html vs .md) and same-name files under different subdirs
    # (transcripts/foo.md vs videos/foo.md, every .gitkeep, etc.) don't
    # collide on id.
    item_id = slug_from_path_fragment(f"{dated}-{source_ref}")
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


# ---------------------------------------------------------------------------
# Source walkers
# ---------------------------------------------------------------------------

_DAILIES_DIR_RE = re.compile(r"^(20\d{2})-(\d{2})-(\d{2})$")

_LOOSE_SUFFIXES = {".html", ".md", ".png", ".jpg", ".jpeg"}
_LOOSE_SKIP_NAMES = {
    "backpack.json",
    "README.md",
    "CLAUDE.md",
    "AGENTS.md",
    "package.json",
    "qa-onboarding-guide.md",
    "platform-dev-staging-access.md",
}
_HOARD_FILE_SKIP_SUFFIXES = {".pyc", ".ds_store"}


def migrate_dailies(scratch_root: Path, out_root: Path) -> tuple[int, list[str]]:
    """Walk ``dailies/YYYY-MM-DD/`` and write one hoard entry per file."""
    written = 0
    skipped: list[str] = []
    dailies = scratch_root / "dailies"
    if not dailies.is_dir():
        return 0, ["dailies/ not found"]

    for day_dir in sorted(dailies.iterdir()):
        if not day_dir.is_dir():
            continue
        if not _DAILIES_DIR_RE.match(day_dir.name):
            continue
        dated = day_dir.name
        aged_out_at = f"{dated}T23:59:59Z"
        for f in sorted(day_dir.rglob("*")):
            if not f.is_file():
                continue
            if f.suffix.lower() in _HOARD_FILE_SKIP_SUFFIXES:
                continue
            rel = f.relative_to(scratch_root).as_posix()
            entry = hoard_entry_for_file(
                f, dated=dated, aged_out_at=aged_out_at, source_ref=rel,
            )
            out_path = hoard_path_for(out_root, dated, entry["id"])
            try:
                write_frontmatter_md(out_path, entry)
                written += 1
            except FileExistsError as exc:
                skipped.append(str(exc))
    return written, skipped


def migrate_loose_artifacts(
    scratch_root: Path, out_root: Path, *, now: datetime
) -> tuple[int, list[str]]:
    """Hoard loose ``*.html`` / ``*.md`` / image files at the scratch-pad root."""
    written = 0
    skipped: list[str] = []
    today_iso = now.date().isoformat()
    today_aged = to_iso_z(now)

    for f in sorted(scratch_root.iterdir()):
        if not f.is_file():
            continue
        if f.suffix.lower() not in _LOOSE_SUFFIXES:
            continue
        if f.name in _LOOSE_SKIP_NAMES:
            continue
        m = RE_ISO_DATE.search(f.stem)
        if m:
            dated = f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
            aged_out_at = f"{dated}T23:59:59Z"
        else:
            dated = today_iso
            aged_out_at = today_aged
        rel = f.relative_to(scratch_root).as_posix()
        entry = hoard_entry_for_file(
            f, dated=dated, aged_out_at=aged_out_at, source_ref=rel,
        )
        out_path = hoard_path_for(out_root, dated, entry["id"])
        try:
            write_frontmatter_md(out_path, entry)
            written += 1
        except FileExistsError as exc:
            skipped.append(str(exc))
    return written, skipped


def migrate_hoard(
    scratch_root: Path, out_root: Path, *, now: datetime | None = None,
) -> dict:
    """Run both hoard sources end-to-end. Returns counts + skipped list."""
    if now is None:
        now = datetime.now(timezone.utc)
    d_w, d_s = migrate_dailies(scratch_root, out_root)
    l_w, l_s = migrate_loose_artifacts(scratch_root, out_root, now=now)
    return {
        "dailies_written": d_w,
        "loose_written": l_w,
        "skipped": d_s + l_s,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="migrate_hoard.py",
        description="Populate <operator-root>/hoard/ from a scratch-pad tree.",
    )
    parser.add_argument("scratch_root", help="Path to scratch-pad root")
    parser.add_argument("out_root", help="Output operator-root directory")
    parser.add_argument(
        "--now",
        dest="now",
        metavar="ISO",
        help="Wall-clock 'now' for undated loose artifacts (ISO-8601). "
             "Defaults to real UTC now.",
    )
    args = parser.parse_args(argv[1:])

    scratch_root = Path(args.scratch_root)
    out_root = Path(args.out_root)
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

    result = migrate_hoard(scratch_root, out_root, now=now)
    print(
        f"hoard additions: {result['dailies_written']} from dailies/, "
        f"{result['loose_written']} from loose artifacts."
    )
    if result["skipped"]:
        print(f"skipped {len(result['skipped'])}:", file=sys.stderr)
        for r in result["skipped"]:
            print(f"  {r}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
