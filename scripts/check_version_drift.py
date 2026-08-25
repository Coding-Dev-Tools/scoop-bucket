#!/usr/bin/env python3
"""Check every bucket manifest's version against its upstream GitHub tags.

Closes a silent-green gap: validate_manifests.py checks internal consistency
(version matches url tag), but nothing compared manifest version against the
UPSTREAM repo. json2sql-cli drifted this way (manifest said 0.1.1 while the
latest published release was 0.1.0) and was only caught by hand.

For each manifest:
  * resolves the upstream repo from checkver.github (preferred) or homepage
  * queries https://api.github.com/repos/<owner>/<repo>/tags (with auth if available)
  * compares the newest tag (v-prefix stripped) with the manifest version
  * falls back to /releases/latest if no version tags exist

Exit code 0 = all match; 1 = at least one drifted or unreachable repo.
"""
import argparse
import glob
import json
import os
import re
import sys
import time
import urllib.request
import urllib.error

API_BASE = "https://api.github.com/repos"
TAG_RE = re.compile(r"^v?\d+(\.\d+)*$")
MAX_RETRIES = 3
BASE_BACKOFF = 2  # seconds


def repo_from_url(url):
    """Extract '<owner>/<repo>' from a github.com URL, else None."""
    if not isinstance(url, str) or "github.com/" not in url:
        return None
    parts = url.split("github.com/", 1)[1].strip("/").split("/")
    if len(parts) >= 2 and parts[0] and parts[1]:
        return f"{parts[0]}/{parts[1]}"
    return None


def repo_from_manifest(data):
    """Extract upstream repo from checkver.github (preferred) or homepage."""
    cv = data.get("checkver")
    if isinstance(cv, dict):
        gh = cv.get("github")
        if isinstance(gh, str):
            repo = repo_from_url(gh)
            if repo:
                return repo
    hp = data.get("homepage")
    if isinstance(hp, str):
        return repo_from_url(hp)
    return None


def newest_version_tag(tags):
    """Return the newest semver-ish tag (v-prefix stripped) from a tag-name list."""
    versions = [t.lstrip("v") for t in tags if TAG_RE.match(t)]
    if not versions:
        return None
    def key(v):
        return [int(x) for x in v.split(".")]
    return max(versions, key=key)


def _github_headers():
    """Build headers for GitHub API requests, including auth if available."""
    headers = {"Accept": "application/vnd.github+json"}
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _fetch_with_retry(url, headers, timeout=15):
    """Fetch URL with retry logic and exponential backoff."""
    last_exc = None
    for attempt in range(MAX_RETRIES):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.load(resp)
        except urllib.error.HTTPError as exc:
            # Don't retry 4xx errors (404, 403, etc.) - they're not transient
            if 400 <= exc.code < 500:
                raise
            last_exc = exc
        except (urllib.error.URLError, TimeoutError) as exc:
            last_exc = exc
        if attempt < MAX_RETRIES - 1:
            time.sleep(BASE_BACKOFF * (2 ** attempt))
    if last_exc:
        raise last_exc
    raise RuntimeError("fetch failed after retries with no exception captured")


def fetch_tags(repo, timeout=15):
    """Fetch all tags from a GitHub repo with pagination support."""
    headers = _github_headers()
    all_tags = []
    page = 1
    while True:
        url = f"{API_BASE}/{repo}/tags?per_page=100&page={page}"
        data = _fetch_with_retry(url, headers, timeout)
        if not data:
            break
        all_tags.extend(t["name"] for t in data if "name" in t)
        if len(data) < 100:
            break
        page += 1
    return all_tags


def fetch_latest_release(repo, timeout=15):
    """Fetch the latest release (not pre-release) from a GitHub repo."""
    headers = _github_headers()
    url = f"{API_BASE}/{repo}/releases/latest"
    try:
        data = _fetch_with_retry(url, headers, timeout)
        tag = data.get("tag_name", "")
        return tag.lstrip("v") if tag else None
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return None
        raise


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
            with open(path, encoding="utf-8") as handle:
                data = json.load(handle)
        except Exception as exc:
            problems.append(f"{rel}: invalid JSON: {exc}")
            continue

        repo = repo_from_manifest(data)
        if not repo:
            problems.append(f"{rel}: cannot determine upstream repo (no checkver.github or github.com homepage)")
            continue

        # Try tags first (most common)
        try:
            tags = fetch_tags(repo)
            latest = newest_version_tag(tags)
        except Exception as exc:
            status = getattr(exc, "code", None)
            if status == 404:
                print(f"{rel}: upstream {repo} unreachable (404) - skipped")
                continue
            problems.append(f"{rel}: could not query tags for {repo}: {exc}")
            continue

        # Fallback to releases if no version tags found
        if latest is None:
            try:
                latest = fetch_latest_release(repo)
            except Exception as exc:
                status = getattr(exc, "code", None)
                if status == 404:
                    print(f"{rel}: upstream {repo} has no releases - skipped")
                    continue
                problems.append(f"{rel}: could not query releases for {repo}: {exc}")
                continue

        if latest is None:
            print(f"{rel}: upstream {repo} has no version tags or releases - skipped")
            continue

        version = data.get("version")
        if version != latest:
            problems.append(f"{rel}: version '{version}' != upstream latest '{latest}' ({repo})")
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