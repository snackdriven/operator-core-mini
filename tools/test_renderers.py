"""
test_renderers.py — golden output tests for renderers/.

Runs each renderer against examples/operator-root-fixture/ at a fixed
``--now`` and diffs the output against the committed ``expected-*`` file.
This is what catches accidental drift when someone refactors a renderer
or adds a Doctrine entry that changes selection.

Used standalone:

    python tools/test_renderers.py

Or imported and called from tools/validate.py.
"""
from __future__ import annotations

import difflib
import subprocess
import sys
from pathlib import Path

NOW = "2026-04-29T14:00:00Z"

CASES: list[tuple[str, list[str], str]] = [
    # (renderer module, extra args, expected file basename)
    ("renderers/session_primer.py", [], "expected-session-primer.md"),
    ("renderers/daily_brief.py", [], "expected-daily-brief.md"),
    ("renderers/statusline.py", [], "expected-statusline.txt"),
    # narrator-list — the template-driven structured surface (formerly
    # narrator-brief; renamed per ADR 0005 clarification 2026-04-29).
    ("renderers/narrator_list.py", [], "expected-narrator-list.md"),
    (
        "renderers/narrator_list.py",
        ["--skin", "mass-effect"],
        "expected-narrator-list.mass-effect.md",
    ),
    # narrator-brief — the prompt-driven surface; output is a deterministic
    # prompt artefact for an LLM (the LLM step is outside the renderer
    # boundary). The prompt itself is testable as a stable golden because
    # build_fact_bundle is deterministic for a fixed (operator_root, now).
    ("renderers/narrator_brief.py", [], "expected-narrator-brief.prompt.md"),
]


def run(repo_root: Path) -> bool:
    fixture = repo_root / "examples" / "operator-root-fixture"
    if not fixture.is_dir():
        print(f"[skip] no fixture at {fixture}")
        return True

    ok = True
    for renderer, extra, expected_name in CASES:
        cmd = [sys.executable, str(repo_root / renderer), str(fixture), "--now", NOW] + extra
        try:
            actual = subprocess.run(
                cmd, check=True, capture_output=True, text=True
            ).stdout
        except subprocess.CalledProcessError as exc:
            ok = False
            print(f"[FAIL] {renderer} {' '.join(extra)}: {exc.stderr.strip() or exc}")
            continue

        expected_path = fixture / expected_name
        if not expected_path.is_file():
            ok = False
            print(f"[FAIL] {renderer}: expected file missing: {expected_path.name}")
            continue
        expected = expected_path.read_text(encoding="utf-8")

        if actual == expected:
            print(f"[OK] renderer:{renderer} → {expected_name}")
            continue

        ok = False
        diff = "".join(
            difflib.unified_diff(
                expected.splitlines(keepends=True),
                actual.splitlines(keepends=True),
                fromfile=f"expected/{expected_name}",
                tofile=f"actual/{renderer}",
                n=2,
            )
        )
        print(f"[FAIL] renderer:{renderer} → {expected_name} (output drift)")
        print(diff)
    return ok


def main() -> int:
    repo_root = Path(__file__).resolve().parent.parent
    return 0 if run(repo_root) else 1


if __name__ == "__main__":
    raise SystemExit(main())
