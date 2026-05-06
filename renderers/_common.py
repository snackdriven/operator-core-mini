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
import sys

# On Windows, stdout may default to a narrow codec (e.g. cp1252) that can't
# encode Unicode characters like →. Reconfigure to UTF-8 so all renderers
# can emit arbitrary Unicode without crashing.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
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


def read_replaced(operator_root: Path) -> list[dict]:
    """Read ``backpack/_replaced/*.md`` — items that were superseded by a newer
    item in the same ``id`` family. NOTE: per ADR 0002, ``_replaced/`` is *not*
    "aged out". Aged-out content lives in Hoard; see :func:`read_hoard`.
    """
    entries: list[dict] = []
    p = operator_root / "backpack" / "_replaced"
    if not p.is_dir():
        return entries
    for path in sorted(p.rglob("*.md")):
        fm, body = load_frontmatter(path)
        if "value" not in fm and body:
            fm["value"] = body
        fm["_path"] = str(path.relative_to(operator_root))
        entries.append(fm)
    return entries


def read_hoard(operator_root: Path) -> list[dict]:
    """Read every ``hoard/**/*.md`` as a Hoard entry — items that aged out of
    active carry-state per ADR 0002. Each entry SHOULD carry an
    ``aged_out_at`` ISO-8601 timestamp; renderers use it to decide what
    happened "overnight" or "since last render".
    """
    entries: list[dict] = []
    root = operator_root / "hoard"
    if not root.is_dir():
        return entries
    for path in sorted(root.rglob("*.md")):
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
        # Per follow-up #7 (2026-04-29): consent.scope (a free-string)
        # matches against an item's tags. We previously also matched
        # against backpack-item.scope (an enum) for ergonomic reasons,
        # but the enum values never overlap with the free strings
        # operators write into consent policies, so the second clause
        # was effectively dead. The enum has been renamed to `area`
        # and is not consulted here.
        tags = set(item.get("tags") or [])
        hit_policy = next(
            (p for p in policies if p["scope"] in tags),
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


# ---------------------------------------------------------------------------
# Per-surface item budgets
# ---------------------------------------------------------------------------
#
# Backpacks tend to grow unbounded over time; without budgets the headline
# bullet-list sections ("Near today", "What's near right now", etc.) become
# walls of text that defeat the surface's purpose. Per-surface budgets cap
# the rendered list and surface a `+N more` footer when truncation happens.
# Pinned items are NEVER truncated — the operator chose them deliberately.
#
# Budget defaults are sized so the existing 4-item fixture renders unchanged
# (no budget triggers when item count <= the cap). Operators can override
# per-surface in policy/freshness.json under `renderer_budgets:`, e.g.:
#
#   { "renderer_budgets": { "daily-brief": { "current": 12 } } }

DEFAULT_RENDERER_BUDGETS: dict[str, dict[str, int]] = {
    "session-primer":  {"current": 12, "recent": 8,  "verify": 8,  "aged_out": 8},
    "daily-brief":     {"current": 10, "recent": 6,  "verify": 8,  "aged_out": 8},
    "narrator-list":   {"current": 8,  "recent": 4,  "verify": 0,  "aged_out": 4},
    "narrator-brief":  {"current": 8,  "recent": 4,  "verify": 0,  "aged_out": 4},
    "statusline":      {"current": 1,  "recent": 0,  "verify": 0,  "aged_out": 0},
}


def budget_for(renderer_id: str, slice_name: str, freshness: dict | None) -> int:
    """Return the per-surface budget for a slice.

    Looks first at policy/freshness.json `renderer_budgets`, then falls back
    to DEFAULT_RENDERER_BUDGETS, then to a permissive default of 50.
    """
    overrides = (freshness or {}).get("renderer_budgets") or {}
    o = overrides.get(renderer_id) or {}
    if slice_name in o:
        return int(o[slice_name])
    d = DEFAULT_RENDERER_BUDGETS.get(renderer_id) or {}
    if slice_name in d:
        return int(d[slice_name])
    return 50


def apply_budget(items: list, budget: int) -> tuple[list, int]:
    """Truncate ``items`` to ``budget``. Returns (kept, dropped_count).

    A budget of 0 keeps everything (treat 0 as “unset”).
    A negative budget keeps everything.
    """
    if not items or budget is None or budget <= 0 or len(items) <= budget:
        return list(items), 0
    return items[:budget], len(items) - budget


def by_priority(entry: dict) -> int:
    """Sort key: higher renderer_hints.priority first; default 50."""
    rh = entry.get("renderer_hints") or {}
    return -int(rh.get("priority", 50))


def by_priority_then_recency(entry: dict) -> tuple:
    """Sort key: priority desc, then `dated` desc, then id asc for stability.

    Used for headline backpack views where two items at default priority
    (50) need a tiebreak that surfaces the most-recent first instead of
    alphabetical-by-id (which is what the legacy migrator produces).
    """
    rh = entry.get("renderer_hints") or {}
    prio = -int(rh.get("priority", 50))
    # Reverse-sort by dated by negating the ISO string via a wrapper.
    # Python tuple sort is ascending; we want descending dated, so emit
    # the key as a tuple where ("~" * lack-of-dated, negated-dated).
    dated = (entry.get("dated") or "").strip()
    # Items with no dated land last (we treat them as oldest).
    no_date = 1 if not dated else 0
    # For descending dated, invert by subtracting from a high-water mark.
    # Cleaner: use a tuple (no_date, neg_year, neg_month, neg_day).
    if dated and len(dated) >= 10 and dated[4] == "-" and dated[7] == "-":
        try:
            y, m, d = int(dated[0:4]), int(dated[5:7]), int(dated[8:10])
            recency = (-y, -m, -d)
        except ValueError:
            recency = (0, 0, 0)
            no_date = 1
    else:
        recency = (0, 0, 0)
    return (prio, no_date, recency, entry.get("id") or "")


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


# ---------------------------------------------------------------------------
# Fact bundle (per-renderer projection)
# ---------------------------------------------------------------------------

# Default window for "what aged out overnight" — the daily brief looks back
# this far when reading Hoard. Tunable per call.
DEFAULT_AGED_OUT_WINDOW_HOURS = 36


@dataclass(frozen=True)
class FactBundle:
    """The single source of truth a renderer projects from.

    Per ADR 0003, all renderers share the same fact universe at time T;
    only framing varies. This dataclass is that universe, *already filtered*
    for the calling renderer (consent gate applied; ``applies_here`` applied
    to the headline backpack collections). Renderers consume this directly
    instead of re-walking the substrate; that's how we keep narrator-brief
    and daily-brief from silently disagreeing about the fact set.

    Fields with the ``_all`` suffix are unfiltered for callers that need
    the whole picture (e.g. session-primer's pinned doctrine groupings,
    which span all kinds and don't pre-filter by ``applies_to``).
    """

    now: datetime
    renderer_id: str
    operator_root: Path

    # Doctrine (unfiltered). Pinned + grouped views are derived helpers below.
    doctrine: list[dict]

    # Backpack — post-consent, post-applies_here.
    backpack: list[dict]
    pinned_bp: list[dict]
    current_bp: list[dict]
    recent_bp: list[dict]
    timeline_bp: list[dict]

    # Derived slices.
    near_today: list[dict]      # current_bp minus verify_items
    verify_items: list[dict]    # current_bp + recent_bp where needs_verify
    this_week: list[dict]       # recent_bp minus verify_items
    today_lifestate: dict | None

    # Diff sources.
    replaced: list[dict]        # backpack/_replaced/ — superseded items
    aged_out: list[dict]        # hoard/ — real aged-out (within window)

    # Voice + routing (relevant for narrator-style renderers; optional).
    voice: dict | None
    routing: dict | None

    # Consent gate output.
    omitted_for_consent: list[str]
    gate_messages: list[str]
    gate_messages_short: list[str]

    # Policy.
    freshness_policy: dict | None

    # Source-side counts (for renderer headers).
    backpack_total: int = 0
    replaced_total: int = 0
    aged_out_total: int = 0

    def pinned_doctrine_by_kind(self) -> dict[str, list[dict]]:
        """Group pinned, applies-here Doctrine by ``kind``, sorted by priority."""
        out: dict[str, list[dict]] = {}
        for entry in self.doctrine:
            if not applies_here(entry, self.renderer_id):
                continue
            if not entry.get("pinned", False):
                continue
            out.setdefault(entry["kind"], []).append(entry)
        for kind in out:
            out[kind].sort(key=by_priority)
        return out


def build_fact_bundle(
    operator_root: Path,
    now: datetime,
    renderer_id: str,
    *,
    voice_skin_override: str | None = None,
    energy: str | None = None,
    aged_out_window_hours: int = DEFAULT_AGED_OUT_WINDOW_HOURS,
) -> FactBundle:
    """Build the per-renderer FactBundle for time ``now``.

    This is the single point that calls the substrate loaders + selectors.
    Adding a new renderer means consuming the bundle, not re-walking files.

    Voice / routing selection is included here so narrator-style renderers
    don't repeat the lookup. For renderers that don't care, the fields are
    simply None.
    """
    doctrine = read_doctrine(operator_root)
    backpack_raw = read_backpack(operator_root)
    replaced_raw = read_replaced(operator_root)
    hoard_raw = read_hoard(operator_root)
    freshness = read_freshness_policy(operator_root)

    # --- Consent gate ----------------------------------------------------
    # Run the gate over the union so per-policy counts cover everything we
    # might surface, and the renderer sees one banner per policy rather
    # than one per substrate.
    union_in = (
        [("bp", b) for b in backpack_raw]
        + [("rp", b) for b in replaced_raw]
        + [("ho", b) for b in hoard_raw]
    )
    kept_combined, omitted, gate_messages = consent_filter(
        [item for _, item in union_in], doctrine, renderer_id
    )
    kept_ids = {id(item) for item in kept_combined}
    backpack = [b for b in backpack_raw if id(b) in kept_ids]
    replaced = [b for b in replaced_raw if id(b) in kept_ids]
    aged_out_all = [b for b in hoard_raw if id(b) in kept_ids]
    short_gate = consent_gate_short(doctrine, omitted, renderer_id)

    # --- applies_here scoping for headline backpack views ---------------
    here = lambda b: applies_here(b, renderer_id)
    pinned_bp = sorted(
        [b for b in backpack if b.get("freshness_class") == "pinned" and here(b)],
        key=by_priority,
    )
    current_bp = sorted(
        [b for b in backpack if b.get("freshness_class") == "current" and here(b)],
        key=by_priority_then_recency,
    )
    recent_bp = sorted(
        [b for b in backpack if b.get("freshness_class") == "recent" and here(b)],
        key=by_priority_then_recency,
    )
    timeline_bp = sorted(
        [b for b in backpack if b.get("memory_class") == "timeline" and here(b)],
        key=by_priority_then_recency,
    )

    # --- Derived slices --------------------------------------------------
    verify_after_days = (freshness or {}).get("rules", {}).get("verify_after_days", 7)
    verify_items = [
        b for b in (current_bp + recent_bp)
        if needs_verify(b, now, verify_after_days)
    ]
    near_today = [b for b in current_bp if b not in verify_items]
    this_week = [b for b in recent_bp if b not in verify_items]

    today_str = now.strftime("%Y-%m-%d")
    today_lifestate = next(
        (
            b for b in timeline_bp
            if str(b.get("dated") or "")[:10] == today_str
            and "life-state" in (b.get("tags") or [])
        ),
        None,
    )

    # --- Aged-out window -------------------------------------------------
    cutoff = now - timedelta(hours=aged_out_window_hours)
    aged_out = []
    for b in aged_out_all:
        ts = parse_iso(b.get("aged_out_at"))
        # Items missing aged_out_at still surface (operator hasn't migrated
        # yet); this matches how the lint will warn but not block.
        if ts is None or ts >= cutoff:
            aged_out.append(b)

    # --- Voice + routing -------------------------------------------------
    if voice_skin_override:
        voice = select_voice_rule(doctrine, renderer_id, skin_override=voice_skin_override)
        routing = None
    else:
        routing = select_routing_rule(doctrine, when=energy) if energy else None
        if routing and (routing.get("routing") or {}).get("narrator"):
            voice = select_voice_rule(
                doctrine, renderer_id,
                skin_override=routing["routing"]["narrator"],
            )
        else:
            voice = select_voice_rule(doctrine, renderer_id)

    return FactBundle(
        now=now,
        renderer_id=renderer_id,
        operator_root=operator_root,
        doctrine=doctrine,
        backpack=backpack,
        pinned_bp=pinned_bp,
        current_bp=current_bp,
        recent_bp=recent_bp,
        timeline_bp=timeline_bp,
        near_today=near_today,
        verify_items=verify_items,
        this_week=this_week,
        today_lifestate=today_lifestate,
        replaced=replaced,
        aged_out=aged_out,
        voice=voice,
        routing=routing,
        omitted_for_consent=omitted,
        gate_messages=gate_messages,
        gate_messages_short=short_gate,
        freshness_policy=freshness,
        backpack_total=len(backpack),
        replaced_total=len(replaced),
        aged_out_total=len(aged_out),
    )
