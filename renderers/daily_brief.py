#!/usr/bin/env python3
"""
daily_brief.py — render the morning resumption surface.

The daily brief is the renderer the operator opens first thing in the
morning. It assumes session context already exists (the session primer
covers identity / posture / pinned defaults) and focuses on **what to
move on today** — current backpack items, recent items that need
verification, and what aged out overnight.

Per ADR 0003 this is a pure projection. Per ADR 0004 the consent gate
runs before any rendering work; items scoped to a forbidden posture
never appear, named or otherwise.

Sections rendered (when data is present):

  * Today — life-state-derived shape of the day, only if not consent-gated.
  * Near today — current backpack items sorted by priority.
  * Verify before acting — recent items + items aged past the policy
    threshold.
  * What aged out — backpack items in ``_replaced/`` with a ``replaces``
    chain, treated as the overnight diff.
  * This week — current items in the ``recent`` band that don't need verify.
  * Consent gate — count-only summary of suppressed items.

Usage:
    python renderers/daily_brief.py <operator-root> [--now ISO-8601]

Outputs the rendered markdown to stdout.
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _common import (  # noqa: E402
    age_days,
    applies_here,
    by_priority,
    consent_filter,
    load_frontmatter,
    needs_verify,
    parse_iso,
    read_backpack,
    read_doctrine,
    read_freshness_policy,
)


RENDERER_ID = "daily-brief"


def read_replaced(operator_root: Path) -> list[dict]:
    """Read ``backpack/_replaced/*.md`` (the overnight diff substrate)."""
    out: list[dict] = []
    p = operator_root / "backpack" / "_replaced"
    if not p.is_dir():
        return out
    for f in sorted(p.rglob("*.md")):
        fm, body = load_frontmatter(f)
        if "value" not in fm and body:
            fm["value"] = body
        fm["_path"] = str(f.relative_to(operator_root))
        out.append(fm)
    return out


def first_line(s: str | None) -> str:
    if not s:
        return ""
    return s.strip().splitlines()[0] if s.strip() else ""


def render(operator_root: Path, now: datetime | None = None) -> str:
    now = now or datetime.now(timezone.utc)
    doctrine = read_doctrine(operator_root)
    backpack = read_backpack(operator_root)
    replaced = read_replaced(operator_root)
    policy = read_freshness_policy(operator_root)

    # Apply consent gate to everything we might surface. Run on the union
    # so per-policy counts cover both backpack and the overnight diff and
    # we render one banner per policy rather than two.
    combined = [("bp", b) for b in backpack] + [("rp", b) for b in replaced]
    kept_combined, omitted, gate_messages = consent_filter(
        [item for _, item in combined], doctrine, RENDERER_ID
    )
    kept_ids = {id(item) for item in kept_combined}
    backpack = [b for b in backpack if id(b) in kept_ids]
    replaced = [b for b in replaced if id(b) in kept_ids]

    here = lambda b: applies_here(b, RENDERER_ID)

    pinned_bp = sorted([b for b in backpack if b.get("freshness_class") == "pinned" and here(b)], key=by_priority)
    current_bp = sorted([b for b in backpack if b.get("freshness_class") == "current" and here(b)], key=by_priority)
    recent_bp = sorted([b for b in backpack if b.get("freshness_class") == "recent" and here(b)], key=by_priority)
    timeline_bp = sorted([b for b in backpack if b.get("memory_class") == "timeline" and here(b)], key=by_priority)

    verify_after_days = (policy or {}).get("rules", {}).get("verify_after_days", 7)
    verify_items = [b for b in (current_bp + recent_bp) if needs_verify(b, now, verify_after_days)]

    # "This week" — recent items that DON'T need verify (gentler band).
    this_week = [b for b in recent_bp if b not in verify_items]

    # "Today" comes from a backpack item with memory_class=timeline that
    # is dated today and tagged life-state. If consent-gated for this
    # renderer, it's already filtered out and this section is empty.
    today_items = [
        b for b in timeline_bp
        if str(b.get("dated") or "")[:10] == now.strftime("%Y-%m-%d")
        and "life-state" in (b.get("tags") or [])
    ]

    today = now.strftime("%A, %Y-%m-%d")
    lines: list[str] = []
    lines.append(f"# Daily Brief — {today}")
    lines.append("")
    lines.append("> Generated from Backpack + Doctrine. Edit sources, not this file.")
    lines.append(f"> Renderer: `{RENDERER_ID}`. Items: {len(backpack)} backpack, {len(replaced)} replaced overnight.")
    lines.append("")

    if today_items:
        lines.append("## Today")
        lines.append("")
        for b in today_items:
            lines.append(first_line(b.get("value")))
        lines.append("")

    if current_bp:
        lines.append("## Near today")
        lines.append("")
        for b in current_bp:
            lines.append(f"- **{b['id']}** — {first_line(b.get('value'))}")
        lines.append("")

    if verify_items:
        lines.append("## Verify before acting")
        lines.append("")
        for b in verify_items:
            age = age_days(b, now)
            age_note = f"~{age:.0f}d old" if age is not None else "no created_at"
            lines.append(f"- **{b['id']}** ({age_note}). {first_line(b.get('value'))}")
        lines.append("")

    if replaced:
        lines.append("## What aged out overnight")
        lines.append("")
        for b in replaced:
            replaces_target = ""
            # An item in _replaced was itself superseded; surface its prior id.
            if b.get("replaces"):
                replaces_target = f" → replaced `{b['replaces']}`"
            lines.append(f"- **{b['id']}**{replaces_target}. Demoted from active carry-state.")
        lines.append("")

    if this_week:
        lines.append("## This week (recent band)")
        lines.append("")
        for b in this_week:
            lines.append(f"- **{b['id']}** — {first_line(b.get('value'))}")
        lines.append("")

    if pinned_bp:
        lines.append("## Reference shelf (Backpack: pinned)")
        lines.append("")
        for b in pinned_bp:
            lines.append(f"- **{b['id']}** — {first_line(b.get('value'))}")
        lines.append("")

    if gate_messages:
        lines.append("## Consent gate")
        lines.append("")
        for msg in gate_messages:
            lines.append(msg)
        lines.append("")

    lines.append("---")
    lines.append(
        f"*Source: `{operator_root}`. Rendered {now.isoformat()} by "
        f"`renderers/daily_brief.py`. Pure projection over Backpack + Doctrine.*"
    )
    return "\n".join(lines) + "\n"


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    p.add_argument("operator_root", help="Path to the operator root directory")
    p.add_argument("--now", help="ISO-8601 timestamp (overrides 'now' for tests)")
    args = p.parse_args(argv[1:])

    operator_root = Path(args.operator_root).resolve()
    if not (operator_root / "doctrine").is_dir():
        print(f"not an operator root (no doctrine/): {operator_root}", file=sys.stderr)
        return 1

    now = parse_iso(args.now) if args.now else datetime.now(timezone.utc)
    sys.stdout.write(render(operator_root, now=now))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
