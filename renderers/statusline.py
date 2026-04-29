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
    python renderers/statusline.py <operator-root> --json

Default output is a single line of plain text terminated with a newline.
With ``--json``, emits a structured payload of the same already-filtered
tokens for consumers that want to compose their own surface (for example,
the claude-statusline shell renderer, which projects each token into its
own region with independent TTL/priority/color). The JSON shape is::

    {
      "date":         "04-29",
      "carry":        "<top current backpack item summary>" | "",
      "today_event":  "<today-dated q2/sync/meeting summary>" | "",
      "verify_count": <int>,
      "gate_short":   "<first short gate message, if any>" | "",
      "gate_short_all": [<every short gate message>],
      "tokens":       [<the joined string's tokens, in order>]
    }

All consent / surfaces / never_surface_in / freshness filtering happens
inside ``build_fact_bundle`` per ADR 0003 + 0004; the JSON form just
exposes the same already-filtered facts without joining them.
"""
from __future__ import annotations

import argparse
import json
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


def _select_tokens(operator_root: Path, now: datetime) -> dict:
    """Build the structured token set both renderers project from.

    Returns a dict with stable keys (``date``, ``carry``, ``today_event``,
    ``verify_count``, ``gate_short_all``) plus the ordered ``tokens`` list
    that the plain-text renderer joins. Splitting selection from formatting
    keeps the string output and the ``--json`` output trivially in sync.
    """
    bundle = build_fact_bundle(operator_root, now, RENDERER_ID)

    date_token = now.strftime("%m-%d")
    carry = short_summary(bundle.current_bp[0]) if bundle.current_bp else ""

    today_str = now.strftime("%Y-%m-%d")
    today_event_item = next(
        (
            b for b in bundle.current_bp[1:]
            if str(b.get("dated") or "")[:10] == today_str
            and any(t in (b.get("tags") or []) for t in ("sync", "meeting", "q2"))
        ),
        None,
    )
    today_event = short_summary(today_event_item) if today_event_item else ""

    verify_count = len(bundle.verify_items)

    # Per ADR 0004 the gate banner comes from the policy itself; per ADR 0005
    # the renderer just emits whatever the policy supplied (or the generic
    # short token if none was supplied).
    gate_short_all = list(bundle.gate_messages_short)

    tokens: list[str] = [date_token]
    if carry:
        tokens.append(carry)
    if today_event:
        tokens.append(today_event)
    if verify_count:
        tokens.append(f"{verify_count} stale")
    tokens.extend(gate_short_all)

    return {
        "date": date_token,
        "carry": carry,
        "today_event": today_event,
        "verify_count": verify_count,
        "gate_short": gate_short_all[0] if gate_short_all else "",
        "gate_short_all": gate_short_all,
        "tokens": tokens,
    }


def render(operator_root: Path, now: datetime | None = None) -> str:
    now = now or datetime.now(timezone.utc)
    payload = _select_tokens(operator_root, now)
    return " · ".join(payload["tokens"]) + "\n"


def render_json(operator_root: Path, now: datetime | None = None) -> str:
    """Emit the structured token payload as a single JSON line.

    Keys are stable; consumers that pin field names (e.g. shell scripts
    using ``jq -r '.carry'``) will not break when new fields are added.
    A trailing newline is included so line-oriented readers behave.
    """
    now = now or datetime.now(timezone.utc)
    payload = _select_tokens(operator_root, now)
    return json.dumps(payload, ensure_ascii=False) + "\n"


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    p.add_argument("operator_root", help="Path to the operator root directory")
    p.add_argument("--now", help="ISO-8601 timestamp (overrides 'now' for tests)")
    p.add_argument(
        "--json",
        action="store_true",
        help="Emit structured JSON tokens instead of the joined plain-text line.",
    )
    args = p.parse_args(argv[1:])

    operator_root = Path(args.operator_root).resolve()
    if not (operator_root / "doctrine").is_dir():
        print(f"not an operator root (no doctrine/): {operator_root}", file=sys.stderr)
        return 1

    now = parse_iso(args.now) if args.now else datetime.now(timezone.utc)
    if args.json:
        sys.stdout.write(render_json(operator_root, now=now))
    else:
        sys.stdout.write(render(operator_root, now=now))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
