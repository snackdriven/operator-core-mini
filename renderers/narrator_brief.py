#!/usr/bin/env python3
"""
narrator_brief.py — render the narrator-brief *prompt* surface.

narrator-brief is the LLM-mediated companion to narrator-list. The
renderer itself is still a pure projection over the FactBundle: it does
not call an LLM and produces deterministic output. What it produces is
not narrator prose; it is a *prompt artefact* — a markdown document that
an LLM consumes to render the prose surface offline. Per ADR 0003 the
fact set is identical to what narrator-list, daily-brief, and statusline
would surface for the same state; only the framing (and the medium —
prompt instead of finished list) varies.

Per the 2026-04-29 clarification on ADR 0005:

  * narrator-list  — template-driven, deterministic markdown list.
  * narrator-brief — prompt-driven; output is a prompt for an LLM.
  * Voice-rule selection is identical for both surfaces.

The prompt is laid out in four blocks so a tool can split it cleanly:

  1. ``# Narrator brief prompt — <date>`` — human-readable header.
  2. ``---`` YAML frontmatter system block (``role: system``) declaring
     the active voice rule, do/avoid lists, ``prompt_version``, and a
     "facts stable, framing adapts" reminder. This is the operator-side
     prompt the LLM sees.
  3. A ``## Facts`` block — markdown rendering of the FactBundle with
     stable item ids, used as ground truth.
  4. A ``## Instruction`` block — the load-bearing render instruction.
     Treated as versioned (see ``prompt_version`` in the system block);
     iterate based on actual LLM output.

Per ADR 0004 the consent gate runs first; the prompt only ever names
items that survived the gate. Suppressed items surface as a banner in
the system block (count + gate message) so the LLM knows aggregate
context exists without naming it.

Usage:
    python renderers/narrator_brief.py <operator-root> \
        [--now ISO-8601] [--skin good-place|mass-effect|...] \
        [--energy low-energy|...]
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


RENDERER_ID = "narrator-brief"
PROMPT_VERSION = 1


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def first_line(s: str | None) -> str:
    if not s:
        return ""
    return s.strip().splitlines()[0] if s.strip() else ""


def _yaml_quote(s: str) -> str:
    """Single-quote a string for a YAML scalar; double single-quotes inside."""
    return "'" + s.replace("'", "''") + "'"


def _yaml_list(items: list[str]) -> str:
    if not items:
        return "[]"
    return "[" + ", ".join(_yaml_quote(i) for i in items) + "]"


# ---------------------------------------------------------------------------
# Renderer
# ---------------------------------------------------------------------------

def render(
    operator_root: Path,
    now: datetime | None = None,
    skin: str | None = None,
    energy: str | None = None,
) -> str:
    now = now or datetime.now(timezone.utc)
    bundle = build_fact_bundle(
        operator_root, now, RENDERER_ID,
        voice_skin_override=skin,
        energy=energy,
    )

    voice = bundle.voice
    if skin:
        voice_source = "cli --skin"
    elif bundle.routing:
        voice_source = (
            f"routing-rule `{bundle.routing.get('id', '?')}` (when={energy})"
        )
    else:
        voice_source = "default voice-rule (highest priority)"

    voice_obj = (voice or {}).get("voice") or {}
    skin_id = voice_obj.get("skin", "neutral")
    register = voice_obj.get("register", "neutral")
    do_rules = voice_obj.get("do") or []
    avoid_rules = voice_obj.get("avoid") or []

    date_str = now.strftime("%Y-%m-%d")

    lines: list[str] = []
    lines.append(f"# Narrator brief prompt — {date_str}")
    lines.append("")
    lines.append(
        "> This document is a *prompt*, not narrator prose. An LLM"
        " consumes the system block + facts and renders prose offline."
        " The facts surface here is identical to what narrator-list,"
        " daily-brief, and statusline would surface for the same state"
        " (ADR 0003)."
    )
    lines.append("")

    # --- System block ---------------------------------------------------
    lines.append("---")
    lines.append("role: system")
    lines.append(f"prompt_version: {PROMPT_VERSION}")
    lines.append(f"renderer_id: {RENDERER_ID}")
    lines.append(f"rendered_at: {now.isoformat()}")
    lines.append("voice:")
    lines.append(f"  skin: {skin_id}")
    lines.append(f"  register: {register}")
    lines.append(f"  selected_via: {_yaml_quote(voice_source)}")
    lines.append(f"  do: {_yaml_list(do_rules)}")
    lines.append(f"  avoid: {_yaml_list(avoid_rules)}")
    lines.append(
        "contract: 'Facts stable across renderers; only framing adapts."
        " Do not invent items not in the Facts block. Cite each prose"
        " claim by item id in a trailing comment.'"
    )
    if bundle.gate_messages:
        lines.append("consent_banner:")
        for msg in bundle.gate_messages:
            lines.append(f"  - {_yaml_quote(msg)}")
    lines.append("---")
    lines.append("")

    # --- Facts block -----------------------------------------------------
    lines.append("## Facts")
    lines.append("")

    if bundle.today_lifestate:
        ls = bundle.today_lifestate
        lines.append("### Today's life-state")
        lines.append("")
        lines.append(f"- **{ls.get('id', '?')}** — {first_line(ls.get('value'))}")
        lines.append("")

    if bundle.near_today:
        lines.append("### In the bag")
        lines.append("")
        kept, dropped = apply_budget(
            bundle.near_today,
            budget_for(RENDERER_ID, "current", bundle.freshness_policy),
        )
        for b in kept:
            lines.append(f"- **{b['id']}** — {first_line(b.get('value'))}")
        if dropped:
            lines.append(f"- _… +{dropped} more current items not shown (budgeted)._")
        lines.append("")

    if bundle.verify_items:
        lines.append("### Verify before acting")
        lines.append("")
        kept, dropped = apply_budget(
            bundle.verify_items,
            budget_for(RENDERER_ID, "verify", bundle.freshness_policy),
        )
        for b in kept:
            age = age_days(b, now)
            age_note = f"~{age:.0f}d old" if age is not None else "no created_at"
            lines.append(f"- **{b['id']}** ({age_note}) — {first_line(b.get('value'))}")
        if dropped:
            lines.append(f"- _… +{dropped} more verify items not shown (budgeted)._")
        lines.append("")

    if bundle.this_week:
        lines.append("### This week")
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

    if bundle.aged_out:
        lines.append("### Aged out overnight")
        lines.append("")
        kept, dropped = apply_budget(
            bundle.aged_out,
            budget_for(RENDERER_ID, "aged_out", bundle.freshness_policy),
        )
        for b in kept:
            ts = (b.get("aged_out_at") or "").split("T")[0] or "?"
            lines.append(f"- **{b['id']}** (aged out {ts}) — {first_line(b.get('value'))}")
        if dropped:
            lines.append(f"- _… +{dropped} more aged-out items not shown (budgeted)._")
        lines.append("")

    if not (bundle.today_lifestate or bundle.near_today or bundle.verify_items
            or bundle.this_week or bundle.aged_out):
        lines.append("- *(no facts surfaced for this renderer at this time)*")
        lines.append("")

    # --- Instruction block ----------------------------------------------
    lines.append("## Instruction")
    lines.append("")
    lines.append(
        "Render the Facts block above as prose using the voice rule"
        f" declared in the system block (skin: `{skin_id}`, register:"
        f" `{register}`). Apply the do/avoid rules verbatim. Do not"
        " invent items not in the Facts block. Cite each prose claim by"
        " item id in a trailing HTML comment (e.g. `<!-- cite: q2-roadmap-sync -->`)."
        " Keep the prose under ~250 words. End with a single-line closer"
        " consistent with the active voice."
    )
    lines.append("")

    # --- Footer ----------------------------------------------------------
    lines.append("---")
    lines.append(
        f"*Source: `{operator_root}`. Rendered {now.isoformat()} by "
        f"`renderers/narrator_brief.py`. Deterministic prompt artefact;"
        f" the LLM step is outside the renderer boundary.*"
    )
    return "\n".join(lines) + "\n"


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    p.add_argument("operator_root", help="Path to the operator root directory")
    p.add_argument("--now", help="ISO-8601 timestamp (overrides 'now' for tests)")
    p.add_argument("--skin", help="Voice skin to render (overrides default + routing)")
    p.add_argument("--energy", help="Energy/state token for routing-rule lookup")
    args = p.parse_args(argv[1:])

    operator_root = Path(args.operator_root).resolve()
    if not (operator_root / "doctrine").is_dir():
        print(f"not an operator root (no doctrine/): {operator_root}", file=sys.stderr)
        return 1

    now = parse_iso(args.now) if args.now else datetime.now(timezone.utc)
    sys.stdout.write(render(operator_root, now=now, skin=args.skin, energy=args.energy))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
