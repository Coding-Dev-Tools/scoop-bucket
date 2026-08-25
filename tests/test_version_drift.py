from __future__ import annotations

import importlib.util
import unittest
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


class RepoFromManifestTests(unittest.TestCase):
    def test_prefers_checkver_github(self):
        data = {
            "homepage": "https://github.com/owner/repo-homepage",
            "checkver": {"github": "https://github.com/owner/repo-checkver"},
        }
        self.assertEqual(drift.repo_from_manifest(data), "owner/repo-checkver")

    def test_falls_back_to_homepage(self):
        data = {"homepage": "https://github.com/owner/repo-homepage"}
        self.assertEqual(drift.repo_from_manifest(data), "owner/repo-homepage")

    def test_none_when_no_github_url(self):
        data = {"homepage": "https://example.invalid/tool"}
        self.assertIsNone(drift.repo_from_manifest(data))
        data = {}
        self.assertIsNone(drift.repo_from_manifest(data))


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


if __name__ == "__main__":
    unittest.main()