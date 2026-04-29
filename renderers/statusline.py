#!/usr/bin/env python3
"""
statusline.py — render the ambient single-line status surface.

The statusline is the tightest renderer: one line, no markdown, terminal-
friendly. It exists to give the operator a glance at carry-state without
context-switching into a richer surface. Per ADR 0003 and ADR 0004 it is
a pure projection and consent-gated; per writing-preferences it avoids
exclamation points and ranked priority lists.

The line is built from short tokens separated by ' · '. Tokens come from:

  * The date (MM-DD)
  * The single highest-priority current backpack item's ``summary`` (or
    the generated short form of its first line)
  * A meeting/event token if a current item with tag 'q2' or 'sync' is
    dated today
  * The number of items needing verification today
  * The number of items suppressed by the consent gate (count only)

Anything that would require more than one short token is left to richer
renderers.

Usage:
    python renderers/statusline.py <operator-root> [--now ISO-8601]

Outputs a single line of plain text to stdout, terminated with a newline.
"""
from __future__ import annotations

import argparse
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _common import (  # noqa: E402
    build_fact_bundle,
    parse_iso,
)


RENDERER_ID = "statusline"

# Short summary that would render on a status bar — maximum chars.
SUMMARY_MAX_CHARS = 60


def short_summary(item: dict) -> str:
    """Use ``summary`` if present; otherwise compress the first body line."""
    s = (item.get("summary") or "").strip()
    if s:
        return s
    body = (item.get("value") or "").strip().splitlines()[0] if item.get("value") else ""
    body = re.sub(r"^\d{4}-\d{2}-\d{2}\s+[-—:]\s*", "", body)  # strip date prefix
    body = re.sub(r"\s+", " ", body)
    if len(body) > SUMMARY_MAX_CHARS:
        body = body[: SUMMARY_MAX_CHARS - 1].rstrip() + "…"
    return body


def render(operator_root: Path, now: datetime | None = None) -> str:
    now = now or datetime.now(timezone.utc)
    bundle = build_fact_bundle(operator_root, now, RENDERER_ID)

    tokens: list[str] = []
    tokens.append(now.strftime("%m-%d"))

    if bundle.current_bp:
        tokens.append(short_summary(bundle.current_bp[0]))

    today_str = now.strftime("%Y-%m-%d")
    today_event = next(
        (
            b for b in bundle.current_bp[1:]
            if str(b.get("dated") or "")[:10] == today_str
            and any(t in (b.get("tags") or []) for t in ("sync", "meeting", "q2"))
        ),
        None,
    )
    if today_event:
        tokens.append(short_summary(today_event))

    if bundle.verify_items:
        tokens.append(f"{len(bundle.verify_items)} stale")

    # Per ADR 0004 the gate banner comes from the policy itself; per ADR 0005
    # the renderer just emits whatever the policy supplied (or the generic
    # short token if none was supplied).
    tokens.extend(bundle.gate_messages_short)

    return " · ".join(tokens) + "\n"


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
