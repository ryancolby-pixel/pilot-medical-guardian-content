#!/usr/bin/env python3
"""Fail if a manifest does not match the files sitting beside it.

Run against the STAGED copy during the Pages deploy so an inconsistent manifest can
never reach the CDN. The app verifies downloaded reference files against the manifest
checksum, so a mismatch means the app silently rejects the file and keeps stale content.

Deliberately a separate file rather than an inline heredoc in the workflow: a heredoc
terminator inside a YAML block scalar ends up indented, which does not terminate the
heredoc. That exact mistake broke two things in this repo on 2026-08-07.
"""
import hashlib
import json
import pathlib
import sys

target = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else "v1")
manifest_path = target / "manifest.json"

try:
    manifest = json.loads(manifest_path.read_text())
except (OSError, json.JSONDecodeError) as exc:
    print(f"::error title=Manifest unreadable::{manifest_path}: {exc}")
    sys.exit(2)

problems = []
for entry in manifest.get("files", []):
    path = target / entry["filename"]
    if not path.exists():
        problems.append(f"{entry['filename']}: listed in the manifest but not present")
        continue
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != entry["checksum"]:
        problems.append(f"{entry['filename']}: checksum mismatch")
    elif len(raw) != entry["size"]:
        problems.append(f"{entry['filename']}: size mismatch")

if problems:
    print("::error title=Manifest does not match the published files::" + "; ".join(problems))
    for p in problems:
        print("  " + p)
    sys.exit(1)

print(f"manifest verified against {target}: {len(manifest.get('files', []))} files, "
      f"generatedAt {manifest.get('generatedAt')}")
