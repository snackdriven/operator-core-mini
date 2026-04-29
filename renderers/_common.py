"""
_common.py — shared loaders, helpers, and consent gate for all renderers.

Renderers in this directory are pure projections over an operator root laid
out as `backpack/`, `doctrine/`, `policy/`. Each renderer owns its own output
format, but they share the same substrate-reading logic; that lives here so
the renderers can stay focused on selection + rendering.

Per ADR 0003, a renderer MUST:

  * be read-only,
  * declare its own `RENDERER_ID`,
  * honor `renderer_hints` (allow/deny lists, priority),
  * honor consent policies via `consent_filter`,
  * be idempotent for a given (operator_root, now) input.
"""
from __future__ import annotations

import json
import re
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
    """Return (frontmatter_dict, body_string).

    Body is the markdown after the closing ``---``, stripped. Frontmatter may
    itself contain a ``body`` key (Doctrine convention); in that case the
    trailing markdown body is empty and the frontmatter body is authoritative.
    """
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
    """Read every ``doctrine/*/*.md`` as a Doctrine entry. Each return dict
    has the merged frontmatter; the markdown body (if any) is folded into
    the ``body`` key when the frontmatter lacks one. ``_path`` is added for
    debugging."""
    entries: list[dict] = []
    root = operator_root / "doctrine"
    if not root.is_dir():
        return entries
    for path in sorted(root.rglob("*.md")):
        fm, body = load_frontmatter(path)
        if "body" not in fm and body:
            fm["body"] = body
        fm["_path"] = str(path.relative_to(operator_root))
        entries.append(fm)
    return entries


def read_backpack(operator_root: Path) -> list[dict]:
    """Read every ``backpack/*/*.md`` (excluding ``_replaced/``) as a Backpack
    item. Frontmatter keys are the structured form; the markdown body becomes
    the ``value`` field when the frontmatter doesn't already set one."""
    entries: list[dict] = []
    root = operator_root / "backpack"
    if not root.is_dir():
        return entries
    for path in sorted(root.rglob("*.md")):
        # Skip the replacement archive — those items are out of carry-state.
        if "_replaced" in path.parts:
            continue
        fm, body = load_frontmatter(path)
        if "value" not in fm and body:
            fm["value"] = body
        fm["_path"] = str(path.relative_to(operator_root))
        entries.append(fm)
    return entries


def read_freshness_policy(operator_root: Path) -> dict | None:
    p = operator_root / "policy" / "freshness.json"
    if not p.is_file():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Consent gate
# ---------------------------------------------------------------------------

def _forbidden_policies_for(renderer_id: str, doctrine: list[dict]) -> list[dict]:
    """Return every policy entry whose consent block forbids this renderer.
    Each entry's full consent dict is returned (callers want ``scope`` and
    ``gate_message``)."""
    out: list[dict] = []
    for entry in doctrine:
        if entry.get("kind") != "policy":
            continue
        consent = entry.get("consent")
        if not consent:
            continue
        if consent.get("posture") != "forbidden":
            continue
        renderers = consent.get("applies_to_renderers") or []
        if renderer_id in renderers:
            out.append(consent)
    return out


GENERIC_GATE_MESSAGE = (
    "{count} item(s) suppressed by a forbidden consent posture. "
    "Renderers MUST NOT name suppressed items."
)
GENERIC_GATE_MESSAGE_SHORT = "{count} private"


def forbidden_scopes_for(renderer_id: str, doctrine: list[dict]) -> list[str]:
    """Back-compat helper: return only the scope strings."""
    return [c["scope"] for c in _forbidden_policies_for(renderer_id, doctrine)]


def consent_filter(
    items: list[dict],
    doctrine: list[dict],
    renderer_id: str,
) -> tuple[list[dict], list[str], list[str]]:
    """Drop any item whose scope intersects a forbidden consent posture
    targeting this renderer.

    Returns ``(kept, omission_rationales, gate_messages)``:
      * ``kept`` — items that survive the gate, in input order.
      * ``omission_rationales`` — debug strings naming suppressed items;
        renderers MUST NOT surface these (they are for audit / logging).
      * ``gate_messages`` — rendered ``gate_message`` strings (one per
        policy that actually fired), with ``{count}`` already substituted.
        Renderers SHOULD display these verbatim. If a forbidding policy
        omits ``gate_message``, a generic count-only string is generated
        from ``GENERIC_GATE_MESSAGE``.
    """
    policies = _forbidden_policies_for(renderer_id, doctrine)
    if not policies:
        return items, [], []

    # Per-policy bookkeeping so we can render policy-specific gate messages.
    per_policy_count: dict[int, int] = {id(p): 0 for p in policies}

    kept: list[dict] = []
    omissions: list[str] = []
    for item in items:
        tags = set(item.get("tags") or [])
        scope = item.get("scope") or ""
        hit_policy = next(
            (p for p in policies if p["scope"] in tags or p["scope"] == scope),
            None,
        )
        if hit_policy is not None:
            per_policy_count[id(hit_policy)] += 1
            omissions.append(
                f"{item.get('id', '?')} (matched forbidden scope '{hit_policy['scope']}')"
            )
        else:
            kept.append(item)

    gate_messages: list[str] = []
    for p in policies:
        count = per_policy_count[id(p)]
        if count == 0:
            continue
        template = p.get("gate_message") or GENERIC_GATE_MESSAGE
        try:
            gate_messages.append(template.format(count=count))
        except (KeyError, IndexError, ValueError):
            # Bad template — fail safe to the generic form rather than crash.
            gate_messages.append(GENERIC_GATE_MESSAGE.format(count=count))

    return kept, omissions, gate_messages


