from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import tempfile
import unittest
import urllib.error
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load(name, rel):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


drift = load("check_version_drift", "scripts/check_version_drift.py")
validator = load("validate_manifests", "scripts/validate_manifests.py")


class RepoFromUrlTests(unittest.TestCase):
    def test_extracts_owner_repo(self):
        self.assertEqual(
            drift.repo_from_url("https://github.com/Coding-Dev-Tools/apighost"),
            "Coding-Dev-Tools/apighost",
        )

    def test_none_for_non_github(self):
        self.assertIsNone(drift.repo_from_url("https://example.invalid/tool"))
        self.assertIsNone(drift.repo_from_url(None))

    def test_trailing_slash_and_extra_path(self):
        self.assertEqual(
            drift.repo_from_url("https://github.com/o/r/"),
            "o/r",
        )


class NewestVersionTagTests(unittest.TestCase):
    def test_picks_highest_semver(self):
        self.assertEqual(drift.newest_version_tag(["v0.1.0", "v0.1.1", "v0.1.10", "v0.1.2"]), "0.1.10")

    def test_ignores_non_version_tags(self):
        self.assertEqual(drift.newest_version_tag(["latest", "nightly"]), None)

    def test_strips_v_prefix(self):
        self.assertEqual(drift.newest_version_tag(["v1.2.3"]), "1.2.3")


class CheckverHomepageConsistencyTests(unittest.TestCase):
    BASE = {
        "name": "x",
        "version": "1.0.0",
        "description": "d",
        "homepage": "https://github.com/o/r",
        "license": "MIT",
        "depends": "python",
        "post_install": "",
        "url": f"https://github.com/o/r/archive/refs/tags/v1.0.0.tar.gz",
        "hash": "a" * 64,
    }

    def test_matching_repos_pass(self):
        m = dict(self.BASE, checkver={"github": "https://github.com/o/r"}, autoupdate={"url": "u/$version"})
        self.assertEqual(validator.problems_for("t.json", m), [])

    def test_wrong_repo_flagged(self):
        m = dict(self.BASE, checkver={"github": "https://github.com/o/other"})
        probs = validator.problems_for("t.json", m)
        self.assertTrue(any("different repo than homepage" in p for p in probs))


class MainBehaviourTests(unittest.TestCase):
    """End-to-end main() tests: skip warnings, exit-code semantics, summary."""

    def _write_manifest(self, tmpdir, name="tool.json", version="1.0.0"):
        p = Path(tmpdir) / name
        p.write_text(
            json.dumps(
                {
                    "name": "x",
                    "version": version,
                    "description": "d",
                    "homepage": "https://github.com/o/r",
                    "license": "MIT",
                    "depends": "python",
                    "post_install": "",
                    "url": "https://github.com/o/r/archive/refs/tags/v1.0.0.tar.gz",
                    "hash": "a" * 64,
                }
            ),
            encoding="utf-8",
        )
        return str(p)

    def _run_main(self, argv, monkeypatched):
        orig = drift.fetch_tags
        drift.fetch_tags = monkeypatched
        try:
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc = drift.main(argv)
        finally:
            drift.fetch_tags = orig
        return rc, buf.getvalue()

    def test_exit0_on_skipped_upstream_with_warning(self):
        with tempfile.TemporaryDirectory() as td:
            self._write_manifest(td)

            def boom(repo, timeout=10):
                raise urllib.error.HTTPError(f"{drift.API_BASE}/{repo}/tags", 404, "nf", {}, None)

            rc, out = self._run_main([td], boom)
            self.assertEqual(rc, 0)
            self.assertIn("::warning::bucket/tool.json: SKIPPED upstream", out)
            self.assertIn("HTTP 404", out)
            self.assertIn("skipped/unreachable: bucket/tool.json", out)

    def test_exit0_on_tagless_repo_with_warning(self):
        with tempfile.TemporaryDirectory() as td:
            self._write_manifest(td)
            rc, out = self._run_main([td], lambda repo, timeout=10: ["latest", "nightly"])
            self.assertEqual(rc, 0)
            self.assertIn("no version tags published", out)

    def test_exit1_on_drift(self):
        with tempfile.TemporaryDirectory() as td:
            self._write_manifest(td, version="1.0.0")
            rc, out = self._run_main([td], lambda repo, timeout=10: ["v2.0.0"])
            self.assertEqual(rc, 1)
            self.assertIn("'1.0.0' != upstream latest tag '2.0.0'", out)

    def test_exit1_on_no_manifests(self):
        with tempfile.TemporaryDirectory() as td:
            rc, out = self._run_main([td], lambda repo, timeout=10: [])
            self.assertEqual(rc, 1)
            self.assertIn("no manifests found", out)

    def test_network_error_is_nonfatal_skip(self):
        # 5xx / network failures must warn + skip, not crash or fail the run.
        with tempfile.TemporaryDirectory() as td:
            self._write_manifest(td)

            def boom(repo, timeout=10):
                raise urllib.error.URLError("connection reset")

            rc, out = self._run_main([td], boom)
            self.assertEqual(rc, 0)
            self.assertIn("URLError", out)


if __name__ == "__main__":
    unittest.main()
