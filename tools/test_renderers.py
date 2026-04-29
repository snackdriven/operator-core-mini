"""
test_renderers.py — golden output tests for renderers/.

Runs each renderer against examples/operator-root-fixture/ at a fixed
``--now`` and diffs the output against the committed ``expected-*`` file.
This is what catches accidental drift when someone refactors a renderer
or adds a Doctrine entry that changes selection.

Two-tier goldens (per PLAN-followups-2026-04-29.md catch-alls):

  * **Snapshot tier** — full-text byte equality vs ``expected-*``. This is
    the historical check; deterministic renderers (session-primer,
    daily-brief, statusline, narrator-brief prompt) MUST match
    byte-for-byte. The narrator-list snapshot is treated as
    *advisory* — a diff surfaces but does not fail the run when the
    structural tier still matches. Rationale: a voice-rule wording
    edit (e.g. swapping a word in a do-rule) shouldn't redline the
    suite if the fact set and section ordering are unchanged.
  * **Structural tier** — for voice-aware surfaces, extract a
    fingerprint of (a) the ordered list of ``##`` section headers and
    (b) the set of bolded fact ids referenced (``**<id>**``). The
    structural fingerprint MUST match between actual + expected;
    moving a section or dropping a fact id is a real regression.

Used standalone:

    python tools/test_renderers.py

Or imported and called from tools/validate.py.
"""
from __future__ import annotations

import difflib
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

NOW = "2026-04-29T14:00:00Z"


@dataclass(frozen=True)
class Case:
    renderer: str
    extra: list[str]
    expected: str
    # voice_aware surfaces use the two-tier check: structural MUST match,
    # snapshot diffs are advisory. Deterministic surfaces use single-tier
    # (snapshot must match byte-for-byte).
    voice_aware: bool = False


CASES: list[Case] = [
    Case("renderers/session_primer.py", [], "expected-session-primer.md"),
    Case("renderers/daily_brief.py",    [], "expected-daily-brief.md"),
    Case("renderers/statusline.py",     [], "expected-statusline.txt"),
    # narrator-list — the template-driven structured surface (formerly
    # narrator-brief; renamed per ADR 0005 clarification 2026-04-29).
    # Voice-aware: a do-rule wording edit should NOT redline the suite
    # if the fact set + section ordering are unchanged.
    Case("renderers/narrator_list.py",  [], "expected-narrator-list.md", voice_aware=True),
    Case(
        "renderers/narrator_list.py",
        ["--skin", "mass-effect"],
        "expected-narrator-list.mass-effect.md",
        voice_aware=True,
    ),
    # narrator-brief — the prompt-driven surface; output is a deterministic
    # prompt artefact for an LLM (the LLM step is outside the renderer
    # boundary). The prompt itself is testable as a stable golden because
    # build_fact_bundle is deterministic for a fixed (operator_root, now).
    Case("renderers/narrator_brief.py", [], "expected-narrator-brief.prompt.md"),
    # Energy-routing regression: when --energy is passed, the renderer must
    # consult routing-rules in Doctrine and (for low-energy) flip the active
    # voice rule from `good-place` to `mass-effect`. The fixture ships two
    # routing-rules (low-energy + high-energy) so the selector has more than
    # one entry to disambiguate by `routing.when`. ADR 0005 follow-up.
    Case(
        "renderers/narrator_brief.py",
        ["--energy", "low-energy"],
        "expected-narrator-brief.low-energy.prompt.md",
    ),
]


# ---------------------------------------------------------------------------
# Structural fingerprint
# ---------------------------------------------------------------------------

_HEADER_RE = re.compile(r"^(#{1,6})\s+(.*?)\s*$", re.M)
_BOLD_ID_RE = re.compile(r"\*\*([a-z0-9][a-z0-9._\-]*)\*\*")


@dataclass(frozen=True)
class Fingerprint:
    """Structural fingerprint of a renderer's output.

    ``sections`` preserves order and depth so a section move is a
    regression, not a no-op. ``ids`` is the *set* of bolded fact ids
    referenced anywhere in the body — order doesn't matter, but the
    set membership is what guarantees facts-stable / framing-adapts.
    """
    sections: tuple[tuple[int, str], ...]
    ids: frozenset[str]


def fingerprint(text: str) -> Fingerprint:
    sections = tuple(
        (len(m.group(1)), m.group(2)) for m in _HEADER_RE.finditer(text)
    )
    # Bolded fact ids look like '**q2-roadmap-sync-2026-04-29**'. We only
    # capture ones that look like ids (lowercase, dotted/dashed/digits) so
    # we don't pick up regular bold-for-emphasis text.
    ids = frozenset(_BOLD_ID_RE.findall(text))
    return Fingerprint(sections=sections, ids=ids)


