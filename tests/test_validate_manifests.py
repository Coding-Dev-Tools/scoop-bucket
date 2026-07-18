from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "validate_manifests", ROOT / "scripts" / "validate_manifests.py"
)
assert SPEC and SPEC.loader
validate_manifests = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(validate_manifests)


def valid_manifest(**overrides):
    manifest = {
        "name": "Example",
        "version": "1.2.3",
        "description": "Example manifest",
        "homepage": "https://example.invalid",
        "license": "MIT",
        "depends": "python",
        "url": "https://github.com/example/tool/releases/download/v1.2.3/tool.zip",
        "hash": "a" * 64,
        "post_install": "Write-Host installed",
    }
    manifest.update(overrides)
    return manifest


class ManifestValidationTests(unittest.TestCase):
    def test_all_repository_manifests_validate(self):
        manifests = sorted((ROOT / "bucket").glob("*.json"))
        self.assertTrue(manifests)
        for path in manifests:
            with self.subTest(path=path.name):
                data = json.loads(path.read_text(encoding="utf-8"))
                self.assertEqual([], validate_manifests.problems_for(path.name, data))

    def test_empty_architecture_is_rejected(self):
        manifest = valid_manifest()
        manifest.pop("url")
        manifest.pop("hash")
        manifest["architecture"] = {}
        problems = validate_manifests.problems_for("empty-arch.json", manifest)
        self.assertEqual(
            ["empty-arch.json: 'architecture' present but empty - no url/hash anywhere"],
            problems,
        )

    def test_invalid_hash_and_release_tag_mismatch_are_rejected(self):
        manifest = valid_manifest(hash="not-a-sha256", version="9.9.9")
        problems = validate_manifests.problems_for("broken.json", manifest)
        self.assertEqual(2, len(problems))
        self.assertIn("not a 64-char sha256", problems[0])
        self.assertIn("does not match url tag", problems[1])

    def test_checkver_requires_templated_autoupdate(self):
        missing = valid_manifest(checkver="github")
        self.assertEqual(
            ["missing.json: has 'checkver' but missing 'autoupdate' (scoop cannot self-update)"],
            validate_manifests.problems_for("missing.json", missing),
        )

        malformed = valid_manifest(
            checkver="github", autoupdate={"url": "https://example.invalid/latest.zip"}
        )
        self.assertEqual(
            ["malformed.json: autoupdate.url must be a version-template containing '$version'"],
            validate_manifests.problems_for("malformed.json", malformed),
        )

    def test_main_rejects_empty_bucket_and_accepts_valid_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            bucket = Path(tmp)
            self.assertEqual(1, validate_manifests.main(["validate_manifests.py", str(bucket)]))
            (bucket / "example.json").write_text(
                json.dumps(valid_manifest()), encoding="utf-8"
            )
            self.assertEqual(0, validate_manifests.main(["validate_manifests.py", str(bucket)]))


if __name__ == "__main__":
    unittest.main()
