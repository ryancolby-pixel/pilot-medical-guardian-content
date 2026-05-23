#!/usr/bin/env python3
"""Content validation for Pilot Medical Guardian's reference data.

Runs in CI on every PR before merge. Catches the cheap, mechanical mistakes
(invalid JSON, missing envelope fields, duplicate codes, unresolved SI
requirement cross-refs) so the AME advisor's review only spends time on the
medical/aeromedical content, not on bookkeeping. This is the §0 gate enforced
in code (CONTENT_PIPELINE.md).
"""
import json, sys, hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
V1 = ROOT / "v1"

REQUIRED_ENVELOPE = {"code", "contentVersion", "lastVerified", "sourceCitation"}

errors: list[str] = []

def load(name: str):
    try:
        return json.loads((V1 / name).read_text())
    except Exception as ex:
        errors.append(f"{name}: invalid JSON — {ex}")
        return None

# Load every JSON file in v1/ (each must be a list of entries with envelopes,
# except manifest.json which has its own shape).
content_files = [p.name for p in V1.glob("*.json") if p.name != "manifest.json"]
loaded = {name: load(name) for name in content_files}
manifest = load("manifest.json") or {}

# Envelope + uniqueness checks per content file
all_codes_by_file: dict[str, set[str]] = {}
for name, data in loaded.items():
    if data is None: continue
    if not isinstance(data, list):
        errors.append(f"{name}: top-level must be a JSON array")
        continue
    codes = set()
    for i, entry in enumerate(data):
        env = entry.get("envelope", {}) if isinstance(entry, dict) else {}
        missing = REQUIRED_ENVELOPE - set(env.keys())
        if missing:
            errors.append(f"{name}[{i}]: envelope missing {sorted(missing)}")
        code = env.get("code")
        if not code:
            continue
        if code in codes:
            errors.append(f"{name}: duplicate code '{code}'")
        codes.add(code)
    all_codes_by_file[name] = codes

# Cross-ref: SI condition.requirementCodes must resolve to existing requirement entries.
if "si_conditions.json" in loaded and "si_requirements.json" in loaded:
    req_codes = all_codes_by_file.get("si_requirements.json", set())
    for c in loaded["si_conditions.json"] or []:
        cc = c.get("envelope", {}).get("code", "?")
        for rc in c.get("requirementCodes", []):
            if rc not in req_codes:
                errors.append(f"si_conditions.json:{cc} references missing requirement '{rc}'")

# Manifest sanity: listed files exist and (if checksum/size present) match.
if manifest:
    listed = {e.get("filename"): e for e in manifest.get("files", [])}
    for name in content_files:
        if name not in listed:
            errors.append(f"manifest.json: missing entry for '{name}'")
    for name, entry in listed.items():
        p = V1 / name
        if not p.exists():
            errors.append(f"manifest.json: lists '{name}' but file is missing")
            continue
        size = p.stat().st_size
        checksum = hashlib.sha256(p.read_bytes()).hexdigest()
        if "size" in entry and entry["size"] != size:
            errors.append(f"manifest.json: size mismatch for {name} (manifest={entry['size']}, actual={size}) — run scripts/gen_manifest.py")
        if "checksum" in entry and entry["checksum"] not in ("sample", checksum):
            errors.append(f"manifest.json: checksum mismatch for {name} — run scripts/gen_manifest.py")

if errors:
    print("CONTENT VALIDATION FAILED:")
    for e in errors:
        print(f"  • {e}")
    sys.exit(1)

print(f"✅ content valid — {len(content_files)} files; "
      f"manifest version: {manifest.get('contentVersion', '?')}")
