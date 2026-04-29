#!/usr/bin/env python3
"""
session_primer.py — render the session-primer surface from an operator root.

Reads the file-system-as-database layout (backpack/, doctrine/, policy/) and
produces a markdown brief that the assistant uses to bootstrap a session.
This is a pure projection: no writes, no LLM calls.

Per [ADR 0003](../docs/decisions/0003-renderers-over-one-truth-layer.md), the
session primer must:

  1. Read pinned Doctrine first (identity, defaults, key workflows, key policies).
  2. Read current Backpack second (active carry-state, sorted by priority).
  3. Surface a "verify before acting" section for items in the ``recent``
     freshness band or aged past the freshness policy's verify threshold.
  4. Honor ``consent.applies_to_renderers`` on policy entries by quietly
     omitting any item whose scope intersects with a ``forbidden`` posture.

Usage:
    python renderers/session_primer.py <operator-root>
    python renderers/session_primer.py examples/operator-root-fixture

Outputs the rendered markdown to stdout. Returns exit code 0 on success.

Requires: pyyaml.
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

# Allow `python renderers/session_primer.py ...` from the repo root.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _common import (  # noqa: E402
    age_days,
    applies_here,
    by_priority,
    consent_filter,
    needs_verify,
    parse_iso,
    read_backpack,
    read_doctrine,
    read_freshness_policy,
)


RENDERER_ID = "session-primer"


def render(operator_root: Path, now: datetime | None = None) -> str:
    now = now or datetime.now(timezone.utc)
    doctrine = read_doctrine(operator_root)
    backpack = read_backpack(operator_root)
    policy = read_freshness_policy(operator_root)

    backpack, omitted_for_consent, gate_messages = consent_filter(backpack, doctrine, RENDERER_ID)

    # Doctrine groupings — pinned only, by kind, then priority.
    by_kind: dict[str, list[dict]] = {}
    for entry in doctrine:
        if not applies_here(entry, RENDERER_ID):
            continue
        if not entry.get("pinned", False):
            continue
        by_kind.setdefault(entry["kind"], []).append(entry)
    for kind in by_kind:
        by_kind[kind].sort(key=by_priority)

    identity = by_kind.get("identity") or []
    defaults = by_kind.get("default") or []
    workflows = by_kind.get("workflow") or []
    policies = [
        e for e in (by_kind.get("policy") or [])
        # Skip consent-only policies (the rule applies; the wording would be noise).
        if not (e.get("consent") and not e.get("body"))
    ]

    # Backpack groupings.
    pinned_bp = [b for b in backpack if b.get("freshness_class") == "pinned" and applies_here(b, RENDERER_ID)]
    current_bp = [b for b in backpack if b.get("freshness_class") == "current" and applies_here(b, RENDERER_ID)]
    recent_bp = [b for b in backpack if b.get("freshness_class") == "recent" and applies_here(b, RENDERER_ID)]

    pinned_bp.sort(key=by_priority)
    current_bp.sort(key=by_priority)
    recent_bp.sort(key=by_priority)

    verify_after_days = (policy or {}).get("rules", {}).get("verify_after_days", 7)
    needs_verify_items = [
        b for b in (current_bp + recent_bp)
        if needs_verify(b, now, verify_after_days)
    ]

    today = now.strftime("%Y-%m-%d %H:%M %Z").strip()
    lines: list[str] = []
    lines.append(f"# Session primer — {today}")
    lines.append("")
    lines.append("> Generated from Backpack + Doctrine. Do not edit; edit the source files instead.")
    lines.append(f"> Renderer: `{RENDERER_ID}`. Items: {len(backpack)} backpack, {len(doctrine)} doctrine.")
    lines.append("")

    if identity:
        lines.append("## Identity (Doctrine: pinned)")
        lines.append("")
        for e in identity:
            lines.append(e["body"].strip())
            lines.append("")

    if defaults or workflows or policies:
        lines.append("## Defaults, workflows, and policies (Doctrine: pinned)")
        lines.append("")
        for e in defaults + workflows + policies:
            lines.append(f"- **{e['title']}** — {e['body'].strip().splitlines()[0]}")
        lines.append("")

    if pinned_bp:
        lines.append("## Reference shelf (Backpack: pinned)")
        lines.append("")
        for b in pinned_bp:
            lines.append(f"- **{b['id']}** — {b['value'].strip().splitlines()[0]}")
        lines.append("")

    if current_bp:
        lines.append("## What's near right now (Backpack: current)")
        lines.append("")
        for b in current_bp:
            first_line = b["value"].strip().splitlines()[0]
            lines.append(f"- **{b['id']}** ({b.get('dated', '?')}). {first_line}")
        lines.append("")

    if needs_verify_items:
        lines.append("## Verify before acting")
        lines.append("")
        for b in needs_verify_items:
            age = age_days(b, now)
            age_note = f"~{age:.0f}d old" if age is not None else "no created_at"
            lines.append(f"- `{b['id']}` ({age_note}). Re-confirm before acting.")
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
        f"`renderers/session_primer.py`. Pure projection over Backpack + Doctrine.*"
    )
    return "\n".join(lines) + "\n"


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    p.add_argument("operator_root", help="Path to the operator root directory")
    p.add_argument(
        "--now",
        help="ISO-8601 timestamp to use as 'now' (for deterministic rendering in tests)",
    )
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
