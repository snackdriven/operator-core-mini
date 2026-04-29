#!/usr/bin/env python3
"""
bootstrap_doctrine.py — write a starter doctrine/ tree under an operator root.

The Backpack migrator (`tools/migrate.py`) covers the carry-state, but the
renderers refuse to run without a `doctrine/` tree. Doctrine, by definition,
is operator-authored: it encodes who you are, how renderers should behave,
and what consent postures govern ingestion. This script does NOT try to
auto-extract doctrine from your CLAUDE.md (those files are too prose-shaped
to mine reliably). It writes the *minimum* schema-valid scaffolding so:

  - renderers run
  - the user has obvious files to hand-edit, with TODO markers in body text
  - voice/routing rules ship as working defaults (Good Place + Mass Effect
    skins, low/high energy routing) so narrator surfaces render out of the box

The nine seed entries this script writes are:

  identity/user-profile, default/writing-preferences,
  voice/voice-good-place, voice/voice-mass-effect,
  routing/narrator-low-energy, routing/narrator-high-energy,
  policy/consent-narrator-vault, policy/consent-health-private,
  policy/github-source-of-truth

Not every renderer reads every entry today — statusline, daily-brief, and
session-primer use only `identity/*` and `default/*`; the `voice/*` and
`routing/*` entries are consumed by `narrator_*` and the `policy/*` entries
are honored by ingestion adapters and the consent gate. They ship together
because hand-authoring them later (when an operator finally needs the
narrator skin or a consent posture) is more friction than ignoring nine
schema-clean files. Treat these as **seeds**, not active configuration: a
fresh operator-root after `bootstrap_doctrine.py` is renderable but not
yet personalized; hand-edit the body text + frontmatter to taste.

Usage:
    python tools/bootstrap_doctrine.py path/to/operator-root [--name "Kayla"]
                                        [--summary "QA at NHHA"]
                                        [--force]

Refuses to overwrite any existing doctrine file unless --force is passed.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from textwrap import dedent

try:
    import yaml  # PyYAML
except ImportError:  # pragma: no cover
    sys.exit("PyYAML required: pip install pyyaml")


class _LiteralBlockDumper(yaml.SafeDumper):
    """Multi-line strings as block literals; matches migrate.py output."""


def _str_representer(dumper, data):
    if "\n" in data:
        return dumper.represent_scalar("tag:yaml.org,2002:str", data, style="|")
    return dumper.represent_scalar("tag:yaml.org,2002:str", data)


_LiteralBlockDumper.add_representer(str, _str_representer)


def _dump_fm(item: dict) -> str:
    return yaml.dump(
        item,
        Dumper=_LiteralBlockDumper,
        sort_keys=False,
        allow_unicode=True,
        width=10**9,
        default_flow_style=False,
    ).strip()


def _write(path: Path, item: dict, *, force: bool) -> bool:
    """Write a doctrine markdown file. Returns True if written, False if skipped."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and not force:
        return False
    fm = _dump_fm(item)
    path.write_text(f"---\n{fm}\n---\n", encoding="utf-8")
    return True


# ---------------------------------------------------------------------------
# Doctrine stubs
# ---------------------------------------------------------------------------

