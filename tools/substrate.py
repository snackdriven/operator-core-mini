"""
substrate.py — shared mutation primitives for backpack/hoard items.

Both ``console/verbs.py`` (interactive verbs over the HTTP API) and
``tools/expire.py`` (the nightly TTL daemon) need to:

  * read YAML frontmatter without losing the body,
  * write atomically (tempfile + os.replace),
  * stamp ISO-8601 timestamps,
  * find items by ``id`` across backpack/ and hoard/,
  * demote a backpack item to ``hoard/YYYY/MM/DD/`` with ``aged_out_at``.

That logic lives here so neither caller forks it. Verbs stay thin wrappers
above; the daemon iterates and calls the same primitives directly.
"""
from __future__ import annotations

import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import yaml  # type: ignore


# ---------------------------------------------------------------------------
# YAML loader matching the rest of the repo (renderers/_common.py +
# console/verbs.py): keep timestamp scalars as strings so re-serialization
# round-trips byte-for-byte against the schema's ``format: date-time`` fields.
# ---------------------------------------------------------------------------

class _StringDateLoader(yaml.SafeLoader):
    pass


_StringDateLoader.add_constructor(
    "tag:yaml.org,2002:timestamp",
    lambda loader, node: loader.construct_scalar(node),
)


def split_frontmatter(text: str) -> tuple[dict, str]:
    """Parse ``---\\n<yaml>\\n---\\n<body>``. Raises ValueError if missing or
    unterminated."""
    if not text.startswith("---\n"):
        raise ValueError("file has no YAML frontmatter")
    end = text.find("\n---\n", 4)
    if end == -1:
        raise ValueError("unterminated frontmatter")
    fm = yaml.load(text[4:end], Loader=_StringDateLoader) or {}
    body = text[end + 5 :]
    return fm, body


def join_frontmatter(fm: dict, body: str) -> str:
    """Inverse of :func:`split_frontmatter`. Preserves field order, leaves
    string scalars alone, and ensures the body ends in a newline."""
    dumped = yaml.safe_dump(
        fm,
        sort_keys=False,
        allow_unicode=True,
        default_flow_style=False,
        width=10_000,
    )
    if not body.endswith("\n"):
        body = body + "\n"
    return f"---\n{dumped}---\n{body}"


def atomic_write(path: Path, text: str) -> None:
    """Write atomically: tempfile in the same directory, fsync, os.replace.
    Avoids partially-written files if the process is killed mid-write."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=path.name + ".", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def now_iso(now: datetime | None = None) -> str:
    """ISO-8601 UTC ``YYYY-MM-DDTHH:MM:SSZ`` (no microseconds), matching the
    format used everywhere else in the substrate."""
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    return now.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------------------
# Substrate walks
# ---------------------------------------------------------------------------

def find_by_id(operator_root: Path, item_id: str) -> Path | None:
    """First backpack/* or hoard/** file whose frontmatter ``id`` matches.
    Skips ``backpack/_replaced/``."""
    for layer in ("backpack", "hoard"):
        root = operator_root / layer
        if not root.is_dir():
            continue
        for path in root.rglob("*.md"):
            if "_replaced" in path.parts:
                continue
            try:
                fm, _ = split_frontmatter(path.read_text(encoding="utf-8"))
            except (ValueError, yaml.YAMLError):
                continue
            if fm.get("id") == item_id:
                return path
    return None


def iter_backpack(operator_root: Path):
    """Yield (path, fm, body) for every backpack item (excluding _replaced/).
    Skips files without parseable frontmatter."""
    root = operator_root / "backpack"
    if not root.is_dir():
        return
    for path in sorted(root.rglob("*.md")):
        if "_replaced" in path.parts:
            continue
        try:
            fm, body = split_frontmatter(path.read_text(encoding="utf-8"))
        except (ValueError, yaml.YAMLError):
            continue
        yield path, fm, body


# ---------------------------------------------------------------------------
# Demote primitive — the file move that "expire" and "complete" both need.
# ---------------------------------------------------------------------------

def demote_to_hoard(
    operator_root: Path,
    path: Path,
    *,
    now: datetime | None = None,
) -> Path:
    """Move ``path`` from backpack/ to ``hoard/YYYY/MM/DD/<basename>`` with
    ``aged_out_at`` stamped on the frontmatter. Returns the new path.

    Raises ValueError if ``path`` is not under ``operator_root/backpack/``.
    Hoard is write-once per ADR 0002 and the manifesto, so we only ever add
    to it.
    """
    if "backpack" not in path.parts:
        raise ValueError(f"refusing to demote non-backpack path: {path}")

    fm, body = split_frontmatter(path.read_text(encoding="utf-8"))
    iso = now_iso(now)
    fm["aged_out_at"] = iso

    now_dt = datetime.now(timezone.utc) if now is None else now.astimezone(timezone.utc)
    target_dir = (
        operator_root / "hoard"
        / now_dt.strftime("%Y") / now_dt.strftime("%m") / now_dt.strftime("%d")
    )
    target = target_dir / path.name

    target.parent.mkdir(parents=True, exist_ok=True)
    atomic_write(target, join_frontmatter(fm, body))
    path.unlink()
    return target


# ---------------------------------------------------------------------------
# TTL eligibility — single source of truth for "is this item past its lease?"
# Used by both the daemon and any UI that wants to flag stale items.
# ---------------------------------------------------------------------------

def is_expired(fm: dict, now: datetime | None = None) -> bool:
    """An item is *expired* iff it has both ``created_at`` and ``ttl_seconds``
    and ``created_at + ttl_seconds < now``. Items without TTL never expire.
    Pinned items are *eligible* by this predicate but the daemon excludes
    them — that decision lives in the caller, not here.

    Note: ``ttl_seconds: 0`` is valid per the schema and means
    "lease is zero seconds" — i.e. expired the moment ``created_at`` is
    in the past. This differs from omitting ``ttl_seconds`` entirely,
    which means "no lease."
    """
    ttl = fm.get("ttl_seconds")
    created_at = fm.get("created_at")
    if ttl is None or created_at is None:
        return False
    try:
        ttl_int = int(ttl)
    except (ValueError, TypeError):
        return False
    if ttl_int < 0:
        return False
    try:
        ca = datetime.fromisoformat(str(created_at).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return False
    if ca.tzinfo is None:
        ca = ca.replace(tzinfo=timezone.utc)
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    return (now - ca).total_seconds() > ttl_int
