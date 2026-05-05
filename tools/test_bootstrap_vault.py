#!/usr/bin/env python3
"""
test_bootstrap_vault.py — fixture-based tests for tools/bootstrap_vault.py.

Asserts that a freshly bootstrapped vault:

  1. has every layer dir present (backpack/{current,recent,...}, doctrine/,
     hoard/, policy/) with .gitkeep so empty dirs survive git;
  2. has a schema-clean policy/freshness.json;
  3. has the 9 doctrine seeds from bootstrap_doctrine.py;
  4. has the deploy/operator-vault-template/ files copied in
     (.gitignore, README.md, .github/workflows/{expire,today}.yml);
  5. honors --no-actions by skipping .github/;
  6. refuses to clobber a non-empty tree without --force.
"""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

THIS = Path(__file__).resolve().parent
REPO = THIS.parent
sys.path.insert(0, str(THIS))

import bootstrap_vault as bv  # noqa: E402


# ---------------------------------------------------------------------------
# Optional schema validation — silently skipped if jsonschema isn't around.
# ---------------------------------------------------------------------------

def _maybe_validate(schema_rel: str, payload) -> list[str]:
    try:
        from jsonschema import Draft202012Validator  # type: ignore
    except ImportError:
        return []
    schema_path = REPO / schema_rel
    if not schema_path.is_file():
        return []
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    return [e.message for e in Draft202012Validator(schema).iter_errors(payload)]


# ---------------------------------------------------------------------------
# tests
# ---------------------------------------------------------------------------

class BootstrapVaultTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="vault-test-"))

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp)

    # -- happy path --------------------------------------------------------

    def test_full_bootstrap_emits_expected_layout(self):
        bv.bootstrap(
            self.tmp,
            name="Tester",
            summary="end-to-end fixture",
            with_actions=True,
            force=False,
        )

        # Layer dirs present with .gitkeep
        for rel in (
            "backpack/current/.gitkeep",
            "backpack/recent/.gitkeep",
            "backpack/pinned/.gitkeep",
            "backpack/evergreen/.gitkeep",
            "backpack/_replaced/.gitkeep",
            "doctrine/.gitkeep",
            "hoard/.gitkeep",
            "policy/.gitkeep",
        ):
            self.assertTrue(
                (self.tmp / rel).exists(),
                msg=f"missing {rel}",
            )

        # Freshness policy is valid JSON and shaped right
        policy_path = self.tmp / "policy" / "freshness.json"
        self.assertTrue(policy_path.is_file())
        policy = json.loads(policy_path.read_text(encoding="utf-8"))
        self.assertIn("version", policy)
        self.assertIn("bands", policy)
        self.assertIn("rules", policy)
        # Schema-validate when jsonschema is present
        errors = _maybe_validate("schemas/freshness-policy.schema.json", policy)
        self.assertEqual(errors, [], msg=f"freshness.json schema errors: {errors}")

        # Doctrine seeds — 9 files written by bootstrap_doctrine.py
        doctrine_md = list((self.tmp / "doctrine").rglob("*.md"))
        self.assertGreaterEqual(
            len(doctrine_md), 9,
            msg=f"expected ≥9 doctrine seeds, got {len(doctrine_md)}",
        )

        # Template files copied in
        for rel in (
            ".gitignore",
            "README.md",
            ".github/workflows/expire.yml",
            ".github/workflows/today.yml",
        ):
            self.assertTrue(
                (self.tmp / rel).is_file(),
                msg=f"missing template file {rel}",
            )

    # -- --no-actions ------------------------------------------------------

    def test_no_actions_skips_github_workflows(self):
        bv.bootstrap(
            self.tmp,
            name="Tester",
            summary="no-actions fixture",
            with_actions=False,
            force=False,
        )
        self.assertFalse((self.tmp / ".github").exists())
        # but other template files still land
        self.assertTrue((self.tmp / "README.md").is_file())
        self.assertTrue((self.tmp / ".gitignore").is_file())

    # -- clobber protection -----------------------------------------------

    def test_refuses_to_clobber_existing_tree(self):
        (self.tmp / "important.txt").write_text("don't overwrite me", encoding="utf-8")
        with self.assertRaises(SystemExit):
            bv.bootstrap(self.tmp, with_actions=True, force=False)

    def test_force_proceeds_through_existing_tree(self):
        (self.tmp / "important.txt").write_text("ok to coexist", encoding="utf-8")
        bv.bootstrap(self.tmp, with_actions=True, force=True)
        self.assertTrue((self.tmp / "important.txt").exists())  # not deleted
        self.assertTrue((self.tmp / "policy" / "freshness.json").is_file())

    def test_hidden_dirs_dont_count_as_visible(self):
        # Mimic `git clone` of an empty repo: a `.git/` folder is present.
        (self.tmp / ".git").mkdir()
        (self.tmp / ".git" / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")
        # Should not raise (no --force needed)
        bv.bootstrap(self.tmp, with_actions=True, force=False)
        self.assertTrue((self.tmp / "policy" / "freshness.json").is_file())

    # -- idempotency-ish ---------------------------------------------------

    def test_second_bootstrap_with_force_is_idempotent(self):
        bv.bootstrap(self.tmp, with_actions=True, force=False)
        before = (self.tmp / "policy" / "freshness.json").read_bytes()
        bv.bootstrap(self.tmp, with_actions=True, force=True)
        after = (self.tmp / "policy" / "freshness.json").read_bytes()
        self.assertEqual(before, after)


# ---------------------------------------------------------------------------
# Workflow YAML sanity (parses + has the schedules + key steps we expect)
# ---------------------------------------------------------------------------

class WorkflowFileTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="vault-wf-"))
        bv.bootstrap(self.tmp, with_actions=True, force=False)

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp)

    def _load_yaml(self, rel: str) -> dict:
        import yaml  # type: ignore
        text = (self.tmp / rel).read_text(encoding="utf-8")
        return yaml.safe_load(text)

    def test_expire_yaml_has_schedule_and_dispatch(self):
        wf = self._load_yaml(".github/workflows/expire.yml")
        # PyYAML normalizes the bare key `on:` to True (a YAML 1.1 quirk),
        # so look for the trigger block under either spelling.
        triggers = wf.get("on") or wf.get(True)
        self.assertIsNotNone(triggers, msg="no triggers block in expire.yml")
        self.assertIn("schedule", triggers)
        self.assertIn("workflow_dispatch", triggers)
        self.assertEqual(triggers["schedule"][0]["cron"], "55 23 * * *")

    def test_today_yaml_renders_three_surfaces(self):
        wf = self._load_yaml(".github/workflows/today.yml")
        steps = wf["jobs"]["render"]["steps"]
        run_lines = " ".join(s.get("run", "") for s in steps)
        self.assertIn("daily_brief.py", run_lines)
        self.assertIn("narrator_brief.py", run_lines)
        self.assertIn("statusline.py", run_lines)

    def test_both_workflows_dual_checkout(self):
        for fname in ("expire.yml", "today.yml"):
            wf = self._load_yaml(f".github/workflows/{fname}")
            jobs = wf.get("jobs", {})
            # only one job per file in this template
            (job,) = jobs.values()
            paths = [s.get("with", {}).get("path") for s in job["steps"]]
            repos = [s.get("with", {}).get("repository") for s in job["steps"]]
            self.assertIn("vault", paths, msg=f"{fname} must checkout vault as ./vault")
            self.assertIn("substrate", paths,
                          msg=f"{fname} must checkout operator-core-mini as ./substrate")
            self.assertIn("snackdriven/operator-core-mini", repos,
                          msg=f"{fname} must reference snackdriven/operator-core-mini")

    def test_both_workflows_request_contents_write(self):
        for fname in ("expire.yml", "today.yml"):
            wf = self._load_yaml(f".github/workflows/{fname}")
            self.assertEqual(wf.get("permissions", {}).get("contents"), "write")


if __name__ == "__main__":
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromModule(sys.modules[__name__])
    runner = unittest.TextTestRunner(stream=sys.stdout, verbosity=2)
    result = runner.run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)