def doctrine_entries(*, name: str, summary: str) -> list[tuple[str, dict]]:
    """
    Return (relative_path, frontmatter_dict) pairs for the bootstrap set.

    Schema reference: schemas/doctrine-entry.schema.json
    Required fields per kind:
      identity / default / workflow / evergreen-reference / vocabulary:
        id, kind, title, body
      voice-rule: + voice block
      routing-rule: + routing block
      policy: + (optional) consent block
    """
    entries: list[tuple[str, dict]] = []

    # --- identity ----------------------------------------------------------
    entries.append((
        "doctrine/identity/user-profile.md",
        {
            "id": "user-profile",
            "kind": "identity",
            "title": "User profile",
            "body": dedent(f"""\
                {name}. {summary}

                TODO: refine this from your CLAUDE.md / personal context.
                Rendered into every surface header. Keep it short.
                """).rstrip(),
            "pinned": True,
            "stability": "evolving",
            "tags": ["identity"],
            "applies_to": [
                "session-primer",
                "narrator-list",
                "narrator-brief",
                "daily-brief",
            ],
            "renderer_hints": {
                "surfaces": ["session-primer", "narrator"],
                "priority": 100,
                "requires_consent": False,
            },
        },
    ))

    # --- defaults ----------------------------------------------------------
    entries.append((
        "doctrine/default/writing-preferences.md",
        {
            "id": "writing-preferences",
            "kind": "default",
            "title": "Writing preferences",
            "body": dedent("""\
                Plain language. Dated entries. No exclamation points.
                Short paragraphs. Lists over prose when items are parallel.
                Markdown headers under six words.

                TODO: replace with the rules from your CLAUDE.md "Adapter
                Rules" / "Output rules" sections.
                """).rstrip(),
            "pinned": True,
            "stability": "evolving",
            "applies_to": [
                "narrator-list",
                "narrator-brief",
                "daily-brief",
                "session-primer",
            ],
        },
    ))

    # --- voice rules -------------------------------------------------------
    entries.append((
        "doctrine/voice/voice-good-place.md",
        {
            "id": "voice-good-place",
            "kind": "voice-rule",
            "title": "Good Place narrator skin",
            "body": dedent("""\
                Warm, low-demand register. Selected by default when no
                low-energy routing override has fired and writing-preferences
                allows neutral-warm tone.
                """).rstrip(),
            "pinned": True,
            "stability": "stable",
            "tags": ["voice", "narrator"],
            "voice": {
                "skin": "good-place",
                "scope": ["narrator-list", "narrator-brief"],
                "register": "warm",
                "do": [
                    "lead with a friendly orientation",
                    "name the smallest next step",
                    "prefer \"what's already in your bag\" framings",
                ],
                "avoid": [
                    "hustle vocabulary",
                    "ranked priority lists",
                    "exclamation points",
                ],
                "facts_stable": True,
            },
            "renderer_hints": {
                "surfaces": ["narrator-list", "narrator-brief"],
                "priority": 50,
            },
        },
    ))

    entries.append((
        "doctrine/voice/voice-mass-effect.md",
        {
            "id": "voice-mass-effect",
            "kind": "voice-rule",
            "title": "Mass Effect narrator skin",
            "body": dedent("""\
                Terse, mission-brief register. Available as an alternative
                narrator skin; selected via --skin or by routing rule, never
                by default.
                """).rstrip(),
            "pinned": False,
            "stability": "stable",
            "tags": ["voice", "narrator"],
            "voice": {
                "skin": "mass-effect",
                "scope": ["narrator-list", "narrator-brief"],
                "register": "terse",
                "do": [
                    "open with situation, then objective",
                    "state facts as bullets",
                    "close with the next decision point",
                ],
                "avoid": [
                    "softening hedges",
                    "meta-commentary",
                    "emoji",
                ],
                "facts_stable": True,
            },
            "renderer_hints": {
                "surfaces": ["narrator-list", "narrator-brief"],
                "priority": 30,
            },
        },
    ))

    # --- routing rules -----------------------------------------------------
    entries.append((
        "doctrine/routing/narrator-low-energy.md",
        {
            "id": "narrator-low-energy-routing",
            "kind": "routing-rule",
            "title": "Switch to terse narrator on low-energy days",
            "body": dedent("""\
                When the morning life-state token is `low-energy`, prefer a
                terser narrator skin so the brief is short and decision-led.
                """).rstrip(),
            "pinned": True,
            "stability": "evolving",
            "tags": ["routing", "narrator"],
            "routing": {
                "when": "low-energy",
                "prefer_renderer": "narrator-brief",
                "narrator": "mass-effect",
                "tone": "terse",
            },
        },
    ))

    entries.append((
        "doctrine/routing/narrator-high-energy.md",
        {
            "id": "narrator-high-energy-routing",
            "kind": "routing-rule",
            "title": "Stay warm on high-energy days",
            "body": dedent("""\
                When the morning life-state token is `high-energy`, keep the
                warm Good Place skin; no need to compress the brief.
                """).rstrip(),
            "pinned": True,
            "stability": "evolving",
            "tags": ["routing", "narrator"],
            "routing": {
                "when": "high-energy",
                "prefer_renderer": "narrator-list",
                "narrator": "good-place",
                "tone": "warm",
            },
        },
    ))

    # --- policies ----------------------------------------------------------
    entries.append((
        "doctrine/policy/consent-narrator-vault.md",
        {
            "id": "consent-narrator-vault",
            "kind": "policy",
            "title": "Narrator vault is opt-out at the file level",
            "body": dedent("""\
                Markdown files in the narrator vault are ingested by default.
                A file is excluded if it contains the frontmatter key
                'ingest: false' OR lives under a path matching
                narrator/_private/. Excluded files MUST emit no audit event
                referencing their path.
                """).rstrip(),
            "pinned": True,
            "stability": "stable",
            "tags": ["consent", "narrator"],
            "consent": {
                "scope": "narrator-vault",
                "posture": "opt-out",
                "applies_to_pathways": ["narrator-vault"],
                "requires": [
                    "honor 'ingest: false' frontmatter key",
                    "honor narrator/_private/ path prefix",
                ],
                "rationale": (
                    "The vault is dense; opt-in would require touching "
                    "hundreds of files."
                ),
            },
        },
    ))

    entries.append((
        "doctrine/policy/consent-health-private.md",
        {
            "id": "consent-health-private",
            "kind": "policy",
            "title": "Health-state items are forbidden on shared surfaces",
            "body": dedent("""\
                Items tagged or scoped 'health' are personal context. They
                MUST NOT surface on daily-brief or statusline; they MAY
                surface on session-primer / narrator surfaces only when
                renderer_hints.requires_consent is satisfied.
                """).rstrip(),
            "pinned": True,
            "stability": "stable",
            "tags": ["consent", "health"],
            "consent": {
                "scope": "health",
                "posture": "opt-in",
                "applies_to_renderers": ["daily-brief", "statusline"],
                "requires": [
                    "renderer_hints.requires_consent = true",
                    "operator-confirmed life-state token",
                ],
                "rationale": (
                    "Health information is personal; never include on shared "
                    "or ambient surfaces by default."
                ),
                "gate_message": (
                    "Held back {count} health-tagged items from this surface."
                ),
                "gate_message_short": "+{count} private",
            },
        },
    ))

    entries.append((
        "doctrine/policy/github-source-of-truth.md",
        {
            "id": "github-source-of-truth",
            "kind": "policy",
            "title": "GitHub is the source of truth",
            "body": dedent("""\
                When Backpack and a repo disagree about state, the repo wins.
                Update the Backpack item to match the repo, not the other way
                around.
                """).rstrip(),
            "pinned": True,
            "stability": "stable",
            "tags": ["policy", "github"],
        },
    ))

    return entries


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("operator_root", type=Path)
    p.add_argument(
        "--name",
        default="Operator",
        help="Display name for identity stub (default: Operator)",
    )
    p.add_argument(
        "--summary",
        default="TODO: short bio sentence.",
        help="One-line role summary for identity stub.",
    )
    p.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing doctrine files.",
    )
    args = p.parse_args(argv)

    root = args.operator_root
    if not root.exists():
        print(f"not found: {root}", file=sys.stderr)
        return 1

    written, skipped = [], []
    for rel, item in doctrine_entries(name=args.name, summary=args.summary):
        out = root / rel
        if _write(out, item, force=args.force):
            written.append(rel)
        else:
            skipped.append(rel)

    print(f"wrote {len(written)} doctrine entries under {root}")
    for rel in written:
        print(f"  + {rel}")
    if skipped:
        print(f"skipped {len(skipped)} (already exists; use --force to overwrite):")
        for rel in skipped:
            print(f"  - {rel}")
    print(
        "\nnext: hand-edit identity/user-profile.md and default/writing-preferences.md\n"
        "      to match your CLAUDE.md content. Then run a renderer to verify."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
