"""
verbs.py — substrate mutation verbs for the operator console.

Each verb is a small, well-scoped operation against an operator-root laid out
as backpack/ + doctrine/ + hoard/ + policy/. Verbs are the *only* code path in
the console that writes to disk; the renderers stay read-only per ADR 0003.

Implemented verbs (v0):

  * verify(id)  — refresh ``created_at`` so TTL math resets.
  * pin(id)     — set ``freshness_class: pinned``.
  * unpin(id)   — revert to ``current``; aging takes over again.
  * demote(id)  — stamp ``aged_out_at`` and move the file from backpack/ into
                  hoard/YYYY/MM/DD/.

Each verb returns a dict {ok, message, mutated_paths} so the frontend can
update the tree without re-fetching the whole substrate.
"""
from __future__ import annotations

import os
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import yaml  # type: ignore


# ---------------------------------------------------------------------------
# Frontmatter I/O
# ---------------------------------------------------------------------------

class _StringDateLoader(yaml.SafeLoader):
    pass


_StringDateLoader.add_constructor(
    "tag:yaml.org,2002:timestamp",
    lambda loader, node: loader.construct_scalar(node),
)


def _split_frontmatter(text: str) -> tuple[dict, str]:
    if not text.startswith("---\n"):
        raise ValueError("file has no YAML frontmatter")
    end = text.find("\n---\n", 4)
    if end == -1:
        raise ValueError("unterminated frontmatter")
    fm = yaml.load(text[4:end], Loader=_StringDateLoader) or {}
    body = text[end + 5 :]
    return fm, body


def _join_frontmatter(fm: dict, body: str) -> str:
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


def _atomic_write(path: Path, text: str) -> None:
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


# ---------------------------------------------------------------------------
# ID lookup
# ---------------------------------------------------------------------------

def _find_by_id(operator_root: Path, item_id: str) -> Path | None:
    """Return the first backpack/* or hoard/** file whose frontmatter ``id``
    matches. Skips _replaced/."""
    for layer in ("backpack", "hoard"):
        root = operator_root / layer
        if not root.is_dir():
            continue
        for path in root.rglob("*.md"):
            if "_replaced" in path.parts:
                continue
            try:
                fm, _ = _split_frontmatter(path.read_text(encoding="utf-8"))
            except (ValueError, yaml.YAMLError):
                continue
            if fm.get("id") == item_id:
                return path
    return None


def _now_iso(now: datetime | None = None) -> str:
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    return now.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------------------
# Verbs
# ---------------------------------------------------------------------------

def verify(operator_root: Path, item_id: str, now: datetime | None = None) -> dict:
    path = _find_by_id(operator_root, item_id)
    if path is None:
        return {"ok": False, "message": f"no item with id={item_id!r}", "mutated_paths": []}
    fm, body = _split_frontmatter(path.read_text(encoding="utf-8"))
    fm["created_at"] = _now_iso(now)
    _atomic_write(path, _join_frontmatter(fm, body))
    return {
        "ok": True,
        "message": f"verified {item_id} (created_at reset)",
        "mutated_paths": [str(path.relative_to(operator_root))],
    }


def pin(operator_root: Path, item_id: str) -> dict:
    path = _find_by_id(operator_root, item_id)
    if path is None:
        return {"ok": False, "message": f"no item with id={item_id!r}", "mutated_paths": []}
    fm, body = _split_frontmatter(path.read_text(encoding="utf-8"))
    fm["freshness_class"] = "pinned"
    _atomic_write(path, _join_frontmatter(fm, body))
    return {
        "ok": True,
        "message": f"pinned {item_id}",
        "mutated_paths": [str(path.relative_to(operator_root))],
    }


def unpin(operator_root: Path, item_id: str) -> dict:
    path = _find_by_id(operator_root, item_id)
    if path is None:
        return {"ok": False, "message": f"no item with id={item_id!r}", "mutated_paths": []}
    fm, body = _split_frontmatter(path.read_text(encoding="utf-8"))
    if fm.get("freshness_class") != "pinned":
        return {
            "ok": False,
            "message": f"{item_id} is not pinned (freshness_class={fm.get('freshness_class')!r})",
            "mutated_paths": [],
        }
    fm["freshness_class"] = "current"
    _atomic_write(path, _join_frontmatter(fm, body))
    return {
        "ok": True,
        "message": f"unpinned {item_id} (now freshness_class=current)",
        "mutated_paths": [str(path.relative_to(operator_root))],
    }


def demote(operator_root: Path, item_id: str, now: datetime | None = None) -> dict:
    """Move a backpack item to hoard/YYYY/MM/DD/, stamp aged_out_at."""
    path = _find_by_id(operator_root, item_id)
    if path is None:
        return {"ok": False, "message": f"no item with id={item_id!r}", "mutated_paths": []}
    if "hoard" in path.parts:
        return {"ok": False, "message": f"{item_id} already in hoard", "mutated_paths": []}

    fm, body = _split_frontmatter(path.read_text(encoding="utf-8"))
    iso = _now_iso(now)
    fm["aged_out_at"] = iso

    now_dt = datetime.now(timezone.utc) if now is None else now.astimezone(timezone.utc)
    target_dir = operator_root / "hoard" / now_dt.strftime("%Y") / now_dt.strftime("%m") / now_dt.strftime("%d")
    target = target_dir / path.name

    target.parent.mkdir(parents=True, exist_ok=True)
    _atomic_write(target, _join_frontmatter(fm, body))
    path.unlink()

    rel_old = str(path.relative_to(operator_root))
    rel_new = str(target.relative_to(operator_root))
    return {
        "ok": True,
        "message": f"demoted {item_id} → {rel_new}",
        "mutated_paths": [rel_old, rel_new],
    }