def consent_gate_short(
    doctrine: list[dict],
    omissions: list[str],
    renderer_id: str,
) -> list[str]:
    """Compact equivalent of the gate_messages return from `consent_filter`,
    suitable for ambient surfaces. Pass the omissions list returned by
    `consent_filter` so per-policy counts can be rebuilt from the rationale
    strings (which carry the matched scope).

    Returns one short message per forbidding policy that actually fired.
    Each policy contributes its `gate_message_short` if set, otherwise
    `GENERIC_GATE_MESSAGE_SHORT`.
    """
    if not omissions:
        return []

    policies = _forbidden_policies_for(renderer_id, doctrine)
    if not policies:
        return []

    # Rebuild per-policy counts from the rationale strings. The rationale
    # format is set above as: `<id> (matched forbidden scope '<scope>')`.
    counts: dict[str, int] = {}
    for r in omissions:
        m = re.search(r"matched forbidden scope '([^']+)'", r)
        if not m:
            continue
        counts[m.group(1)] = counts.get(m.group(1), 0) + 1

    out: list[str] = []
    for p in policies:
        n = counts.get(p["scope"], 0)
        if not n:
            continue
        template = p.get("gate_message_short") or GENERIC_GATE_MESSAGE_SHORT
        try:
            out.append(template.format(count=n))
        except (KeyError, IndexError, ValueError):
            out.append(GENERIC_GATE_MESSAGE_SHORT.format(count=n))
    return out


# ---------------------------------------------------------------------------
# Renderer-hint helpers
# ---------------------------------------------------------------------------

def applies_here(entry: dict, renderer_id: str) -> bool:
    """True if this entry should surface in this renderer.

    Honors both the schema field ``renderer_hints.surfaces`` (allowlist) and
    the legacy ``applies_to`` array; default-include when neither is set.
    Honors ``renderer_hints.never_surface_in`` as a denylist override.
    """
    hints = entry.get("renderer_hints") or {}
    deny = hints.get("never_surface_in") or []
    if renderer_id in deny:
        return False
    surfaces = hints.get("surfaces") or entry.get("applies_to") or []
    return renderer_id in surfaces or not surfaces


def by_priority(entry: dict) -> int:
    """Sort key: higher renderer_hints.priority first; default 50."""
    rh = entry.get("renderer_hints") or {}
    return -int(rh.get("priority", 50))


# ---------------------------------------------------------------------------
# Time helpers
# ---------------------------------------------------------------------------

def parse_iso(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


def parse_date(s: str | None) -> datetime | None:
    """Accept either an ISO-8601 datetime or a YYYY-MM-DD date string."""
    if not s:
        return None
    dt = parse_iso(s)
    if dt:
        return dt
    try:
        return datetime.strptime(s, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return None


def age_days(item: dict, now: datetime, key: str = "created_at") -> float | None:
    created = parse_iso(item.get(key))
    if not created:
        # Some items only carry a date (``dated``); fall back to that.
        created = parse_date(item.get("dated"))
    if not created:
        return None
    delta = now - created
    return delta.total_seconds() / 86400.0


def needs_verify(item: dict, now: datetime, verify_after_days: int) -> bool:
    """Items in the ``recent`` band always surface a verify nudge. Items in
    other bands surface one if they've crossed the ``verify_after_days``
    threshold from the freshness policy."""
    if item.get("freshness_class") == "recent":
        return True
    age = age_days(item, now)
    return age is not None and age >= verify_after_days


# ---------------------------------------------------------------------------
# Voice rule selection (for narrator-style renderers)
# ---------------------------------------------------------------------------

def select_voice_rule(
    doctrine: list[dict],
    renderer_id: str,
    skin_override: str | None = None,
) -> dict | None:
    """Pick a ``kind: voice-rule`` Doctrine entry that applies to this
    renderer. Returns the entry dict or None.

    Selection order:
      1. If ``skin_override`` is given, match by ``voice.skin`` exactly.
      2. Otherwise pick the highest-priority voice-rule whose ``voice.scope``
         contains ``renderer_id`` or is empty (applies-anywhere).
      3. If two rules tie on priority, prefer the one with a non-empty scope
         over an applies-anywhere rule (more specific wins).
    """
    candidates = [e for e in doctrine if e.get("kind") == "voice-rule" and e.get("voice")]
    if not candidates:
        return None

    if skin_override is not None:
        for e in candidates:
            if e["voice"].get("skin") == skin_override:
                return e
        return None

    def applies(e: dict) -> bool:
        scope = e["voice"].get("scope") or []
        return renderer_id in scope or not scope

    eligible = [e for e in candidates if applies(e)]
    if not eligible:
        return None

    def sort_key(e: dict) -> tuple[int, int, str]:
        # Per ADR 0005: priority desc, scope-specificity (specific wins),
        # then lexicographic skin id for determinism.
        prio = -int((e.get("renderer_hints") or {}).get("priority", 50))
        scope_specificity = 0 if (e["voice"].get("scope") or []) else 1
        skin = e["voice"].get("skin") or ""
        return (prio, scope_specificity, skin)

    eligible.sort(key=sort_key)
    return eligible[0]


def select_routing_rule(
    doctrine: list[dict],
    when: str | None = None,
) -> dict | None:
    """Pick a ``kind: routing-rule`` whose ``routing.when`` matches the given
    state token (e.g. 'low-energy'). Returns None if nothing matches.

    No condition language is implemented here; ``when`` strings are matched
    by exact equality. A real implementation would evaluate the predicate
    against current life-state.
    """
    if not when:
        return None
    for e in doctrine:
        if e.get("kind") != "routing-rule":
            continue
        routing = e.get("routing") or {}
        if routing.get("when") == when:
            return e
    return None
