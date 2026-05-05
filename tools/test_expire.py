#!/usr/bin/env python3
"""
test_expire.py — fixture-based tests for tools/expire.py + tools/substrate.py.

Covers the daemon's contract:

  1. Items with no ``ttl_seconds`` are kept (no lease, no expiry).
  2. Items where ``created_at + ttl_seconds < now`` are demoted to
     ``hoard/YYYY/MM/DD/<basename>`` with ``aged_out_at`` stamped.
  3. Pinned items (``freshness_class: pinned``) are never demoted, even
     if their lease has expired.
  4. Items in ``backpack/_replaced/`` are skipped (out-of-band).
  5. ``--dry-run`` makes no filesystem changes.
  6. The daemon is idempotent — running it twice in a row demotes
     nothing on the second pass.
  7. Hoard write-once: an existing aged_out_at on a hoard item is not
     touched (the daemon only walks backpack/).
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

THIS = Path(__file__).resolve().parent
REPO = THIS.parent
sys.path.insert(0, str(THIS))

from substrate import (  # noqa: E402
    is_expired,
    join_frontmatter,
    split_frontmatter,
)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def write_item(
    path: Path,
    *,
    item_id: str,
    created_at: str | None,
    ttl_seconds: int | None,
    pinned: bool = False,
    summary: str = "test",
):
    """Write one schema-shaped backpack item."""
    fm: dict = {
        "id": item_id,
        "freshness_class": "pinned" if pinned else "current",
        "memory_class": "expiring-tactical",
        "area": "work",
        "source": {"kind": "manual", "ref": "test"},
        "dated": "2026-04-29",
        "tags": ["test"],
        "summary": summary,
    }
    if created_at is not None:
        fm["created_at"] = created_at
    if ttl_seconds is not None:
        fm["ttl_seconds"] = ttl_seconds
    body = f"2026-04-29 — {summary}\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(join_frontmatter(fm, body), encoding="utf-8")


def run_expire(operator_root: Path, *, now: str, dry_run: bool = False) -> tuple[int, str, str]:
    """Subprocess the CLI so we exercise the same path cron / weaver would."""
    args = [sys.executable, str(THIS / "expire.py"), str(operator_root), "--now", now]
    if dry_run:
        args.append("--dry-run")
    proc = subprocess.run(args, capture_output=True, text=True)
    return proc.returncode, proc.stdout, proc.stderr


# ---------------------------------------------------------------------------
# is_expired (unit)
# ---------------------------------------------------------------------------

class IsExpiredTests(unittest.TestCase):
    def setUp(self) -> None:
        self.now = datetime(2026, 5, 1, 12, 0, tzinfo=timezone.utc)

    def test_no_ttl_never_expires(self):
        self.assertFalse(is_expired({"created_at": "2024-01-01T00:00:00Z"}, now=self.now))

    def test_no_created_at_never_expires(self):
        self.assertFalse(is_expired({"ttl_seconds": 60}, now=self.now))

    def test_within_lease_not_expired(self):
        ca = (self.now - timedelta(seconds=30)).strftime("%Y-%m-%dT%H:%M:%SZ")
        self.assertFalse(is_expired({"created_at": ca, "ttl_seconds": 60}, now=self.now))

    def test_past_lease_is_expired(self):
        ca = (self.now - timedelta(seconds=120)).strftime("%Y-%m-%dT%H:%M:%SZ")
        self.assertTrue(is_expired({"created_at": ca, "ttl_seconds": 60}, now=self.now))

    def test_naive_datetime_treated_as_utc(self):
        ca = (self.now - timedelta(seconds=120)).strftime("%Y-%m-%dT%H:%M:%S")  # no Z
        self.assertTrue(is_expired({"created_at": ca, "ttl_seconds": 60}, now=self.now))

    def test_garbage_created_at_does_not_explode(self):
        self.assertFalse(is_expired({"created_at": "yesterday", "ttl_seconds": 60}, now=self.now))


# ---------------------------------------------------------------------------
# Daemon end-to-end
# ---------------------------------------------------------------------------

class ExpireE2ETests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="expire-test-"))
        self.now_iso = "2026-05-01T12:00:00Z"
        self.now_dt = datetime.fromisoformat("2026-05-01T12:00:00+00:00")

        # Three current items:
        #   * fresh-item: TTL 7d, created 1h ago (kept)
        #   * stale-item: TTL 1d, created 8d ago (demoted)
        #   * pinned-stale: TTL 1d, created 8d ago, but pinned (kept)
        # Two edge cases:
        #   * no-ttl: evergreen, no ttl_seconds (kept)
        #   * already-expired: TTL 0 with old created_at (demoted)
        # And one excluded:
        #   * _replaced/old-item: in backpack/_replaced/, never demoted
        old = (self.now_dt - timedelta(days=8)).strftime("%Y-%m-%dT%H:%M:%SZ")
        recent = (self.now_dt - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ")

        write_item(
            self.tmp / "backpack" / "current" / "fresh-item.md",
            item_id="fresh-item",
            created_at=recent,
            ttl_seconds=7 * 86400,
        )
        write_item(
            self.tmp / "backpack" / "current" / "stale-item.md",
            item_id="stale-item",
            created_at=old,
            ttl_seconds=86400,
        )
        write_item(
            self.tmp / "backpack" / "current" / "pinned-stale.md",
            item_id="pinned-stale",
            created_at=old,
            ttl_seconds=86400,
            pinned=True,
        )
        write_item(
            self.tmp / "backpack" / "current" / "no-ttl.md",
            item_id="no-ttl",
            created_at=old,
            ttl_seconds=None,  # evergreen-style: no lease
        )
        write_item(
            self.tmp / "backpack" / "current" / "already-expired.md",
            item_id="already-expired",
            created_at=old,
            ttl_seconds=0,  # expires immediately; created 8d ago
        )
        write_item(
            self.tmp / "backpack" / "_replaced" / "old-item.md",
            item_id="old-item",
            created_at=old,
            ttl_seconds=86400,
        )

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp)

    # -- assertions --------------------------------------------------------

    def assert_in_backpack(self, item_id: str):
        for p in (self.tmp / "backpack").rglob("*.md"):
            fm, _ = split_frontmatter(p.read_text(encoding="utf-8"))
            if fm.get("id") == item_id:
                return p
        self.fail(f"{item_id} not in backpack/")

    def assert_in_hoard(self, item_id: str):
        for p in (self.tmp / "hoard").rglob("*.md"):
            fm, _ = split_frontmatter(p.read_text(encoding="utf-8"))
            if fm.get("id") == item_id:
                return p, fm
        self.fail(f"{item_id} not in hoard/")

    def assert_not_in_hoard(self, item_id: str):
        if not (self.tmp / "hoard").is_dir():
            return
        for p in (self.tmp / "hoard").rglob("*.md"):
            fm, _ = split_frontmatter(p.read_text(encoding="utf-8"))
            if fm.get("id") == item_id:
                self.fail(f"{item_id} unexpectedly in hoard at {p.relative_to(self.tmp)}")

    # -- tests -------------------------------------------------------------

    def test_dry_run_makes_no_changes(self):
        rc, stdout, stderr = run_expire(self.tmp, now=self.now_iso, dry_run=True)
        self.assertEqual(rc, 0, msg=f"stdout={stdout!r} stderr={stderr!r}")
        self.assertIn("would", stdout)
        # filesystem unchanged
        self.assert_in_backpack("stale-item")
        self.assert_not_in_hoard("stale-item")
        self.assert_in_backpack("already-expired")
        self.assert_not_in_hoard("already-expired")

    def test_demotes_only_expired_unpinned(self):
        rc, stdout, stderr = run_expire(self.tmp, now=self.now_iso)
        self.assertEqual(rc, 0, msg=f"stdout={stdout!r} stderr={stderr!r}")

        # demoted
        _, fm_stale = self.assert_in_hoard("stale-item")
        self.assertEqual(fm_stale.get("aged_out_at"), self.now_iso)
        _, fm_zero = self.assert_in_hoard("already-expired")
        self.assertEqual(fm_zero.get("aged_out_at"), self.now_iso)

        # kept in backpack
        self.assert_in_backpack("fresh-item")
        self.assert_in_backpack("pinned-stale")
        self.assert_in_backpack("no-ttl")

        # _replaced never moves
        self.assertTrue((self.tmp / "backpack" / "_replaced" / "old-item.md").exists())
        self.assert_not_in_hoard("old-item")

    def test_hoard_path_is_year_month_day(self):
        run_expire(self.tmp, now=self.now_iso)
        target = self.tmp / "hoard" / "2026" / "05" / "01" / "stale-item.md"
        self.assertTrue(target.is_file(), msg=f"expected {target}")

    def test_idempotent(self):
        rc1, stdout1, _ = run_expire(self.tmp, now=self.now_iso)
        self.assertEqual(rc1, 0)
        self.assertIn("demote ", stdout1)

        rc2, stdout2, _ = run_expire(self.tmp, now=self.now_iso)
        self.assertEqual(rc2, 0)
        # second run finds nothing to do
        self.assertNotIn("demote ", stdout2)

    def test_pinned_stale_never_demotes(self):
        run_expire(self.tmp, now=self.now_iso)
        self.assert_in_backpack("pinned-stale")
        self.assert_not_in_hoard("pinned-stale")

    def test_summary_count_in_stderr(self):
        _, _, stderr = run_expire(self.tmp, now=self.now_iso)
        # 2 expired & unpinned items => summary should say 2
        self.assertIn("demoted 2 item", stderr)


# ---------------------------------------------------------------------------
# CLI argument hygiene
# ---------------------------------------------------------------------------

class ArgvTests(unittest.TestCase):
    def test_bad_now_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            (Path(td) / "backpack").mkdir()
            proc = subprocess.run(
                [sys.executable, str(THIS / "expire.py"), td, "--now", "not-a-date"],
                capture_output=True, text=True,
            )
            self.assertNotEqual(proc.returncode, 0)
            self.assertIn("--now", proc.stderr)

    def test_missing_root_rejected(self):
        proc = subprocess.run(
            [sys.executable, str(THIS / "expire.py"), "/no/such/path/anywhere"],
            capture_output=True, text=True,
        )
        self.assertNotEqual(proc.returncode, 0)


if __name__ == "__main__":
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromModule(sys.modules[__name__])
    runner = unittest.TextTestRunner(stream=sys.stdout, verbosity=2)
    result = runner.run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)
