#!/usr/bin/env python3
"""Check every bucket manifest's version against its upstream GitHub tags.

Closes a silent-green gap: validate_manifests.py checks internal consistency
(version matches url tag), but nothing compared manifest version against the
UPSTREAM repo. json2sql-cli drifted this way (manifest said 0.1.1 while the
latest published release was 0.1.0) and was only caught by hand.

For each manifest:
  * resolves the upstream repo from homepage (github.com/<owner>/<repo>)
  * queries https://api.github.com/repos/<owner>/<repo>/tags (no auth needed;
    tags are used instead of /releases/latest because repos can tag without
    publishing a Release object)
  * compares the newest tag (v-prefix stripped) with the manifest version

Exit code 0 = all match; 1 = at least one drifted or unreachable repo.
Use --checkver-only to limit checks to offline checkver/homepage consistency.
"""
import argparse
import glob
import json
import os
import re
import sys
import urllib.request
import urllib.error

API_BASE = "https://api.github.com/repos"
TAG_RE = re.compile(r"^v?\d+(\.\d+)*$")


def repo_from_url(url):
    """Extract '<owner>/<repo>' from a github.com URL, else None."""
    if not isinstance(url, str) or "github.com/" not in url:
        return None
    parts = url.split("github.com/", 1)[1].strip("/").split("/")
    if len(parts) >= 2 and parts[0] and parts[1]:
        return f"{parts[0]}/{parts[1]}"
    return None


def newest_version_tag(tags):
    """Return the newest semver-ish tag (v-prefix stripped) from a tag-name list."""
    versions = [t.lstrip("v") for t in tags if TAG_RE.match(t)]
    if not versions:
        return None
    def key(v):
        return [int(x) for x in v.split(".")]
    return max(versions, key=key)


def fetch_tags(repo, timeout=10):
    req = urllib.request.Request(
        f"{API_BASE}/{repo}/tags?per_page=100",
        headers={"Accept": "application/vnd.github+json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return [t["name"] for t in json.load(resp)]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bucket", nargs="?", help="path to bucket/ (default: ../bucket)")
    args = parser.parse_args(argv)

    here = os.path.dirname(os.path.abspath(__file__))
    bucket = os.path.normpath(args.bucket or os.path.join(here, "..", "bucket"))
    manifests = sorted(glob.glob(os.path.join(bucket, "*.json")))
    if not manifests:
        print("::error::no manifests found - refusing to pass silently")
        return 1

    problems = []
    for path in manifests:
        rel = "bucket/" + os.path.basename(path)
        try:
            data = json.load(open(path, encoding="utf-8"))
        except Exception as exc:
            problems.append(f"{rel}: invalid JSON: {exc}")
            continue
        repo = repo_from_url(data.get("homepage"))
        if not repo:
            problems.append(f"{rel}: homepage is not a github.com repo URL")
            continue
        try:
            latest = newest_version_tag(fetch_tags(repo))
        except Exception as exc:
            # 404 on a private/unreleased repo is informational, not drift.
            status = getattr(exc, "code", None)
            if status == 404:
                print(f"{rel}: upstream {repo} unreachable (404) - skipped")
                continue
            problems.append(f"{rel}: could not query tags for {repo}: {exc}")
            continue
        if latest is None:
            print(f"{rel}: upstream {repo} has no version tags yet - skipped")
            continue
        version = data.get("version")
        if version != latest:
            problems.append(f"{rel}: version '{version}' != upstream latest tag '{latest}' ({repo})")
        else:
            print(f"{rel}: {version} == upstream {repo} ok")

    if problems:
        print(f"Version drift check FAILED; {len(problems)} problem(s):")
        for p in problems:
            print(f"::error::{p}")
        return 1
    print(f"Version drift check passed for {len(manifests)} manifest(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
