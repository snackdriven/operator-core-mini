#!/usr/bin/env python3
"""
daily_brief.py — render the morning resumption surface.

The daily brief is the renderer the operator opens first thing in the
morning. It assumes session context already exists (the session primer
covers identity / posture / pinned defaults) and focuses on **what to
move on today** — current backpack items, recent items that need
verification, what aged out overnight, and what was replaced overnight.

Per ADR 0003 this is a pure projection. Per ADR 0004 the consent gate
runs before any rendering work; items scoped to a forbidden posture
never appear, named or otherwise. The renderer is a thin layout over
the shared FactBundle (see ``_common.py``); fact selection lives in
the bundle so this surface and others can't disagree about today.

Sections rendered (when data is present):

  * Today — life-state-derived shape of the day, only if not consent-gated.
  * Near today — current backpack items sorted by priority.
  * Verify before acting — recent items + items aged past the policy
    threshold.
  * Aged out overnight — items demoted to Hoard since the last render
    (per follow-up #3, 2026-04-29: this section is now Hoard-sourced;
    ``backpack/_replaced/`` is surfaced separately as "Replaced
    overnight").
  * Replaced overnight — items in ``backpack/_replaced/`` that were
    superseded by a newer entry in the same id family.
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
    apply_budget,
    budget_for,
    build_fact_bundle,
    parse_iso,
)


RENDERER_ID = "daily-brief"


def first_line(s: str | None) -> str:
    if not s:
        return ""
    return s.strip().splitlines()[0] if s.strip() else ""


def render(operator_root: Path, now: datetime | None = None) -> str:
    now = now or datetime.now(timezone.utc)
    bundle = build_fact_bundle(operator_root, now, RENDERER_ID)

    today = now.strftime("%A, %Y-%m-%d")
    lines: list[str] = []
    lines.append(f"# Daily Brief — {today}")
    lines.append("")
    lines.append("> Generated from Backpack + Doctrine. Edit sources, not this file.")
    lines.append(
        f"> Renderer: `{RENDERER_ID}`. Items: {bundle.backpack_total} backpack, "
        f"{bundle.aged_out_total} aged out, {bundle.replaced_total} replaced."
    )
    lines.append("")

    if bundle.today_lifestate:
        lines.append("## Today")
        lines.append("")
        lines.append(first_line(bundle.today_lifestate.get("value")))
        lines.append("")

    if bundle.current_bp:
        lines.append("## Near today")
        lines.append("")
        kept, dropped = apply_budget(
            bundle.current_bp,
            budget_for(RENDERER_ID, "current", bundle.freshness_policy),
        )
        for b in kept:
            lines.append(f"- **{b['id']}** — {first_line(b.get('value'))}")
        if dropped:
            lines.append(f"- _… +{dropped} more current items not shown (budgeted)._")
        lines.append("")

    if bundle.verify_items:
        lines.append("## Verify before acting")
        lines.append("")
        kept, dropped = apply_budget(
            bundle.verify_items,
            budget_for(RENDERER_ID, "verify", bundle.freshness_policy),
        )
        for b in kept:
            age = age_days(b, now)
            age_note = f"~{age:.0f}d old" if age is not None else "no created_at"
            lines.append(f"- **{b['id']}** ({age_note}). {first_line(b.get('value'))}")
        if dropped:
            lines.append(f"- _… +{dropped} more verify items not shown (budgeted)._")
        lines.append("")

    # Follow-up #3 — real aged-out comes from Hoard, not _replaced.
    if bundle.aged_out:
        lines.append("## Aged out overnight")
        lines.append("")
        kept, dropped = apply_budget(
            bundle.aged_out,
            budget_for(RENDERER_ID, "aged_out", bundle.freshness_policy),
        )
        for b in kept:
            ts = (b.get("aged_out_at") or "").split("T")[0] or "?"
            lines.append(f"- **{b['id']}** (aged out {ts}). {first_line(b.get('value'))}")
        if dropped:
            lines.append(f"- _… +{dropped} more aged-out items not shown (budgeted)._")
        lines.append("")

    if bundle.replaced:
        lines.append("## Replaced overnight")
        lines.append("")
        for b in bundle.replaced:
            replaces_target = ""
            if b.get("replaces"):
                replaces_target = f" → replaced `{b['replaces']}`"
            lines.append(f"- **{b['id']}**{replaces_target}. Demoted from active carry-state.")
        lines.append("")

    if bundle.this_week:
        lines.append("## This week (recent band)")
        lines.append("")
        kept, dropped = apply_budget(
            bundle.this_week,
            budget_for(RENDERER_ID, "recent", bundle.freshness_policy),
        )
        for b in kept:
            lines.append(f"- **{b['id']}** — {first_line(b.get('value'))}")
        if dropped:
            lines.append(f"- _… +{dropped} more recent items not shown (budgeted)._")
        lines.append("")

    if bundle.pinned_bp:
        lines.append("## Reference shelf (Backpack: pinned)")
        lines.append("")
        for b in bundle.pinned_bp:
            lines.append(f"- **{b['id']}** — {first_line(b.get('value'))}")
        lines.append("")

    if bundle.gate_messages:
        lines.append("## Consent gate")
        lines.append("")
        for msg in bundle.gate_messages:
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
