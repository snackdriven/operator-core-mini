"""
verbs.py — substrate mutation verbs for the operator console.

Thin wrappers above ``tools/substrate.py``. Each verb is a small, well-scoped
operation against an operator-root laid out as backpack/ + doctrine/ + hoard/
+ policy/. Verbs are the *only* code path in the console that writes to disk;
the renderers stay read-only per ADR 0003.

Implemented verbs:

  * verify(id)             — refresh ``created_at`` so TTL math resets.
  * pin(id)                — set ``freshness_class: pinned``.
  * unpin(id)              — revert to ``current``; aging takes over again.
  * snooze(id, days)       — verify + extend TTL by N days. "kick the can".
  * update(id, summary=)   — edit mutable display fields in place.
  * demote(id)             — stamp ``aged_out_at`` and move to hoard/.

Each verb returns ``{ok, message, mutated_paths}`` so the caller can update
the tree without re-fetching the whole substrate.
"""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

# Pull substrate primitives without packaging the repo. The daemon
# (tools/expire.py) already lives next to substrate.py and imports normally.
_TOOLS = Path(__file__).resolve().parent.parent / "tools"
if str(_TOOLS) not in sys.path:
    sys.path.insert(0, str(_TOOLS))

from substrate import (  # noqa: E402  (sys.path mutation above)
    atomic_write,
    demote_to_hoard,
    find_by_id,
    join_frontmatter,
    now_iso,
    split_frontmatter,
)


# ---------------------------------------------------------------------------
# Backwards-compatible aliases. server.py used to reach into verbs._atomic_write
# and verbs._split_frontmatter directly; keep those names so that import
# doesn't break.
# ---------------------------------------------------------------------------

_atomic_write = atomic_write
_split_frontmatter = split_frontmatter
_join_frontmatter = join_frontmatter
_now_iso = now_iso
_find_by_id = find_by_id


# ---------------------------------------------------------------------------
# Verbs
# ---------------------------------------------------------------------------

def verify(operator_root: Path, item_id: str, now: datetime | None = None) -> dict:
    path = find_by_id(operator_root, item_id)
    if path is None:
        return {"ok": False, "message": f"no item with id={item_id!r}", "mutated_paths": []}
    fm, body = split_frontmatter(path.read_text(encoding="utf-8"))
    fm["created_at"] = now_iso(now)
    atomic_write(path, join_frontmatter(fm, body))
    return {
        "ok": True,
        "message": f"verified {item_id} (created_at reset)",
        "mutated_paths": [str(path.relative_to(operator_root))],
    }


def pin(operator_root: Path, item_id: str) -> dict:
    path = find_by_id(operator_root, item_id)
    if path is None:
        return {"ok": False, "message": f"no item with id={item_id!r}", "mutated_paths": []}
    fm, body = split_frontmatter(path.read_text(encoding="utf-8"))
    fm["freshness_class"] = "pinned"
    atomic_write(path, join_frontmatter(fm, body))
    return {
        "ok": True,
        "message": f"pinned {item_id}",
        "mutated_paths": [str(path.relative_to(operator_root))],
    }


def unpin(operator_root: Path, item_id: str) -> dict:
    path = find_by_id(operator_root, item_id)
    if path is None:
        return {"ok": False, "message": f"no item with id={item_id!r}", "mutated_paths": []}
    fm, body = split_frontmatter(path.read_text(encoding="utf-8"))
    if fm.get("freshness_class") != "pinned":
        return {
            "ok": False,
            "message": f"{item_id} is not pinned (freshness_class={fm.get('freshness_class')!r})",
            "mutated_paths": [],
        }
    fm["freshness_class"] = "current"
    atomic_write(path, join_frontmatter(fm, body))
    return {
        "ok": True,
        "message": f"unpinned {item_id} (now freshness_class=current)",
        "mutated_paths": [str(path.relative_to(operator_root))],
    }


def snooze(
    operator_root: Path,
    item_id: str,
    days: int = 7,
    now: datetime | None = None,
) -> dict:
    """Kick the can: reset ``created_at`` to now AND ensure ``ttl_seconds``
    is at least ``days * 86400``. Result: the item is fresh again for at
    least that many more days. Doesn't shorten an already-longer TTL.
    """
    try:
        days_i = int(days)
    except (TypeError, ValueError):
        return {"ok": False, "message": f"days must be int, got {days!r}", "mutated_paths": []}
    if days_i <= 0:
        return {"ok": False, "message": f"days must be positive, got {days_i}", "mutated_paths": []}

    path = find_by_id(operator_root, item_id)
    if path is None:
        return {"ok": False, "message": f"no item with id={item_id!r}", "mutated_paths": []}

    fm, body = split_frontmatter(path.read_text(encoding="utf-8"))
    fm["created_at"] = now_iso(now)
    new_ttl = days_i * 86400
    fm["ttl_seconds"] = max(int(fm.get("ttl_seconds") or 0), new_ttl)
    atomic_write(path, join_frontmatter(fm, body))
    return {
        "ok": True,
        "message": f"snoozed {item_id} for {days_i}d",
        "mutated_paths": [str(path.relative_to(operator_root))],
    }


def update(
    operator_root: Path,
    item_id: str,
    summary: str | None = None,
) -> dict:
    """Edit mutable display fields in place. v0 supports ``summary`` only;
    add fields here as the UIs need them. Schema-clean — never writes
    arbitrary keys."""
    path = find_by_id(operator_root, item_id)
    if path is None:
        return {"ok": False, "message": f"no item with id={item_id!r}", "mutated_paths": []}
    if summary is None:
        return {"ok": False, "message": "update: nothing to do (no fields supplied)", "mutated_paths": []}
    if not isinstance(summary, str) or not summary.strip():
        return {"ok": False, "message": "summary must be a non-empty string", "mutated_paths": []}

    fm, body = split_frontmatter(path.read_text(encoding="utf-8"))
    fm["summary"] = summary.strip()
    atomic_write(path, join_frontmatter(fm, body))
    return {
        "ok": True,
        "message": f"updated {item_id}",
        "mutated_paths": [str(path.relative_to(operator_root))],
    }


def demote(operator_root: Path, item_id: str, now: datetime | None = None) -> dict:
    """Move a backpack item to hoard/YYYY/MM/DD/, stamp aged_out_at."""
    path = find_by_id(operator_root, item_id)
    if path is None:
        return {"ok": False, "message": f"no item with id={item_id!r}", "mutated_paths": []}
    if "hoard" in path.parts:
        return {"ok": False, "message": f"{item_id} already in hoard", "mutated_paths": []}

    target = demote_to_hoard(operator_root, path, now=now)
    rel_old = str(path.relative_to(operator_root))
    rel_new = str(target.relative_to(operator_root))
    return {
        "ok": True,
        "message": f"demoted {item_id} → {rel_new}",
        "mutated_paths": [rel_old, rel_new],
    }
