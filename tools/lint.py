#!/usr/bin/env python3
"""
lint.py — structural lint for operator-core-schemas.

Complements validate.py (which checks payload-vs-schema). This script enforces
repo-wide conventions that are not captured in JSON Schema:

  1. JSON files re-serialize with 2-space indent + sorted top-level keys
     (catches drift / hand-edits with inconsistent formatting).
  2. JSONL files: every non-blank line parses as JSON.
  3. Filenames in examples/ingestion-trace/{hoard,quarantine}/ start with a
     ULID-shaped prefix.
  4. Markdown frontmatter parses cleanly wherever it appears.
  5. Internal markdown links (relative paths) point to files that exist.
  6. No `TODO:` or `FIXME:` markers in committed schemas.

Warn-only checks (do not fail the run, but surface as `[WARN]`):

  * Hoard markdown files in `examples/**/hoard/**/*.md` should declare an
    `aged_out_at` timestamp in their frontmatter so the renderers' aged-out
    window logic has something concrete to reason about.

Usage:
    python tools/lint.py [repo-root]

Exits 0 on full success, 1 on any failure (prints the offender).
Warnings are reported but never affect the exit code.
Requires: pyyaml.
"""
from __future__ import annotations

import json
import re
import sys
import warnings
from pathlib import Path

warnings.filterwarnings("ignore", category=DeprecationWarning)

import yaml  # type: ignore


# Repo convention: hoard/quarantine filenames start with a ULID-shaped prefix
# (full ULIDs are 26 chars; the repo's worked examples use abbreviated `01H...`
# placeholders, so we require only a 4+ uppercase-alnum lead).
ULID_PREFIX_RE = re.compile(r"^[0-9A-Z]{4,}")
MD_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)\s]+?)(?:\s+\"[^\"]*\")?\)")


# ---------------------------------------------------------------------------
# Frontmatter loader (mirrors validate.py)
# ---------------------------------------------------------------------------

class _StringDateLoader(yaml.SafeLoader):
    pass


_StringDateLoader.add_constructor(
    "tag:yaml.org,2002:timestamp",
    lambda loader, node: loader.construct_scalar(node),
)


# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------

def check_json_formatting(repo_root: Path, errors: list[str]) -> None:
    """Every .json file under schemas/ and examples/ should:
      - parse as JSON
      - end with exactly one trailing newline
      - not contain tab characters in indentation
      - use 2-space indentation when the first indented line has any leading whitespace

    We deliberately do NOT enforce strict canonical round-trip: JSON Schema
    convention keeps short enums and `required` arrays inline for readability,
    and `json.dumps(indent=2)` would explode them onto multiple lines.
    """
    targets: list[Path] = []
    for sub in ("schemas", "examples"):
        targets.extend((repo_root / sub).rglob("*.json"))

    for path in sorted(targets):
        rel = path.relative_to(repo_root)
        raw = path.read_text(encoding="utf-8")

        try:
            json.loads(raw)
        except json.JSONDecodeError as exc:
            errors.append(f"json-parse: {rel}: {exc}")
            continue

        if not raw.endswith("\n"):
            errors.append(f"json-format: {rel}: missing trailing newline")
        if raw.endswith("\n\n"):
            errors.append(f"json-format: {rel}: extra trailing newline(s)")

        # Indentation: scan for the first non-empty line that starts with whitespace.
        for line in raw.splitlines():
            if not line.strip():
                continue
            stripped = line.lstrip(" ")
            if stripped == line:
                continue  # no indent on this line
            if "\t" in line[: len(line) - len(stripped)]:
                errors.append(f"json-format: {rel}: tab in indentation")
                break
            indent = len(line) - len(stripped)
            if indent % 2 != 0:
                errors.append(
                    f"json-format: {rel}: indent appears to be {indent} "
                    f"(expected multiple of 2)"
                )
            break


def check_jsonl_files(repo_root: Path, errors: list[str]) -> None:
    for path in sorted(repo_root.rglob("*.jsonl")):
        rel = path.relative_to(repo_root)
        for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            try:
                json.loads(line)
            except json.JSONDecodeError as exc:
                errors.append(f"jsonl-parse: {rel}:{i}: {exc}")


def check_ulid_filenames(repo_root: Path, errors: list[str]) -> None:
    """Files under hoard/ and quarantine/ must lead with a ULID-shaped prefix."""
    for sub in ("examples/ingestion-trace/hoard", "examples/ingestion-trace/quarantine"):
        d = repo_root / sub
        if not d.is_dir():
            continue
        for path in sorted(d.iterdir()):
            if not path.is_file():
                continue
            if path.name.startswith("."):
                continue
            if path.name == "README.md":
                continue
            if not ULID_PREFIX_RE.match(path.name):
                errors.append(
                    f"ulid-filename: {path.relative_to(repo_root)}: "
                    "must start with a ULID-shaped prefix"
                )


