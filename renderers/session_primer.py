#!/usr/bin/env python3
"""
session_primer.py — render the session-primer surface from an operator root.

Reads the file-system-as-database layout (backpack/, doctrine/, policy/) and
produces a markdown brief that the assistant uses to bootstrap a session.
This is a pure projection: no writes, no LLM calls.

The renderer is a thin layout over a `FactBundle` (see `_common.py`); the
bundle is the single point that walks the substrate and applies consent.
That's how this renderer and others stay in agreement about what the world
looks like at time T.

Per [ADR 0003](../docs/decisions/0003-renderers-over-one-truth-layer.md), the
session primer must:

  1. Read pinned Doctrine first (identity, defaults, key workflows, key policies).
  2. Read current Backpack second (active carry-state, sorted by priority).
  3. Surface a "verify before acting" section for items in the ``recent``
     freshness band or aged past the freshness policy's verify threshold.
  4. Honor ``consent.applies_to_renderers`` on policy entries by quietly
     omitting any item whose scope intersects with a ``forbidden`` posture.

Note on naming: the renderer outputs ``# Session Brief — <date>`` because
"session brief" is the operator-facing nomenclature; the *surface id* is
``session-primer`` everywhere in substrate (schemas, ingestion docs,
fixtures), and that is the durable identity that consent rules and
``applies_to`` arrays reference. Don't "fix" the title to match the surface
id; they are intentionally different.

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
    FactBundle,
    age_days,
    applies_here,
    apply_budget,
    budget_for,
    build_fact_bundle,
    by_priority,
    parse_iso,
    select_voice_rule,
)


RENDERER_ID = "session-primer"


def _doctrine_for_session_primer(bundle: FactBundle) -> dict[str, list[dict]]:
    """Group Doctrine entries that should appear in the session primer.

    Per follow-up #4 (2026-04-29): an entry surfaces if it is pinned OR if
    it explicitly opts in via ``renderer_hints.surfaces`` /
    ``applies_to``. Previously the renderer required *both*, which silently
    dropped non-pinned entries that the operator had explicitly opted in.
    """
    out: dict[str, list[dict]] = {}
    for entry in bundle.doctrine:
        opted_in = applies_here(entry, RENDERER_ID)
        pinned = bool(entry.get("pinned", False))
        # Skip entries that don't apply here AND aren't pinned globally.
        # Pinned entries with an empty surfaces list are global; entries
        # that explicitly omit this renderer via ``never_surface_in``
        # are dropped by ``applies_here``.
        if not pinned and not opted_in:
            continue
        if not opted_in:
            # ``opted_in`` is False either because the entry has a non-empty
            # surfaces list that excludes us, or never_surface_in includes
            # us. The latter is a hard deny; ``applies_here`` already
            # handled it. The former we want to respect even for pinned
            # entries — pinning means "always carry", not "always render
            # everywhere".
            hints = entry.get("renderer_hints") or {}
            surfaces = hints.get("surfaces") or entry.get("applies_to") or []
            deny = hints.get("never_surface_in") or []
            if RENDERER_ID in deny:
                continue
            if surfaces and RENDERER_ID not in surfaces:
                continue
        out.setdefault(entry["kind"], []).append(entry)
    for kind in out:
        out[kind].sort(key=by_priority)
    return out


def _routing_hints_lines(bundle: FactBundle) -> list[str]:
    """Build the Routing hints section body (per follow-up #6).

    The session primer is a *meta* surface: it tells the operator what the
    sister narrator surface will do this session. So we look up the
    narrator-brief voice rule and any routing rule that would fire by
    default — not the session-primer's own (none exists).
    """
    lines: list[str] = []

    # Narrator's active voice (look it up against narrator-brief, not us).
    narrator_voice = select_voice_rule(bundle.doctrine, "narrator-brief")
    if narrator_voice:
        v = narrator_voice.get("voice") or {}
        skin = v.get("skin", "?")
        register = v.get("register", "neutral")
        lines.append(f"- Narrator skin: `{skin}` ({register}).")
    else:
        lines.append("- Narrator skin: not selected (no voice-rule applies).")

    # Energy routing — we don't know the current life-state automatically,
    # so we report whether *any* routing rule is wired up rather than
    # claiming one fired. Renderers without an energy signal report "not
    # triggered" by default.
    routing_rules = [e for e in bundle.doctrine if e.get("kind") == "routing-rule"]
    if routing_rules:
        names = ", ".join(
            f"`{r.get('id', '?')}` (when=`{(r.get('routing') or {}).get('when', '?')}`)"
            for r in routing_rules
        )
        lines.append(f"- Energy routing: not triggered today. Configured: {names}.")
    else:
        lines.append("- Energy routing: not configured.")

    # Surfaces consenting to life-state.
    consenting: list[str] = []
    for entry in bundle.doctrine:
        if entry.get("kind") != "policy":
            continue
        consent = entry.get("consent")
        if not consent:
            continue
        if (consent.get("scope") or "").lower() != "life-state":
            continue
        if consent.get("posture") in ("opt-in", "allow"):
            consenting.extend(consent.get("applies_to_renderers") or [])
    consenting = sorted(set(consenting))
    if consenting:
        lines.append(f"- Surfaces consenting to life-state: {', '.join(consenting)}.")
    else:
        lines.append("- Surfaces consenting to life-state: none active.")

    return lines


def _open_threads(bundle: FactBundle) -> list[dict]:
    """Backpack items tagged ``open-thread`` (per follow-up #6).

    Tag-only by design; see PLAN-followups for the deferred decision on
    promoting this to a first-class field.
    """
    return [
        b for b in (bundle.current_bp + bundle.recent_bp)
        if "open-thread" in (b.get("tags") or [])
    ]


def render(operator_root: Path, now: datetime | None = None) -> str:
    now = now or datetime.now(timezone.utc)
    bundle = build_fact_bundle(operator_root, now, RENDERER_ID)

    by_kind = _doctrine_for_session_primer(bundle)
    identity = by_kind.get("identity") or []
    defaults = by_kind.get("default") or []
    workflows = by_kind.get("workflow") or []
    policies = [
        e for e in (by_kind.get("policy") or [])
        # Skip consent-only policies (the rule applies; the wording would be noise).
        if not (e.get("consent") and not e.get("body"))
    ]

    verify_after_days = (bundle.freshness_policy or {}).get("rules", {}).get("verify_after_days", 7)  # noqa: F841

    today = now.strftime("%Y-%m-%d %H:%M %Z").strip()
    lines: list[str] = []
    lines.append(f"# Session Brief — {today}")
    lines.append("")
    lines.append("> Generated from Backpack + Doctrine. Do not edit; edit the source files instead.")
    lines.append(
        f"> Renderer: `{RENDERER_ID}`. Items: {bundle.backpack_total} backpack, "
        f"{len(bundle.doctrine)} doctrine."
    )
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

    if bundle.pinned_bp:
        lines.append("## Reference shelf (Backpack: pinned)")
        lines.append("")
        for b in bundle.pinned_bp:
            lines.append(f"- **{b['id']}** — {b['value'].strip().splitlines()[0]}")
        lines.append("")

    if bundle.current_bp:
        lines.append("## What's near right now (Backpack: current)")
        lines.append("")
        kept, dropped = apply_budget(
            bundle.current_bp,
            budget_for(RENDERER_ID, "current", bundle.freshness_policy),
        )
        for b in kept:
            first_line = b["value"].strip().splitlines()[0]
            lines.append(f"- **{b['id']}** ({b.get('dated', '?')}). {first_line}")
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
            lines.append(f"- `{b['id']}` ({age_note}). Re-confirm before acting.")
        if dropped:
            lines.append(f"- _… +{dropped} more verify items not shown (budgeted)._")
        lines.append("")

    # Follow-up #6: Routing hints
    lines.append("## Routing hints")
    lines.append("")
    lines.extend(_routing_hints_lines(bundle))
    lines.append("")

    # Follow-up #6: Open threads worth knowing
    open_threads = _open_threads(bundle)
    if open_threads:
        lines.append("## Open threads worth knowing")
        lines.append("")
        for b in open_threads:
            first = (b.get("value") or "").strip().splitlines()[0] if b.get("value") else ""
            lines.append(f"- **{b['id']}** — {first}")
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
