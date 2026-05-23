#!/usr/bin/env python3
"""Regenerate v1/manifest.json from the JSON files alongside it.

Computes sha256 + size for each file. The contentVersion is taken from the
CONTENT_VERSION env var (set by the release commit) or defaults to a build-time
date string. Run from the repo root:

    CONTENT_VERSION=2026.0-beta-1 python3 scripts/gen_manifest.py
"""
import json, os, hashlib, datetime, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
V1 = ROOT / "v1"
MANIFEST = V1 / "manifest.json"

# Files that ship in the manifest (everything in v1/ except the manifest itself).
FILES = sorted(p.name for p in V1.glob("*.json") if p.name != "manifest.json")

def sha256_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(64 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

version = os.environ.get("CONTENT_VERSION") or datetime.date.today().isoformat()
entries = []
for name in FILES:
    p = V1 / name
    entries.append({"filename": name, "size": p.stat().st_size, "checksum": sha256_of(p)})

manifest = {
    "contentVersion": version,
    "generatedAt": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    "files": entries,
}

with open(MANIFEST, "w") as f:
    json.dump(manifest, f, indent=2)
    f.write("\n")

print(f"wrote {MANIFEST.relative_to(ROOT)}  version={version}  files={len(entries)}")
