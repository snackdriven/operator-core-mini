#!/usr/bin/env python3
"""
test_migrate.py — fixture-based tests for tools/migrate.py + migrate_hoard.py.

Covers the contract described by `tools/migrate.py`:

  1. Schema-clean output: every backpack/<sub>/*.md, every hoard/**/*.md,
     and policy/freshness.json validate against their declared schemas.
  2. 3-tier date mining: ``as of YYYY-MM-DD`` > id-encoded date >
     first-line date > last-in-body date > None.
  3. Legacy ``scope`` → schema ``area`` rename for already-structured items.
  4. TTL diversion (before/at/after expiry): backpack items whose
     ``_config:ttl[key].created_at + ttl_seconds <= now`` are written
     under hoard/, NOT backpack/, with ``aged_out_at`` stamped and
     ``freshness_class = historical``. Items not yet expired stay in
     backpack/ and pinned items are never diverted.
  5. ``--with-hoard`` walks dailies/YYYY-MM-DD/ + loose artifacts and
     writes one hoard entry per file with the right ``aged_out_at``.
  6. Id collisions are reported (FileExistsError) and don't crash the run.
  7. ``additionalProperties: false`` is honored — no leaked legacy
     fields like ``_meta``, ``title``, or ``scope``.

Wired into ``tools/validate.py`` so a single ``python tools/validate.py``
runs the schema suite, the lint suite, the renderer goldens, AND this
test file.
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

# Allow `python tools/test_migrate.py` to import sibling modules.
_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

import yaml  # type: ignore

from _migrate_common import extract_dated, slugify, write_frontmatter_md  # noqa: E402
from migrate import (  # noqa: E402
    _build_freshness_skeleton,
    _validate_freshness_skeleton,
    _ttl_eligible,
    freshness_dir,
    migrate,
    normalize_value,
)
from migrate_hoard import migrate_hoard  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

REPO_ROOT = _HERE.parent
NOW = datetime(2026, 4, 29, 20, 0, 0, tzinfo=timezone.utc)


def _load_fm(p: Path) -> dict:
    """Read `p` and return its YAML frontmatter as a dict."""
    text = p.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        raise AssertionError(f"missing frontmatter in {p}")
    _, fm_text, _body = text.split("---", 2)
    return yaml.safe_load(fm_text) or {}


def _validate_against(rel_schema: str, data: dict) -> list[str]:
    """Return a list of validation error messages for `data` vs `rel_schema`."""
    try:
        from jsonschema import Draft202012Validator, RefResolver  # type: ignore
    except ImportError:  # pragma: no cover
        return []
    schema_path = REPO_ROOT / rel_schema
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    # Resolve sibling $refs (e.g. renderer-hints.schema.json).
    store = {}
    for sib in (REPO_ROOT / "schemas").glob("*.schema.json"):
        s = json.loads(sib.read_text(encoding="utf-8"))
        if "$id" in s:
            store[s["$id"]] = s
            store[s["$id"].rsplit("/", 1)[-1]] = s
    resolver = RefResolver(
        base_uri=schema.get("$id", f"file:///{rel_schema}"),
        referrer=schema,
        store=store,
    )
    return [
        f"{'/'.join(map(str, e.absolute_path)) or '<root>'}: {e.message}"
        for e in Draft202012Validator(schema, resolver=resolver).iter_errors(data)
    ]


# ---------------------------------------------------------------------------
# Unit tests for pure helpers
# ---------------------------------------------------------------------------

class DateMiningTests(unittest.TestCase):
    """`extract_dated` priority order."""

    def test_as_of_wins_over_everything(self):
        # value contains both an as-of date and other dates; as-of wins.
        v = "as of 2026-04-29\nold reference 2026-01-01 here\n2025-12-31 trailing"
        self.assertEqual(extract_dated("plain-key", v), "2026-04-29")

    def test_id_date_beats_body_date(self):
        v = "no leading date\nbody mentions 2025-01-01"
        self.assertEqual(extract_dated("dsu-2026-04-07", v), "2026-04-07")

    def test_first_line_when_id_has_no_date(self):
        v = "2026-03-14 first-line date\nlater body 2025-12-25 here"
        self.assertEqual(extract_dated("plain-key", v), "2026-03-14")

    def test_last_body_date_when_first_line_undated(self):
        v = "no date in first line\n\nfinally 2026-02-15 mentioned\nthen 2026-04-01"
        self.assertEqual(extract_dated("plain-key", v), "2026-04-01")

    def test_returns_none_when_no_date(self):
        self.assertIsNone(extract_dated("plain-key", "no dates anywhere"))


class NormalizeValueTests(unittest.TestCase):
    """`normalize_value` schema-cleanliness + scope→area rename."""

    def test_legacy_scope_promoted_to_area(self):
        item = normalize_value(
            "structured-key",
            {"value": "x", "scope": "life", "freshness_class": "current"},
            now_iso="2026-04-29T20:00:00Z",
        )
        self.assertEqual(item.get("area"), "life")
        self.assertNotIn("scope", item)

    def test_unknown_scope_falls_back_to_work(self):
        item = normalize_value(
            "structured-key",
            {"value": "x", "scope": "unknown-bucket", "freshness_class": "current"},
            now_iso="2026-04-29T20:00:00Z",
        )
        self.assertEqual(item.get("area"), "work")

    def test_legacy_meta_and_title_stripped(self):
        item = normalize_value(
            "structured-key",
            {
                "value": "x",
                "_meta": {"who": "me"},
                "title": "old field",
                "freshness_class": "current",
            },
            now_iso="2026-04-29T20:00:00Z",
        )
        self.assertNotIn("_meta", item)
        self.assertNotIn("title", item)

    def test_undated_string_promoted_to_evergreen(self):
        item = normalize_value(
            "no-date-key", "no date in here at all",
            now_iso="2026-04-29T20:00:00Z",
        )
        self.assertEqual(item["freshness_class"], "evergreen")
        self.assertEqual(item["memory_class"], "evergreen-reference")
        self.assertNotIn("dated", item)

    def test_dated_string_gets_dated_and_summary(self):
        v = "Q2 roadmap notes — 2026-04-29: scope locked, NHHA RCM moves to June"
        item = normalize_value("q2-roadmap", v, now_iso="2026-04-29T20:00:00Z")
        self.assertEqual(item["dated"], "2026-04-29")
        self.assertEqual(item["created_at"], "2026-04-29T12:00:00Z")
        self.assertIn("summary", item)
        self.assertEqual(item["freshness_class"], "current")


class FreshnessDirTests(unittest.TestCase):
    """`freshness_dir` mapping logic."""

    def test_evergreen_reference_routes_to_evergreen(self):
        self.assertEqual(
            freshness_dir({"freshness_class": "current",
                           "memory_class": "evergreen-reference"}),
            "evergreen",
        )

    def test_pinned_doctrine_routes_to_pinned(self):
        self.assertEqual(
            freshness_dir({"freshness_class": "current",
                           "memory_class": "pinned-doctrine"}),
            "pinned",
        )

    def test_removed_routes_to_replaced(self):
        self.assertEqual(freshness_dir({"freshness_class": "removed"}), "_replaced")

    def test_default_is_current(self):
        self.assertEqual(freshness_dir({"freshness_class": "current"}), "current")
        self.assertEqual(freshness_dir({"freshness_class": "recent"}), "current")
        self.assertEqual(freshness_dir({"freshness_class": "contextual"}), "current")
        self.assertEqual(freshness_dir({"freshness_class": "historical"}), "current")


class TtlEligibleTests(unittest.TestCase):
    """`_ttl_eligible` boundary behavior."""

    def test_before_expiry_not_eligible(self):
        # 1-day TTL, item created 12h ago at NOW.
        ttl = {"created_at": "2026-04-29T08:00:00Z", "ttl_seconds": 86400}
        eligible, _ = _ttl_eligible(ttl, NOW)
        self.assertFalse(eligible)

    def test_at_expiry_is_eligible(self):
        # ttl elapses exactly at NOW.
        ttl = {"created_at": "2026-04-28T20:00:00Z", "ttl_seconds": 86400}
        eligible, expires = _ttl_eligible(ttl, NOW)
        self.assertTrue(eligible)
        self.assertEqual(expires, "2026-04-29T20:00:00Z")

    def test_past_expiry_eligible(self):
        ttl = {"created_at": "2026-04-01T00:00:00Z", "ttl_seconds": 86400}
        eligible, expires = _ttl_eligible(ttl, NOW)
        self.assertTrue(eligible)
        self.assertEqual(expires, "2026-04-02T00:00:00Z")

    def test_missing_fields_returns_false(self):
        self.assertEqual(_ttl_eligible({}, NOW), (False, None))
        self.assertEqual(
            _ttl_eligible({"created_at": "bogus", "ttl_seconds": 1}, NOW),
            (False, None),
        )


class FreshnessSkeletonTests(unittest.TestCase):
    """The skeleton migrate.py emits must validate against its schema."""

    def test_skeleton_is_schema_clean(self):
        skel = _build_freshness_skeleton({}, [], now_iso="2026-04-29T20:00:00Z")
        errs = _validate_against("schemas/freshness-policy.schema.json", skel)
        self.assertEqual(errs, [], msg="skeleton should validate cleanly")

    def test_post_write_assertion_does_not_raise(self):
        skel = _build_freshness_skeleton({}, [], now_iso="2026-04-29T20:00:00Z")
        # Must not raise on a clean skeleton.
        _validate_freshness_skeleton(skel)

    def test_post_write_assertion_raises_on_garbage(self):
        with self.assertRaises(RuntimeError):
            _validate_freshness_skeleton({"version": "not-a-semver"})


# ---------------------------------------------------------------------------
# End-to-end migrate() against synthetic backpack.json
# ---------------------------------------------------------------------------

class MigrateEndToEndTests(unittest.TestCase):
    """Drive `migrate()` against a synthetic legacy file in a tempdir."""

    def _legacy(self) -> dict:
        # 6 items: 2 dated raw strings, 1 structured-with-scope, 1 undated raw,
        # 1 expired-via-ttl, 1 pinned-and-expired (must not divert).
        return {
            "_config:pinned_keys": ["pinned-and-expired", "writing-preferences"],
            "_config:ttl": {
                "expired-tactical": {
                    "created_at": "2026-01-01T00:00:00Z",
                    "ttl_seconds": 86400,  # 1d, long past
                },
                "fresh-tactical": {
                    "created_at": "2026-04-29T08:00:00Z",
                    "ttl_seconds": 86400,  # 12h ago, still alive
                },
                "pinned-and-expired": {
                    "created_at": "2026-01-01T00:00:00Z",
                    "ttl_seconds": 86400,  # expired, but pinned
                },
            },
            # Dated raw string with id-encoded date.
            "dsu-2026-04-07": "DSU notes — 2026-04-07: standup updates here",
            # Structured legacy item with `scope`.
            "writing-preferences": {
                "value": "Bullet points only. No fluff.",
                "freshness_class": "evergreen",
                "scope": "assistant",
                "_meta": {"legacy": True},
            },
            # Undated raw string → evergreen.
            "naming-quirk": "JIRA OLD-PROJECT-KEY actually means TTOAD now",
            # TTL-expired tactical.
            "expired-tactical": "expired tactical 2026-01-01: snapshot to drop",
            # TTL still alive.
            "fresh-tactical": "fresh tactical as of 2026-04-29: keep",
            # Pinned and expired — pinning wins, must remain in backpack/.
            "pinned-and-expired": "Pinned doctrine that long out-lasted its TTL",
        }

    def test_full_migration_is_schema_clean(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            legacy_path = td / "backpack.json"
            legacy_path.write_text(json.dumps(self._legacy()), encoding="utf-8")
            out_root = td / "operator-root"

            result = migrate(legacy_path, out_root, scratch_root=None, now=NOW)

            # 1. TTL diversion: expired-tactical was diverted, pinned-and-expired wasn't.
            self.assertIn("expired-tactical", result["aged_out_via_ttl"])
            self.assertNotIn("pinned-and-expired", result["aged_out_via_ttl"])
            self.assertNotIn("fresh-tactical", result["aged_out_via_ttl"])

            # 2. expired-tactical is at hoard/2026/01/01/expired-tactical.md
            #    (dated mined from "2026-01-01" inside the value).
            expired_md = out_root / "hoard" / "2026" / "01" / "01" / "expired-tactical.md"
            self.assertTrue(expired_md.exists(), msg=f"expected {expired_md}")
            fm = _load_fm(expired_md)
            self.assertEqual(fm["freshness_class"], "historical")
            self.assertEqual(fm["memory_class"], "timeline")
            self.assertEqual(fm["aged_out_at"], "2026-01-02T00:00:00Z")

            # 3. fresh-tactical stayed in backpack/current/.
            fresh_md = out_root / "backpack" / "current" / "fresh-tactical.md"
            self.assertTrue(fresh_md.exists())
            self.assertNotIn("aged_out_at", _load_fm(fresh_md))

            # 4. pinned-and-expired stayed under backpack/ (not hoard/).
            #    The exact subdirectory depends on its freshness_class:
            #    `pinned` for non-evergreen items, `evergreen` for items
            #    promoted to evergreen because they had no extractable date.
            pinned_candidates = [
                out_root / "backpack" / "pinned" / "pinned-and-expired.md",
                out_root / "backpack" / "evergreen" / "pinned-and-expired.md",
            ]
            self.assertTrue(
                any(p.exists() for p in pinned_candidates),
                msg=f"expected one of {pinned_candidates}",
            )
            # And it must NOT be under hoard/.
            self.assertEqual(
                list((out_root / "hoard").rglob("pinned-and-expired.md")),
                [],
                msg="pinned-and-expired must not divert to hoard/",
            )

            # 5. writing-preferences had scope→area rename.
            wp_md = out_root / "backpack" / "evergreen" / "writing-preferences.md"
            self.assertTrue(wp_md.exists())
            wp_fm = _load_fm(wp_md)
            self.assertEqual(wp_fm["area"], "assistant")
            self.assertNotIn("scope", wp_fm)
            self.assertNotIn("_meta", wp_fm)

            # 6. naming-quirk had no date → evergreen reference.
            nq_md = out_root / "backpack" / "evergreen" / "naming-quirk.md"
            self.assertTrue(nq_md.exists())
            nq_fm = _load_fm(nq_md)
            self.assertEqual(nq_fm["memory_class"], "evergreen-reference")

            # 7. Every backpack + hoard md validates against backpack-item schema.
            for md in (out_root / "backpack").rglob("*.md"):
                errs = _validate_against("schemas/backpack-item.schema.json", _load_fm(md))
                self.assertEqual(errs, [], msg=f"{md}: {errs}")
            for md in (out_root / "hoard").rglob("*.md"):
                errs = _validate_against("schemas/backpack-item.schema.json", _load_fm(md))
                self.assertEqual(errs, [], msg=f"{md}: {errs}")

            # 8. policy/freshness.json validates.
            policy = json.loads((out_root / "policy" / "freshness.json").read_text(encoding="utf-8"))
            errs = _validate_against("schemas/freshness-policy.schema.json", policy)
            self.assertEqual(errs, [], msg=f"policy: {errs}")


class WithHoardEndToEndTests(unittest.TestCase):
    """`--with-hoard` walks dailies + loose artifacts."""

    def _setup_scratch(self, root: Path) -> None:
        # backpack.json with one entry so migrate() runs cleanly.
        (root / "backpack.json").write_text(
            json.dumps({"a-thing-2026-04-29": "a thing — 2026-04-29: it happened"}),
            encoding="utf-8",
        )
        # dailies/2026-04-07/<two files>
        d = root / "dailies" / "2026-04-07"
        d.mkdir(parents=True)
        (d / "scratch.md").write_text("hi", encoding="utf-8")
        (d / "report.html").write_text("<html/>", encoding="utf-8")
        # loose artifact at root.
        (root / "weekly-2026-04-15.html").write_text("<html/>", encoding="utf-8")

    def test_with_hoard_writes_dailies_and_loose(self):
        with tempfile.TemporaryDirectory() as td:
            scratch = Path(td) / "scratch"
            scratch.mkdir()
            self._setup_scratch(scratch)
            out_root = Path(td) / "operator-root"

            result = migrate(
                scratch / "backpack.json",
                out_root,
                scratch_root=scratch,
                now=NOW,
            )
            self.assertEqual(result["hoard_stats"]["dailies"], 2)
            self.assertEqual(result["hoard_stats"]["loose"], 1)
            # Dailies aged_out_at is the date's 23:59:59Z.
            day_dir = out_root / "hoard" / "2026" / "04" / "07"
            self.assertTrue(day_dir.is_dir())
            for md in day_dir.iterdir():
                fm = _load_fm(md)
                self.assertEqual(fm["aged_out_at"], "2026-04-07T23:59:59Z")
                self.assertEqual(fm["dated"], "2026-04-07")
                self.assertEqual(fm["memory_class"], "timeline")
            # Loose dated 2026-04-15 sits at hoard/2026/04/15/.
            self.assertTrue((out_root / "hoard" / "2026" / "04" / "15").is_dir())

    def test_id_collisions_are_reported_not_crashing(self):
        with tempfile.TemporaryDirectory() as td:
            scratch = Path(td) / "scratch"
            (scratch / "dailies" / "2026-04-07").mkdir(parents=True)
            # Pre-create the target hoard file so the second write raises.
            out_root = Path(td) / "operator-root"
            (scratch / "backpack.json").write_text("{}", encoding="utf-8")
            # One file in dailies — the migrator will try to write its hoard entry.
            (scratch / "dailies" / "2026-04-07" / "note.md").write_text("x", encoding="utf-8")
            # Pre-create the exact path the migrator would write.
            from migrate_hoard import hoard_entry_for_file, hoard_path_for
            entry = hoard_entry_for_file(
                scratch / "dailies" / "2026-04-07" / "note.md",
                dated="2026-04-07",
                aged_out_at="2026-04-07T23:59:59Z",
                source_ref="dailies/2026-04-07/note.md",
            )
            collision = hoard_path_for(out_root, "2026-04-07", entry["id"])
            collision.parent.mkdir(parents=True, exist_ok=True)
            collision.write_text("placeholder", encoding="utf-8")

            result = migrate(
                scratch / "backpack.json",
                out_root,
                scratch_root=scratch,
                now=NOW,
            )
            # Collision was reported via skipped (under "hoard" key).
            self.assertTrue(any(k == "hoard" for k, _ in result["skipped"]),
                            msg=f"expected hoard collision in skipped: {result['skipped']}")


# ---------------------------------------------------------------------------
# Test-runner adapter for tools/validate.py
# ---------------------------------------------------------------------------

def run(repo_root: Path | None = None) -> bool:  # noqa: ARG001
    """Entry point used by tools/validate.py."""
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromModule(sys.modules[__name__])
    runner = unittest.TextTestRunner(stream=sys.stdout, verbosity=1)
    print()
    print("[migrate-tests] running…")
    result = runner.run(suite)
    ok = result.wasSuccessful()
    if ok:
        print(f"[OK] migrate-tests ({result.testsRun} tests passed)")
    else:
        print(f"[FAIL] migrate-tests ({len(result.failures)} fail, {len(result.errors)} err)")
    return ok


if __name__ == "__main__":
    sys.exit(0 if run() else 1)
