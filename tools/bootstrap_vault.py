#!/usr/bin/env python3
"""
bootstrap_vault.py — initialize a fresh directory as an operator-root.

Used to bring a new ``operator-vault`` repo up to a runnable state. After
this script finishes the target tree has:

  * backpack/{current,recent,pinned,evergreen,_replaced}/  (empty)
  * doctrine/{identity,default,voice,routing,policy,workflows}/  (9 seeds
      written by tools/bootstrap_doctrine.py — hand-edit later)
  * hoard/  (empty, daemon will populate)
  * policy/freshness.json  (canonical bands + TTL presets + budgets)
  * .github/workflows/{expire.yml,today.yml}  (the GitHub Action template)
  * .gitignore + README.md

Usage:

    python tools/bootstrap_vault.py /path/to/empty-vault
    python tools/bootstrap_vault.py /path/to/empty-vault \\
        --name "Kayla" --summary "QA at Tebra/NHHA. Bentonville, AR."
    python tools/bootstrap_vault.py /path/to/empty-vault --no-actions

Refuses to clobber an existing tree unless ``--force`` is passed. The
target dir must exist and be empty (or pass ``--force``).
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

THIS = Path(__file__).resolve().parent
REPO = THIS.parent
TEMPLATE_DIR = REPO / "deploy" / "operator-vault-template"

# Layers that should exist as empty directories on a fresh vault.
LAYER_DIRS = [
    "backpack/current",
    "backpack/recent",
    "backpack/pinned",
    "backpack/evergreen",
    "backpack/_replaced",
    "doctrine",
    "hoard",
    "policy",
]

# Schema-clean canonical freshness policy. Mirrors the bands described in
# schemas/freshness-policy.schema.json + the TTL presets used by
# bootstrap_doctrine.py and the Carry write-client.
FRESHNESS_POLICY = {
    "version": "1.0.0",
    "bands": [
        {"name": "current", "max_age_days": 1, "treatment": "trust", "renderer_priority": 90},
        {"name": "recent", "max_age_days": 7, "treatment": "mostly-reliable-verify-specifics", "renderer_priority": 70},
        {"name": "contextual", "max_age_days": 30, "treatment": "good-for-patterns-verify-details", "renderer_priority": 50},
        {"name": "historical", "max_age_days": 365, "treatment": "culture-pattern-only", "renderer_priority": 20},
        {"name": "evergreen", "max_age_days": 36500, "treatment": "refresh-periodically", "renderer_priority": 60},
    ],
    "rules": {
        "verify_after_days": 7,
        "require_dated_entries": True,
        "update_in_place": True,
        "patterns_age_slower_than_tactics": True,
    },
    "ttl_presets": {
        "snapshot": 604800,
        "tactical": 1209600,
        "fix-thread": 2592000,
        "quarter": 7776000,
    },
    "pinned_keys": [],
}


def _ensure_dirs(root: Path) -> list[Path]:
    created: list[Path] = []
    for rel in LAYER_DIRS:
        d = root / rel
        if not d.exists():
            d.mkdir(parents=True, exist_ok=True)
            # Drop a .gitkeep so empty layer dirs survive git
            (d / ".gitkeep").write_text("", encoding="utf-8")
            created.append(d)
    return created


def _write_freshness(root: Path, *, force: bool) -> Path | None:
    p = root / "policy" / "freshness.json"
    if p.exists() and not force:
        return None
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(FRESHNESS_POLICY, indent=2) + "\n", encoding="utf-8")
    return p


def _copy_template(root: Path, *, with_actions: bool, force: bool) -> list[Path]:
    """Copy deploy/operator-vault-template/* into the vault root.

    Skips files that already exist unless ``force`` is passed. When
    ``with_actions`` is False, the .github/ tree is omitted.
    """
    if not TEMPLATE_DIR.is_dir():
        raise SystemExit(f"template missing: {TEMPLATE_DIR}")

    written: list[Path] = []
    for src in TEMPLATE_DIR.rglob("*"):
        if src.is_dir():
            continue
        rel = src.relative_to(TEMPLATE_DIR)
        if not with_actions and rel.parts and rel.parts[0] == ".github":
            continue
        dst = root / rel
        if dst.exists() and not force:
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        written.append(dst)
    return written


def _seed_doctrine(root: Path, *, name: str, summary: str, force: bool) -> int:
    """Delegate to tools/bootstrap_doctrine.py:main() so we don't fork the
    seed list. Returns the exit code (0 on success)."""
    sys.path.insert(0, str(THIS))
    import bootstrap_doctrine as bd  # type: ignore  # noqa: E402

    argv = [str(root), "--name", name, "--summary", summary]
    if force:
        argv.append("--force")
    return bd.main(argv)


def bootstrap(
    root: Path,
    *,
    name: str = "Operator",
    summary: str = "TODO: short bio sentence.",
    with_actions: bool = True,
    force: bool = False,
) -> dict:
    """Programmatic entry point. Returns a dict summarizing what landed.

    The CLI :func:`main` wraps this; tests call this directly so they don't
    have to subprocess.
    """
    if not root.exists():
        root.mkdir(parents=True, exist_ok=True)

    # Refuse to write into a non-empty tree unless --force is set.
    # Hidden files (e.g. ``.git/``) don't count for emptiness — running this
    # immediately after ``git clone`` of a fresh empty repo should work.
    visible = [p for p in root.iterdir() if not p.name.startswith(".")]
    if visible and not force:
        raise SystemExit(
            f"{root} already has visible files; pass --force to overwrite "
            f"(found: {', '.join(p.name for p in visible[:5])})"
        )

    layer_dirs = _ensure_dirs(root)
    fresh_path = _write_freshness(root, force=force)

    rc = _seed_doctrine(root, name=name, summary=summary, force=force)
    if rc != 0:
        raise SystemExit(f"bootstrap_doctrine failed (exit={rc})")

    template_files = _copy_template(root, with_actions=with_actions, force=force)

    return {
        "root": str(root),
        "layer_dirs_created": [str(p.relative_to(root)) for p in layer_dirs],
        "freshness_written": str(fresh_path.relative_to(root)) if fresh_path else None,
        "template_files": [str(p.relative_to(root)) for p in template_files],
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    p.add_argument("vault_root", type=Path, help="path to (or for) the new vault")
    p.add_argument("--name", default="Operator", help="identity stub display name")
    p.add_argument(
        "--summary",
        default="TODO: short bio sentence.",
        help="one-line identity summary",
    )
    p.add_argument(
        "--no-actions",
        action="store_true",
        help="skip copying .github/workflows/ (e.g. if you don't use GitHub)",
    )
    p.add_argument("--force", action="store_true", help="overwrite existing files")
    args = p.parse_args(argv)

    summary = bootstrap(
        args.vault_root,
        name=args.name,
        summary=args.summary,
        with_actions=not args.no_actions,
        force=args.force,
    )

    print(f"bootstrapped {summary['root']}", file=sys.stderr)
    print(f"  layer dirs: {len(summary['layer_dirs_created'])} created", file=sys.stderr)
    if summary["freshness_written"]:
        print(f"  policy:     {summary['freshness_written']}", file=sys.stderr)
    print(f"  templates:  {len(summary['template_files'])} files copied", file=sys.stderr)
    print("", file=sys.stderr)
    print("next:", file=sys.stderr)
    print("  cd " + summary["root"], file=sys.stderr)
    print("  git init && git add -A && git commit -m 'initial vault'", file=sys.stderr)
    print("  git remote add origin <your-vault-url> && git push -u origin main", file=sys.stderr)
    print("  # then enable Actions on the new repo and the daemon will fire nightly.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