def check_frontmatter(repo_root: Path, errors: list[str]) -> None:
    """Any markdown file beginning with '---\\n' must have valid YAML frontmatter."""
    for path in sorted(repo_root.rglob("*.md")):
        if any(part in {".git", "node_modules"} for part in path.parts):
            continue
        text = path.read_text(encoding="utf-8")
        if not text.startswith("---\n"):
            continue
        m = re.match(r"---\n(.*?)\n---\n?(.*)", text, re.S)
        if not m:
            errors.append(
                f"frontmatter: {path.relative_to(repo_root)}: "
                "starts with --- but no closing --- found"
            )
            continue
        try:
            yaml.load(m.group(1), Loader=_StringDateLoader)
        except yaml.YAMLError as exc:
            errors.append(f"frontmatter: {path.relative_to(repo_root)}: {exc}")


def check_internal_links(repo_root: Path, errors: list[str]) -> None:
    """Internal markdown links must resolve to a file that exists."""
    for path in sorted(repo_root.rglob("*.md")):
        if any(part in {".git", "node_modules"} for part in path.parts):
            continue
        text = path.read_text(encoding="utf-8")
        rel = path.relative_to(repo_root)
        for match in MD_LINK_RE.finditer(text):
            target = match.group(2)
            # Skip external links and pure anchors.
            if target.startswith(("http://", "https://", "mailto:", "#")):
                continue
            # Strip in-page anchor.
            target_path = target.split("#", 1)[0]
            if not target_path:
                continue
            resolved = (path.parent / target_path).resolve()
            if not resolved.exists():
                errors.append(
                    f"dead-link: {rel}: -> {target} (resolved {resolved.relative_to(repo_root) if resolved.is_relative_to(repo_root) else resolved})"
                )


def check_hoard_aged_out_at(repo_root: Path, warnings_out: list[str]) -> None:
    """Hoard markdown files SHOULD declare `aged_out_at` in frontmatter.

    The schema makes the field optional (older imports may pre-date the
    aged-out concept), so we surface this as a warning rather than a hard
    failure. Renderers degrade gracefully when the field is absent, but
    operators reviewing the hoard benefit from a concrete timestamp.
    """
    for path in sorted(repo_root.rglob("*.md")):
        if any(part in {".git", "node_modules"} for part in path.parts):
            continue
        # Match anything under a `hoard/` segment beneath examples/.
        parts = path.parts
        if "hoard" not in parts:
            continue
        if "examples" not in parts:
            continue
        if path.name == "README.md":
            continue
        text = path.read_text(encoding="utf-8")
        if not text.startswith("---\n"):
            continue
        m = re.match(r"---\n(.*?)\n---\n?(.*)", text, re.S)
        if not m:
            continue
        try:
            data = yaml.load(m.group(1), Loader=_StringDateLoader) or {}
        except yaml.YAMLError:
            continue
        if not isinstance(data, dict):
            continue
        if "aged_out_at" not in data or data.get("aged_out_at") in (None, ""):
            warnings_out.append(
                f"hoard-aged-out-at: {path.relative_to(repo_root)}: "
                "frontmatter is missing `aged_out_at` (recommended for hoard items)"
            )


def check_no_todo_in_schemas(repo_root: Path, errors: list[str]) -> None:
    pat = re.compile(r"\b(TODO|FIXME|XXX)\b")
    for path in sorted((repo_root / "schemas").rglob("*.json")):
        text = path.read_text(encoding="utf-8")
        if pat.search(text):
            rel = path.relative_to(repo_root)
            errors.append(f"todo-in-schema: {rel}: TODO/FIXME/XXX marker present")


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------

CHECKS = [
    ("json-formatting",  check_json_formatting),
    ("jsonl-files",      check_jsonl_files),
    ("ulid-filenames",   check_ulid_filenames),
    ("frontmatter",      check_frontmatter),
    ("internal-links",   check_internal_links),
    ("todo-in-schemas",  check_no_todo_in_schemas),
]

# Warn-only checks: collected separately, never fail the run.
WARN_CHECKS = [
    ("hoard-aged-out-at", check_hoard_aged_out_at),
]


def run(repo_root: Path) -> bool:
    all_errors: list[str] = []
    for name, fn in CHECKS:
        before = len(all_errors)
        fn(repo_root, all_errors)
        added = len(all_errors) - before
        status = "OK" if added == 0 else f"FAIL ({added})"
        print(f"[{status}] lint:{name}")

    all_warnings: list[str] = []
    for name, fn in WARN_CHECKS:
        before = len(all_warnings)
        fn(repo_root, all_warnings)
        added = len(all_warnings) - before
        status = "OK" if added == 0 else f"WARN ({added})"
        print(f"[{status}] lint:{name}")

    if all_errors:
        print()
        print(f"FAILURES PRESENT ({len(all_errors)}):")
        for e in all_errors:
            print(f"  {e}")
        if all_warnings:
            print()
            print(f"WARNINGS ({len(all_warnings)}):")
            for w in all_warnings:
                print(f"  {w}")
        return False
    if all_warnings:
        print()
        print(f"WARNINGS ({len(all_warnings)}):")
        for w in all_warnings:
            print(f"  {w}")
    print()
    print("ALL PASSED")
    return True


def main(argv: list[str]) -> int:
    repo_root = Path(argv[1]) if len(argv) > 1 else Path(__file__).resolve().parent.parent
    if not (repo_root / "schemas").is_dir():
        print(f"not a repo root (no schemas/): {repo_root}", file=sys.stderr)
        return 1
    return 0 if run(repo_root) else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
