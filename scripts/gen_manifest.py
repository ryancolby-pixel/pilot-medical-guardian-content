#!/usr/bin/env python3
"""Regenerate v1/manifest.json from the JSON files alongside it.

Computes sha256 + size for each file. The contentVersion is taken from the
CONTENT_VERSION env var (set by the release commit) or defaults to a build-time
date string. Run from the repo root:

    CONTENT_VERSION=2026.0-beta-1 python3 scripts/gen_manifest.py

paywallActiveDate: LOAD-BEARING. The app reads `manifest.paywallActiveDate` to flip
the Guardian Pro paywall live (earliest-wins). The generator must NOT drop it, or a
regenerated manifest would silently un-set the flip. It is preserved from the existing
manifest, and can be set/overridden with the PAYWALL_ACTIVE_DATE env var (ISO-8601, e.g.
2026-07-10T00:00:00Z). Pass PAYWALL_ACTIVE_DATE=none to deliberately clear it.
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

# Preserve the existing paywallActiveDate + contentVersion unless the env overrides them,
# so an automatic rebuild (checksum refresh) never silently un-sets the paywall flip or
# relabels the CDN version out of step with the app's bundled label. A human bumps the
# version for a real content release via CONTENT_VERSION.
existing_flip = None
existing_version = None
if MANIFEST.exists():
    try:
        _m = json.load(open(MANIFEST))
        existing_flip = _m.get("paywallActiveDate")
        existing_version = _m.get("contentVersion")
    except (json.JSONDecodeError, OSError):
        pass
flip = os.environ.get("PAYWALL_ACTIVE_DATE", existing_flip)
if flip == "none":
    flip = None

version = os.environ.get("CONTENT_VERSION") or existing_version or datetime.date.today().isoformat()
entries = []
for name in FILES:
    p = V1 / name
    entries.append({"filename": name, "size": p.stat().st_size, "checksum": sha256_of(p)})

manifest = {
    "contentVersion": version,
    "generatedAt": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
}
# Keep paywallActiveDate BEFORE files (matches the app's bundled manifest ordering).
if flip:
    manifest["paywallActiveDate"] = flip
manifest["files"] = entries

with open(MANIFEST, "w") as f:
    json.dump(manifest, f, indent=2)
    f.write("\n")

print(f"wrote {MANIFEST.relative_to(ROOT)}  version={version}  files={len(entries)}  paywallActiveDate={flip or '(none)'}")
