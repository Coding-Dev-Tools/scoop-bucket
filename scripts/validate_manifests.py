#!/usr/bin/env python3
"""Validate Scoop bucket manifests (cross-platform).

Closes the silent-green gap the inline PowerShell CI job misses:
when a manifest uses ``architecture``, the PowerShell check skips the
top-level url/hash requirement but never verifies the architecture block
actually contains url/hash, so a manifest with an empty ``architecture``
or an arch entry missing url/hash would still "pass".

This script also checks:
  * required top-level fields (version, description, homepage, license)
  * url+hash present at top level OR in EVERY architecture entry
  * hash is a 64-char hexadecimal sha256 (never a placeholder)
  * version string matches the release tag referenced in the url
  * bucket is non-empty (refuses to pass having validated nothing)

Exit code 1 if any problem is found, 0 if every manifest is valid.
"""
import glob
import json
import os
import re
import sys

REQUIRED_TOP = ["name", "version", "description", "homepage", "license", "depends", "post_install"]
HEX64 = re.compile(r"^[0-9a-fA-F]{64}$")


def problems_for(rel, data):
    probs = []
    if not isinstance(data, dict):
        return [f"{rel}: manifest is not a JSON object"]

    for key in REQUIRED_TOP:
        if key not in data:
            probs.append(f"{rel}: missing required field '{key}'")

    has_top_url = "url" in data
    has_top_hash = "hash" in data
    arch = data.get("architecture")

    if arch is None:
        if not has_top_url:
            probs.append(f"{rel}: missing 'url' (and no architecture block)")
        if not has_top_hash:
            probs.append(f"{rel}: missing 'hash' (and no architecture block)")
    elif not isinstance(arch, dict) or not arch:
        probs.append(f"{rel}: 'architecture' present but empty - no url/hash anywhere")
    else:
        for arch_name, spec in arch.items():
            if not isinstance(spec, dict):
                probs.append(f"{rel}: architecture.{arch_name} is not an object")
                continue
            if "url" not in spec:
                probs.append(f"{rel}: architecture.{arch_name} missing 'url'")
            if "hash" not in spec:
                probs.append(f"{rel}: architecture.{arch_name} missing 'hash'")

    def check_hash(loc, value):
        if not isinstance(value, str):
            probs.append(f"{rel}: {loc} 'hash' is not a string")
            return
        if not HEX64.match(value):
            probs.append(
                f"{rel}: {loc} 'hash' is not a 64-char sha256 (got {len(value)} chars)"
            )
        if value.strip("0") == "":
            probs.append(f"{rel}: {loc} 'hash' is a placeholder (all zeros)")

    if has_top_hash:
        check_hash("top-level", data["hash"])
    if isinstance(arch, dict):
        for arch_name, spec in arch.items():
            if isinstance(spec, dict) and "hash" in spec:
                check_hash(f"architecture.{arch_name}", spec["hash"])

    version = data.get("version")
    url = data.get("url")
    if isinstance(url, str) and isinstance(version, str):
        m = (
            re.search(r"/releases/download/([^/]+)/", url)
            or re.search(r"/archive/refs/tags/([^/]+)\.tar\.gz", url)
            or re.search(r"/archive/([^/]+)\.tar\.gz", url)
        )
        if m:
            tag = m.group(1).lstrip("v")
            if tag and tag != version:
                probs.append(
                    f"{rel}: version '{version}' does not match url tag '{tag}'"
                )

    # checkver.github must point at the same repo as homepage; a copy-paste
    # pointing at another owned repo makes `scoop checkver` compare against
    # the wrong project's releases and silently never (or wrongly) update.
    cv = data.get("checkver")
    cv_repo = None
    if isinstance(cv, dict):
        gh = cv.get("github")
        if isinstance(gh, str) and "github.com/" in gh:
            cv_repo = gh.split("github.com/", 1)[1].strip("/").lower()
    hp = data.get("homepage")
    if isinstance(hp, str) and "github.com/" in hp and cv_repo is not None:
        hp_repo = hp.split("github.com/", 1)[1].strip("/").lower()
        if cv_repo != hp_repo:
            probs.append(
                f"{rel}: checkver.github '{cv}' points at a different repo than homepage '{hp}'"
            )

    # autoupdate must accompany checkver so `scoop update` can self-apply new
    # versions; a manifest with checkver but no autoupdate silently never updates.
    if "checkver" in data and "autoupdate" not in data:
        probs.append(
            f"{rel}: has 'checkver' but missing 'autoupdate' (scoop cannot self-update)"
        )
    if "autoupdate" in data:
        au = data["autoupdate"]
        au_url = au.get("url") if isinstance(au, dict) else None
        if not au_url or "$version" not in au_url:
            probs.append(
                f"{rel}: autoupdate.url must be a version-template containing '$version'"
            )

    return probs


def main(argv):
    here = os.path.dirname(os.path.abspath(__file__))
    bucket = argv[1] if len(argv) > 1 else os.path.join(here, "..", "bucket")
    bucket = os.path.normpath(bucket)

    if not os.path.isdir(bucket):
        print("::error::bucket/ directory is missing", flush=True)
        return 1

    manifests = sorted(glob.glob(os.path.join(bucket, "*.json")))
    if not manifests:
        print("::error::No manifests found in bucket/ - refusing to pass silently.", flush=True)
        return 1

    all_probs = []
    for path in manifests:
        rel = "bucket/" + os.path.basename(path)
        try:
            with open(path, encoding="utf-8") as handle:
                data = json.load(handle)
        except Exception as exc:  # noqa: BLE001 - report and continue
            all_probs.append(f"{rel}: invalid JSON: {exc}")
            continue
        all_probs.extend(problems_for(rel, data))

    if all_probs:
        print(
            f"Validated {len(manifests)} manifest(s); {len(all_probs)} problem(s) found:",
            flush=True,
        )
        for prob in all_probs:
            print(f"::error::{prob}", flush=True)
        return 1

    print(f"Validated {len(manifests)} manifest(s); 0 problems found.", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
