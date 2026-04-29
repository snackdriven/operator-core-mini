#!/usr/bin/env python3
"""
narrator_brief.py — render the narrator brief surface.

The narrator brief is the same facts as the daily brief, framed by an
active voice-rule from Doctrine. It's the surface that proves ADR 0003's
"facts stable, framing adapts" property: the rendered facts MUST not
diverge from what other renderers would surface for the same state; only
the voice envelope changes.

This is a deliberately *non-LLM* renderer. It does not rewrite prose.
Instead it:

  1. Picks an active voice-rule (kind=voice-rule). Selection order:
     a) ``--skin`` overrides everything,
     b) ``--energy`` triggers a routing-rule lookup that may pick a skin,
     c) otherwise the highest-priority voice-rule whose ``voice.scope``
        contains this renderer wins.
  2. Renders a fact bundle (today's shape, near-today items, verify-before-
     acting nudges, the overnight diff).
  3. Wraps the bundle in a header block that declares the active voice
     and a skin-specific opener / closer template. The do/avoid rules are
     reported in the header so a downstream LLM (or human) can apply them
     without re-querying Doctrine.

Per ADR 0004 the consent gate runs first; nothing scoped to a forbidden
posture for this renderer reaches the bundle, named or otherwise.

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
    applies_here,
    by_priority,
    consent_filter,
    needs_verify,
    parse_iso,
    read_backpack,
    read_doctrine,
    read_freshness_policy,
    select_routing_rule,
    select_voice_rule,
)


RENDERER_ID = "narrator-brief"


# ---------------------------------------------------------------------------
# Skin templates
# ---------------------------------------------------------------------------

# Each skin provides its own opener/closer/section-leads. Anything else the
# renderer needs to do per-skin lives here, not in the body of `render()`,
# so adding a skin doesn't require editing the renderer logic.
SKIN_TEMPLATES: dict[str, dict[str, str]] = {
    "good-place": {
        "opener": "Good morning, Kayla. It's {weekday}, the {ordinal} of {month}.",
        "near": "Here's what's already in your bag:",
        "verify": "Two notes from the verify-before-acting drawer:",
        "aged": "What moved on overnight (the Hoard takes good care of it):",
        "closer": "That's the whole day. Everything else is yours to shape.",
        "byline": "— *the narrator*",
    },
    "mass-effect": {
        "opener": "Situation, {date} {time}.",
        "near": "Active items:",
        "verify": "Verify before action:",
        "aged": "Demoted overnight:",
        "closer": "Decision point: pick one and move.",
        "byline": "— mission log, narrator channel",
    },
    "neutral": {
        "opener": "Brief for {date}.",
        "near": "In the bag:",
        "verify": "Verify before acting:",
        "aged": "Aged out overnight:",
        "closer": "End of brief.",
        "byline": "— narrator",
    },
}

DEFAULT_SKIN = "neutral"


def template_for(voice_rule: dict | None) -> dict[str, str]:
    if voice_rule:
        skin = (voice_rule.get("voice") or {}).get("skin") or DEFAULT_SKIN
    else:
        skin = DEFAULT_SKIN
    return SKIN_TEMPLATES.get(skin, SKIN_TEMPLATES[DEFAULT_SKIN])


# ---------------------------------------------------------------------------
# Fact bundle
# ---------------------------------------------------------------------------

def first_line(s: str | None) -> str:
    if not s:
        return ""
    return s.strip().splitlines()[0] if s.strip() else ""


def build_bundle(operator_root: Path, now: datetime) -> dict:
    doctrine = read_doctrine(operator_root)
    backpack = read_backpack(operator_root)
    policy = read_freshness_policy(operator_root)

    backpack, _omitted, gate_messages = consent_filter(backpack, doctrine, RENDERER_ID)

    here = lambda b: applies_here(b, RENDERER_ID)
    current = sorted([b for b in backpack if b.get("freshness_class") == "current" and here(b)], key=by_priority)
    recent = sorted([b for b in backpack if b.get("freshness_class") == "recent" and here(b)], key=by_priority)

    verify_after_days = (policy or {}).get("rules", {}).get("verify_after_days", 7)
    verify_items = [b for b in (current + recent) if needs_verify(b, now, verify_after_days)]
    near_today = [b for b in current if b not in verify_items]

    return {
        "doctrine": doctrine,
        "near_today": near_today,
        "verify_items": verify_items,
        "gate_messages": gate_messages,
    }


# ---------------------------------------------------------------------------
# Renderer
# ---------------------------------------------------------------------------

def _fmt_date_tokens(now: datetime) -> dict[str, str]:
    day = now.day
    suffix = "th" if 11 <= day <= 13 else {1: "st", 2: "nd", 3: "rd"}.get(day % 10, "th")
    return {
        "weekday": now.strftime("%A"),
        "month": now.strftime("%B"),
        "ordinal": f"{day}{suffix}",
        "date": now.strftime("%Y-%m-%d"),
        "time": now.strftime("%H:%M %Z").strip(),
    }


def render(
    operator_root: Path,
    now: datetime | None = None,
    skin: str | None = None,
    energy: str | None = None,
) -> str:
    now = now or datetime.now(timezone.utc)
    bundle = build_bundle(operator_root, now)
    doctrine = bundle["doctrine"]

    # Voice selection.
    if skin:
        voice = select_voice_rule(doctrine, RENDERER_ID, skin_override=skin)
        voice_source = "cli --skin"
    else:
        routing = select_routing_rule(doctrine, when=energy) if energy else None
        if routing and (routing.get("routing") or {}).get("narrator"):
            voice = select_voice_rule(
                doctrine,
                RENDERER_ID,
                skin_override=routing["routing"]["narrator"],
            )
            voice_source = f"routing-rule `{routing.get('id', '?')}` (when={energy})"
        else:
            voice = select_voice_rule(doctrine, RENDERER_ID)
            voice_source = "default voice-rule (highest priority)"

    tpl = template_for(voice)
    fmts = _fmt_date_tokens(now)

    voice_obj = (voice or {}).get("voice") or {}
    skin_id = voice_obj.get("skin", DEFAULT_SKIN)
    register = voice_obj.get("register", "neutral")
    do_rules = voice_obj.get("do") or []
    avoid_rules = voice_obj.get("avoid") or []

    lines: list[str] = []
    lines.append(f"# Narrator Brief — {fmts['date']}")
    lines.append("")

    # Voice header — declares the active rule so downstream tooling can
    # see it without re-reading Doctrine.
    lines.append(f"> Voice: **{skin_id}** ({register}). Selected via {voice_source}.")
    lines.append(f"> Facts stable across renderers; only framing adapts (ADR 0003).")
    if do_rules:
        lines.append(f"> Do: {'; '.join(do_rules)}.")
    if avoid_rules:
        lines.append(f"> Avoid: {'; '.join(avoid_rules)}.")
    lines.append("")

    # Body — opener, near, verify, aged, closer.
    lines.append("---")
    lines.append("")
    lines.append(tpl["opener"].format(**fmts))
    lines.append("")

    if bundle["near_today"]:
        lines.append(tpl["near"])
        lines.append("")
        for b in bundle["near_today"]:
            lines.append(f"- **{b['id']}** — {first_line(b.get('value'))}")
        lines.append("")

    if bundle["verify_items"]:
        lines.append(tpl["verify"])
        lines.append("")
        for b in bundle["verify_items"]:
            age = age_days(b, now)
            age_note = f"~{age:.0f}d old" if age is not None else "no created_at"
            lines.append(f"- **{b['id']}** ({age_note}). {first_line(b.get('value'))}")
        lines.append("")

    lines.append(tpl["closer"])
    lines.append("")
    lines.append(tpl["byline"])
    lines.append("")

    if bundle["gate_messages"]:
        lines.append("---")
        lines.append("")
        for msg in bundle["gate_messages"]:
            lines.append(f"*{msg}*")
        lines.append("")

    lines.append("---")
    lines.append(
        f"*Source: `{operator_root}`. Rendered {now.isoformat()} by "
        f"`renderers/narrator_brief.py`. Pure projection over Backpack + Doctrine.*"
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
