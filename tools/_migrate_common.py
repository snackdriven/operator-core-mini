#!/usr/bin/env python3
"""
_migrate_common.py — shared helpers for migrate.py and migrate_hoard.py.

This module is deliberately small and side-effect-free. Everything here is
reusable across all migration surfaces:
  * id slugification
  * ISO-8601 parse / format
  * YAML frontmatter dumping (literal-block style, stable key order)
  * date / summary mining heuristics

Nothing here opens files or walks directories. Use migrate.py for backpack
logic and migrate_hoard.py for the hoard adapters.
"""
from __future__ import annotations

import re
import sys
from datetime import datetime, timezone
from pathlib import Path

try:
    import yaml  # PyYAML
except ImportError:  # pragma: no cover
    sys.exit("PyYAML required: pip install pyyaml")


# ---------------------------------------------------------------------------
# Id / slug
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


def slug_from_path_fragment(rel: str) -> str:
    """Like slugify but tolerant of path separators and repeated dashes."""
    s = re.sub(r"[^a-z0-9]+", "-", rel.lower()).strip("-")
    return re.sub(r"-+", "-", s) or "item"


# ---------------------------------------------------------------------------
# Time
# ---------------------------------------------------------------------------

def to_iso_z(dt: datetime) -> str:
    """Format a datetime as ISO-8601 with trailing Z."""
    return dt.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def parse_iso(s: str) -> datetime | None:
    """Parse an ISO-8601 string into a tz-aware datetime, or None."""
    if not isinstance(s, str) or not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Date / summary mining
# ---------------------------------------------------------------------------

RE_ISO_DATE = re.compile(r"\b(20\d{2})-(\d{2})-(\d{2})\b")
RE_AS_OF = re.compile(r"as of\s+(20\d{2})-(\d{2})-(\d{2})", re.IGNORECASE)


def extract_dated(key: str, value: str) -> str | None:
    """
    Mine a YYYY-MM-DD date from the legacy key + value text.

    Priority:
      1. ``as of YYYY-MM-DD`` anywhere in value
      2. Last YYYY-MM-DD in the id/key (e.g. ``dsu-2026-04-07``)
      3. First YYYY-MM-DD in the value's first non-empty line
      4. Last YYYY-MM-DD anywhere in value
      5. None — caller decides fallback.
    """
    if m := RE_AS_OF.search(value):
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"

    id_dates = RE_ISO_DATE.findall(key)
    if id_dates:
        y, mo, d = id_dates[-1]
        return f"{y}-{mo}-{d}"

    first_line = next((ln for ln in value.splitlines() if ln.strip()), "")
    if m := RE_ISO_DATE.search(first_line):
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"

    body_dates = RE_ISO_DATE.findall(value)
    if body_dates:
        y, mo, d = body_dates[-1]
        return f"{y}-{mo}-{d}"

    return None


def derive_summary(value: str) -> str | None:
    """Compress the first non-empty line into a short renderer-friendly summary."""
    first = next((ln.strip() for ln in value.splitlines() if ln.strip()), "")
    if not first:
        return None

    cuts = []
    for sep in (". ", ": ", " — ", " - "):
        idx = first.find(sep)
        if 10 <= idx <= 120:
            cuts.append(idx)
    if cuts:
        first = first[: min(cuts)].rstrip(" -—:.")

    if len(first) > 140:
        first = first[:137].rstrip() + "…"
    if len(first) < 8:
        return None
    return first


# ---------------------------------------------------------------------------
# YAML frontmatter writer (shared dumper + key order)
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
    "aged_out_at",
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
    for k, v in item.items():
        if k not in out:
            out[k] = v
    return out


def write_frontmatter_md(out_path: Path, item: dict, body: str = "") -> None:
    """Write a markdown file with YAML frontmatter for one Backpack/Hoard item.

    Refuses to overwrite existing files; callers should handle FileExistsError.
    """
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
