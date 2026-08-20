#!/usr/bin/env python3
"""Content validation for Pilot Medical Guardian's reference data.

Runs in CI on every PR before merge. Catches the cheap, mechanical mistakes
(invalid JSON, missing envelope fields, duplicate codes, unresolved SI
requirement cross-refs) so the AME advisor's review only spends time on the
medical/aeromedical content, not on bookkeeping. This is the §0 gate enforced
in code (CONTENT_PIPELINE.md).
"""
import json, re, sys, hashlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from content_time import is_day_only  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
V1 = ROOT / "v1"

REQUIRED_ENVELOPE = {"code", "contentVersion", "lastVerified", "sourceCitation"}

# ISO-8601, UTC, second precision, trailing Z. See scripts/content_time.py.
STAMP_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")

# Entries that already carried a day-only stamp on 2026-08-17. Grandfathered on purpose:
# nobody recorded a time for them, and inventing one would fabricate precision we never had.
# A day-only stamp on any code NOT in here is NEW, and fails.
_BASELINE = json.loads((Path(__file__).resolve().parent / "day-only-stamp-baseline.json").read_text())
DAY_ONLY_OK = {f: set(c) for f, c in _BASELINE["codes_by_file"].items()}

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

        # 🚨 lastVerified MUST CARRY A TIME OF DAY.
        #
        # Two tools decide "does this copy hold work nobody published?" by comparing the
        # newest stamp on each side, and both comparisons are strict — so two copies at the
        # SAME stamp are indistinguishable. Measured 2026-08-17, that tie was the common
        # case: 406 of 655 entries sat at a bare T00:00:00Z and all 11 files were at equality
        # with the app bundle. Proven by harness, 81 rewritten SI requirement texts with the
        # stamp untouched made check-cdn-drift exit 0 while printing the instruction that
        # destroys them, and made sync-bundle-from-cdn overwrite them outright.
        #
        # A day-only stamp also RENDERS a day early everywhere west of UTC, which is every
        # pilot this app has. (The app now formats provenance dates in UTC, so that half is
        # fixed at the display layer too.)
        #
        # 🚫 The 406 are grandfathered, NOT rewritten. Nobody recorded a time for them;
        # inventing one would fabricate precision we never had, which is the same error as
        # bumping lastVerified without redoing the comparison. They clear naturally: the next
        # genuine re-verification writes content_time.now_stamp().
        stamp = env.get("lastVerified")
        if isinstance(stamp, str) and not STAMP_RE.match(stamp):
            errors.append(
                f"{name}:{code} lastVerified '{stamp}' is not the canonical stamp format. "
                f"Expected ISO-8601 UTC to the second, e.g. '2026-08-17T14:23:11Z' "
                f"(scripts/content_time.now_stamp())"
            )
        elif is_day_only(stamp) and code not in DAY_ONLY_OK.get(name, set()):
            errors.append(
                f"{name}:{code} lastVerified '{stamp}' has no time of day. Stamp the moment "
                f"you actually checked it — use scripts/content_time.now_stamp(). "
                f"(Grandfathered entries are listed in scripts/day-only-stamp-baseline.json; "
                f"this code is not one of them.)"
            )
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


# ---------------------------------------------------------------------------
# Stamp-drift guard: prose changed, lastVerified did not.
#
# WHY THIS EXISTS. On 2026-08-20, 85 medication entries carried a lastVerified
# that predated their own text by up to three months. The largest group traced
# to a June pass that removed authored claims ("generally addressed as
# acceptable when well tolerated") and replaced them with the honest "not
# individually listed in an FAA medication list". That IS a verification, and
# the stamp never moved to say so. Nothing caught it for three months because
# nothing was looking at the relationship between the two.
#
# lastVerified means one thing: the date someone compared the entry against its
# source. If the words a pilot reads changed, that comparison happened, and the
# stamp has to move with it. See CONTENT_PIPELINE.md and CLAUDE.md.
#
# WHITESPACE IS NORMALISED BEFORE COMPARING, DELIBERATELY. A pure formatting
# pass is not a re-verification. Commit 179c0a4 added paragraph breaks to 54
# entries without changing a word, and those stamps were correctly left alone.
# Normalising is what separates that from a real edit -- and it is also what
# nearly hid the seven antidepressants, whose genuine re-source sat UNDER a
# later cosmetic commit.
#
# Compares the working tree against git HEAD, so it fires at the moment of the
# edit rather than months later. Works at clone depth 1.
# ---------------------------------------------------------------------------
import subprocess

def _prose(entry: dict) -> dict:
    """Long-form string fields outside the envelope, whitespace-normalised.

    Length-based rather than a hardcoded field list so a new content file is
    covered on the day it is added, not whenever someone remembers to update
    a constant here. Short fields (codes, names, cadence chips) are excluded:
    changing one is a mapping fix, not a re-reading of an FAA page.
    """
    out = {}
    for k, v in entry.items():
        if k == "envelope" or not isinstance(v, str):
            continue
        if len(v) >= 80:
            out[k] = re.sub(r"\s+", " ", v).strip()
    return out

def _head_version(name: str):
    try:
        r = subprocess.run(["git", "show", f"HEAD:v1/{name}"],
                           cwd=ROOT, capture_output=True, text=True, timeout=30)
        if r.returncode != 0:
            return None
        return json.loads(r.stdout)
    except Exception:
        return None

_guard_ran = False
for name, data in loaded.items():
    if not isinstance(data, list):
        continue
    old = _head_version(name)
    if old is None or not isinstance(old, list):
        continue          # new file, or no git history for it
    _guard_ran = True
    old_by_code = {
        (e.get("envelope") or {}).get("code"): e
        for e in old if isinstance(e, dict)
    }
    for entry in data:
        if not isinstance(entry, dict):
            continue
        env = entry.get("envelope") or {}
        code = env.get("code")
        was = old_by_code.get(code)
        if not was:
            continue      # newly added entry: nothing to drift from
        now_prose, was_prose = _prose(entry), _prose(was)
        changed = sorted(
            k for k in set(now_prose) | set(was_prose)
            if now_prose.get(k) != was_prose.get(k)
        )
        if changed and env.get("lastVerified") == (was.get("envelope") or {}).get("lastVerified"):
            errors.append(
                f"{name}:{code} — {', '.join(changed)} changed but lastVerified did not "
                f"(still {env.get('lastVerified')}). If you re-read the source, stamp it with "
                f"content_time.now_stamp(). If this was formatting only, the whitespace "
                f"normaliser would not have flagged it, so check what really changed."
            )

if not _guard_ran:
    print("⚠️  stamp-drift guard SKIPPED — no git history for any v1/ file. "
          "It is not protecting this run.")


if errors:
    print("CONTENT VALIDATION FAILED:")
    for e in errors:
        print(f"  • {e}")
    sys.exit(1)

print(f"✅ content valid — {len(content_files)} files; "
      f"manifest version: {manifest.get('contentVersion', '?')}")
