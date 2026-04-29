#!/usr/bin/env python3
"""
session_primer.py — render the session-primer surface from an operator root.

Reads the file-system-as-database layout (backpack/, doctrine/, policy/)
and produces a markdown brief that the assistant uses to bootstrap a
session. This is a pure projection: no writes, no LLM calls.

The session primer is the simplest renderer in the system. Per
[ADR 0003](../docs/decisions/0003-renderers-over-one-truth-layer.md) it
must:

  1. Read pinned Doctrine first (identity, defaults, key workflows, key policies).
  2. Read current Backpack second (active carry-state, sorted by renderer_priority).
  3. Surface a "verify before acting" section for items in the `recent`
     freshness band that carry the implicit verify-after-N-days rule.
  4. Honor `consent.applies_to_renderers` on policy entries by quietly
     omitting any item whose scope intersects with a `forbidden` posture.

Usage:
    python renderers/session_primer.py <operator-root>
    python renderers/session_primer.py examples/operator-root-fixture

Outputs the rendered markdown to stdout. Returns exit code 0 on success.

Requires: pyyaml (for frontmatter parsing).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml  # type: ignore


# ---------------------------------------------------------------------------
# Frontmatter loader (mirrors tools/validate.py)
# ---------------------------------------------------------------------------

class _StringDateLoader(yaml.SafeLoader):
    pass


_StringDateLoader.add_constructor(
    "tag:yaml.org,2002:timestamp",
    lambda loader, node: loader.construct_scalar(node),
)


def load_frontmatter(path: Path) -> tuple[dict, str]:
    """Return (frontmatter_dict, body_string). Body is the markdown after the
    closing '---', stripped. Frontmatter may itself contain a 'body' key
    (Doctrine convention); in that case the trailing markdown body is empty
    and the frontmatter body is authoritative."""
    text = path.read_text(encoding="utf-8")
    m = re.match(r"---\n(.*?)\n---\n?(.*)", text, re.S)
    if not m:
        raise ValueError(f"no frontmatter in {path}")
    fm = yaml.load(m.group(1), Loader=_StringDateLoader) or {}
    body = m.group(2).strip()
    return fm, body


# ---------------------------------------------------------------------------
# Layer reads
# ---------------------------------------------------------------------------

def read_doctrine(operator_root: Path) -> list[dict]:
    """Read every doctrine/*/*.md as a Doctrine entry. Each return dict has
    the merged frontmatter; the markdown body (if any) is folded into the
    'body' key when the frontmatter lacks one."""
    entries: list[dict] = []
    for path in sorted((operator_root / "doctrine").rglob("*.md")):
        fm, body = load_frontmatter(path)
        if "body" not in fm and body:
            fm["body"] = body
        fm["_path"] = str(path.relative_to(operator_root))
        entries.append(fm)
    return entries


def read_backpack(operator_root: Path) -> list[dict]:
    """Read every backpack/*/*.md (excluding _replaced/) as a Backpack item.
    Frontmatter keys are the structured form; the markdown body becomes 'value'."""
    entries: list[dict] = []
    for path in sorted((operator_root / "backpack").rglob("*.md")):
        # Skip the replacement archive — those items are out of carry-state.
        if "_replaced" in path.parts:
            continue
        fm, body = load_frontmatter(path)
        if "value" not in fm and body:
            fm["value"] = body
        fm["_path"] = str(path.relative_to(operator_root))
        entries.append(fm)
    return entries


def read_policy(operator_root: Path) -> dict | None:
    p = operator_root / "policy" / "freshness.json"
    if not p.is_file():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Consent gate
# ---------------------------------------------------------------------------

RENDERER_ID = "session-primer"


def consent_filter(items: list[dict], doctrine: list[dict]) -> tuple[list[dict], list[str]]:
    """Drop any item whose scope intersects a 'forbidden' consent posture
    that names this renderer in `applies_to_renderers`. Returns the filtered
    list and a list of human-readable rationale strings for omissions."""
    forbidden_scopes: list[str] = []
    for entry in doctrine:
        if entry.get("kind") != "policy":
            continue
        consent = entry.get("consent")
        if not consent:
            continue
        if consent.get("posture") != "forbidden":
            continue
        renderers = consent.get("applies_to_renderers") or []
        if RENDERER_ID in renderers:
            forbidden_scopes.append(consent["scope"])

    if not forbidden_scopes:
        return items, []

    kept: list[dict] = []
    omissions: list[str] = []
    for item in items:
        tags = set(item.get("tags") or [])
        scope = item.get("scope") or ""
        # Match if any forbidden scope token appears as a tag or as the item's
        # `scope` field (a real implementation would be more sophisticated).
        hit = next(
            (s for s in forbidden_scopes if s in tags or s == scope),
            None,
        )
        if hit:
            omissions.append(f"{item.get('id', '?')} (matched forbidden scope '{hit}')")
        else:
            kept.append(item)
    return kept, omissions


# ---------------------------------------------------------------------------
# Sorting + projection
# ---------------------------------------------------------------------------

def applies_here(entry: dict) -> bool:
    surfaces = entry.get("renderer_hints", {}).get("surfaces") or entry.get("applies_to") or []
    return RENDERER_ID in surfaces or not surfaces


def by_priority(entry: dict) -> int:
    """Higher priority first; default 50."""
    rh = entry.get("renderer_hints") or {}
    return -int(rh.get("priority", 50))


def parse_iso(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


def freshness_age_days(item: dict, now: datetime) -> float | None:
    created = parse_iso(item.get("created_at"))
    if not created:
        return None
    delta = now - created
    return delta.total_seconds() / 86400.0


def needs_verify(item: dict, now: datetime, verify_after_days: int) -> bool:
    """`recent` freshness band crosses the verify threshold; `current` items
    on the cusp also surface a verify nudge."""
    if item.get("freshness_class") == "recent":
        return True
    age = freshness_age_days(item, now)
    return age is not None and age >= verify_after_days


# ---------------------------------------------------------------------------
# Renderer
# ---------------------------------------------------------------------------

def render(operator_root: Path, now: datetime | None = None) -> str:
    now = now or datetime.now(timezone.utc)
    doctrine = read_doctrine(operator_root)
    backpack = read_backpack(operator_root)
    policy = read_policy(operator_root)

    backpack, omitted_for_consent = consent_filter(backpack, doctrine)

    # Doctrine groupings.
    by_kind: dict[str, list[dict]] = {}
    for entry in doctrine:
        if not applies_here(entry):
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
        e for e in by_kind.get("policy") or []
        # Skip consent-only policies (the rule applies; the wording would be noise).
        if not (e.get("consent") and not e.get("body"))
    ]

    # Backpack groupings.
    pinned_bp = [b for b in backpack if b.get("freshness_class") == "pinned" and applies_here(b)]
    current_bp = [b for b in backpack if b.get("freshness_class") == "current" and applies_here(b)]
    recent_bp = [b for b in backpack if b.get("freshness_class") == "recent" and applies_here(b)]

    pinned_bp.sort(key=by_priority)
    current_bp.sort(key=by_priority)
    recent_bp.sort(key=by_priority)

    verify_after_days = (policy or {}).get("rules", {}).get("verify_after_days", 7)
    needs_verify_items = [
        b for b in (current_bp + recent_bp)
        if needs_verify(b, now, verify_after_days)
    ]

    # Now build the markdown.
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
            age = freshness_age_days(b, now)
            age_note = f"~{age:.0f}d old" if age is not None else "no created_at"
            lines.append(f"- `{b['id']}` ({age_note}). Re-confirm before acting.")
        lines.append("")

    if omitted_for_consent:
        lines.append("## Consent gate")
        lines.append("")
        lines.append(f"{len(omitted_for_consent)} item(s) suppressed by a forbidden consent posture.")
        lines.append("Renderers MUST NOT name suppressed items. (See policies in Doctrine.)")
        lines.append("")

    # Footer.
    lines.append("---")
    lines.append(
        f"*Source: `{operator_root}`. Rendered {now.isoformat()} by "
        f"`renderers/session_primer.py`. Pure projection over Backpack + Doctrine.*"
    )

    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

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