def _fp_diff(a: Fingerprint, b: Fingerprint) -> str:
    """Human-readable diff of two fingerprints; empty string if equal."""
    parts: list[str] = []
    if a.sections != b.sections:
        parts.append("section order/text differs:")
        for line in difflib.unified_diff(
            [f"{'#'*d} {h}" for d, h in a.sections],
            [f"{'#'*d} {h}" for d, h in b.sections],
            fromfile="expected/sections",
            tofile="actual/sections",
            n=1,
            lineterm="",
        ):
            parts.append(f"  {line}")
    only_expected = a.ids - b.ids
    only_actual = b.ids - a.ids
    if only_expected:
        parts.append(f"fact ids missing from actual: {sorted(only_expected)}")
    if only_actual:
        parts.append(f"fact ids appearing only in actual: {sorted(only_actual)}")
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------

def run(repo_root: Path) -> bool:
    fixture = repo_root / "examples" / "operator-root-fixture"
    if not fixture.is_dir():
        print(f"[skip] no fixture at {fixture}")
        return True

    ok = True
    for case in CASES:
        cmd = [sys.executable, str(repo_root / case.renderer), str(fixture), "--now", NOW] + case.extra
        try:
            actual = subprocess.run(
                cmd, check=True, capture_output=True, text=True
            ).stdout
        except subprocess.CalledProcessError as exc:
            ok = False
            print(f"[FAIL] {case.renderer} {' '.join(case.extra)}: {exc.stderr.strip() or exc}")
            continue

        # Normalize the operator_root path in the output for cross-platform golden tests
        actual = actual.replace(str(fixture), "/home/user/workspace/operator-core-schemas/examples/operator-root-fixture")
        # Handle posix path separators just in case (e.g. if str(fixture) uses \ but output uses /)
        actual = actual.replace(str(fixture).replace('\\', '/'), "/home/user/workspace/operator-core-schemas/examples/operator-root-fixture")

        expected_path = fixture / case.expected
        if not expected_path.is_file():
            ok = False
            print(f"[FAIL] {case.renderer}: expected file missing: {expected_path.name}")
            continue
        expected = expected_path.read_text(encoding="utf-8")

        snapshot_match = actual == expected

        if not case.voice_aware:
            # Deterministic surface — snapshot must match byte-for-byte.
            if snapshot_match:
                print(f"[OK] renderer:{case.renderer} -> {case.expected}")
                continue
            ok = False
            diff = "".join(
                difflib.unified_diff(
                    expected.splitlines(keepends=True),
                    actual.splitlines(keepends=True),
                    fromfile=f"expected/{case.expected}",
                    tofile=f"actual/{case.renderer}",
                    n=2,
                )
            )
            print(f"[FAIL] renderer:{case.renderer} -> {case.expected} (output drift)")
            print(diff)
            continue

        # Voice-aware surface — two-tier check.
        fp_expected = fingerprint(expected)
        fp_actual = fingerprint(actual)
        structural_match = fp_expected == fp_actual

        if structural_match and snapshot_match:
            print(f"[OK] renderer:{case.renderer} -> {case.expected}")
            continue

        if structural_match and not snapshot_match:
            # Advisory: framing changed but the fact set + section ordering
            # are unchanged. Surface the diff but don't fail the run.
            diff = "".join(
                difflib.unified_diff(
                    expected.splitlines(keepends=True),
                    actual.splitlines(keepends=True),
                    fromfile=f"expected/{case.expected}",
                    tofile=f"actual/{case.renderer}",
                    n=2,
                )
            )
            print(
                f"[ADVISORY] renderer:{case.renderer} -> {case.expected} "
                f"(snapshot drift; structural fingerprint unchanged)"
            )
            print(diff)
            continue

        # Structural drift — real regression.
        ok = False
        print(
            f"[FAIL] renderer:{case.renderer} -> {case.expected} "
            f"(structural drift)"
        )
        fp_msg = _fp_diff(fp_expected, fp_actual)
        if fp_msg:
            for line in fp_msg.splitlines():
                print(f"  {line}")
        if not snapshot_match:
            diff = "".join(
                difflib.unified_diff(
                    expected.splitlines(keepends=True),
                    actual.splitlines(keepends=True),
                    fromfile=f"expected/{case.expected}",
                    tofile=f"actual/{case.renderer}",
                    n=2,
                )
            )
            print(diff)
    return ok


def main() -> int:
    repo_root = Path(__file__).resolve().parent.parent
    return 0 if run(repo_root) else 1


if __name__ == "__main__":
    raise SystemExit(main())
