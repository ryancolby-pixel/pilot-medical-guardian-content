#!/usr/bin/env python3
"""Regenerate v1/manifest.json from the JSON files alongside it.

Computes sha256 + size for each file. The contentVersion is taken from the
CONTENT_VERSION env var (set by the release commit) or defaults to a build-time
date string. Run from the repo root:

    CONTENT_VERSION=2026.0-beta-1 python3 scripts/gen_manifest.py

THE GENERATOR OWNS ONLY contentVersion, generatedAt AND files. Every other top-level key is
a switch the app reads, set on purpose, and a rebuild must never drop it. This script runs on
every v1/ push (rebuild-manifest.yml), on every site deploy (pages.yml), in the monthly
AME-directory cron and by hand for a version bump, so a key it forgets is a key that vanishes
at the next one of those. Until 2026-11-12 it kept only paywallActiveDate, which would have
wiped pcExtensionLive (scope 2026-11-12 §3a, PRE_RELEASE_TEST.md:582).

paywallActiveDate: LOAD-BEARING. The app reads `manifest.paywallActiveDate` to flip
the Guardian Pro paywall live (earliest-wins). The generator must NOT drop it, or a
regenerated manifest would silently un-set the flip. It is preserved from the existing
manifest, and can be set/overridden with the PAYWALL_ACTIVE_DATE env var (ISO-8601, e.g.
2026-07-10T00:00:00Z). Pass PAYWALL_ACTIVE_DATE=none to deliberately clear it.

pcExtensionLive: the app's switch for the Windows rows on MedXPress Prep (Send to a computer
and the Chrome/Edge steps), read as `manifest.pcExtensionLive` (ReferenceManifest.swift,
SendToComputer.isAvailable). Absent means off, and the app does NOT remember it, so dropping
the key hides the rows again on every installed copy. Preserved from the existing manifest.
PC_EXTENSION_LIVE=true sets it; PC_EXTENSION_LIVE=false removes the key. Launch day:

    PC_EXTENSION_LIVE=true CONTENT_VERSION=YYYY-MM-DD.N python3 scripts/gen_manifest.py

Any OTHER top-level key already in the manifest is kept as it is, so a future switch cannot be
wiped by a rebuild before this script learns its name.

🚨 CHANGING A SWITCH RESTAMPS generatedAt. Installed apps download a new manifest only when
the CDN's generatedAt is LATER than the one they hold (ReferenceContentLoader; contentVersion
is a label and does not gate delivery). A switch flipped without a new stamp would sit on the
CDN and never reach a device that already holds the current manifest. So a value changed
through PAYWALL_ACTIVE_DATE or PC_EXTENSION_LIVE stamps a new generatedAt even when no file
changed. Change switches ONLY through those env vars: a hand edit of manifest.json followed by
a rebuild keeps the old stamp, and devices never see it.

🚨 A WRONG TYPE BREAKS EVERY DEVICE'S UPDATES, not just the switch: the app decodes the
manifest with Codable, and one bad value fails the whole decode. So this script refuses to
write a pcExtensionLive that is not true/false, or a paywallActiveDate the app's .iso8601
decoder cannot read (wrong shape, or a date that does not exist). It also refuses to run on a
manifest.json it cannot parse, rather than rebuilding from nothing and dropping every switch.
"""
import json, os, re, hashlib, datetime, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
V1 = ROOT / "v1"
MANIFEST = V1 / "manifest.json"

# Keys this script computes. Everything else at the top level is preserved.
GENERATED_KEYS = ("contentVersion", "generatedAt", "files")
# Switches the app decodes (ReferenceManifest.swift), in the order they are written.
KNOWN_FLAGS = ("paywallActiveDate", "pcExtensionLive")

# What JSONDecoder's .iso8601 strategy accepts: whole seconds, Z or a numeric offset.
ISO8601 = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(Z|[+-]\d{2}:\d{2})$")

# Files that ship in the manifest (everything in v1/ except the manifest itself).
FILES = sorted(p.name for p in V1.glob("*.json") if p.name != "manifest.json")

def sha256_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(64 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

def fail(msg):
    print(f"❌ gen_manifest: {msg}", file=sys.stderr)
    sys.exit(1)

# Preserve the existing switches + contentVersion unless the env overrides them, so an
# automatic rebuild (checksum refresh) never silently un-sets a switch or relabels the CDN
# version out of step with the app's bundled label. A human bumps the version for a real
# content release via CONTENT_VERSION.
#
# A manifest that EXISTS but cannot be read stops the run. Starting from {} there would drop every
# switch, relabel contentVersion and restamp generatedAt, and CI would commit and deploy that with
# nothing going red (a trailing comma from a hand edit, or merge-conflict markers, is enough).
# Only a MISSING file starts fresh: fix the file, or delete it on purpose to rebuild from nothing.
existing = {}
if MANIFEST.exists():
    try:
        with open(MANIFEST) as _f:
            existing = json.load(_f)
    except (json.JSONDecodeError, UnicodeDecodeError, OSError) as e:
        fail(f"cannot read {MANIFEST.relative_to(ROOT)} ({e}). A rebuild from nothing would drop every "
             "switch, so nothing written. Fix the file (git show HEAD:v1/manifest.json has the last good one).")
    if not isinstance(existing, dict):
        fail(f"{MANIFEST.relative_to(ROOT)} is not a JSON object. Nothing written.")

existing_version = existing.get("contentVersion")
existing_generated = existing.get("generatedAt")
existing_entries = existing.get("files")

flags = {k: existing[k] for k in KNOWN_FLAGS if k in existing}
before = dict(flags)

flip = os.environ.get("PAYWALL_ACTIVE_DATE")
if flip == "none":
    flags.pop("paywallActiveDate", None)
elif flip:
    flags["paywallActiveDate"] = flip

pc = os.environ.get("PC_EXTENSION_LIVE")
if pc:
    if pc.lower() == "true":
        flags["pcExtensionLive"] = True
    elif pc.lower() == "false":
        flags.pop("pcExtensionLive", None)
    else:
        fail(f"PC_EXTENSION_LIVE must be true or false, got {pc!r}. Nothing written.")

if "pcExtensionLive" in flags and not isinstance(flags["pcExtensionLive"], bool):
    fail(f"pcExtensionLive is {flags['pcExtensionLive']!r}, not true/false. The app would fail "
         "to decode the whole manifest. Fix it with PC_EXTENSION_LIVE=true|false. Nothing written.")
def _is_real_iso8601(value):
    """The right shape AND a date that exists. 2026-07-32T00:00:00Z has the shape, and the app's
    decoder rejects it, which fails the whole manifest (checked in Swift 11/12). Python is stricter
    than the app (it also refuses Feb 30, 24:00 and :60, which the app rolls over); that only
    stops this script, never a device."""
    if not (isinstance(value, str) and ISO8601.match(value)):
        return False
    try:
        datetime.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return True

if "paywallActiveDate" in flags and not _is_real_iso8601(flags["paywallActiveDate"]):
    fail(f"paywallActiveDate is {flags['paywallActiveDate']!r}; the app reads only a real ISO-8601 "
         "time like 2026-07-10T00:00:00Z. Nothing written.")

# Unknown top-level keys ride along untouched (see the docstring).
others = {k: v for k, v in existing.items() if k not in GENERATED_KEYS and k not in KNOWN_FLAGS}

flags_changed = flags != before

version = os.environ.get("CONTENT_VERSION") or existing_version or datetime.date.today().isoformat()
entries = []
for name in FILES:
    p = V1 / name
    entries.append({"filename": name, "size": p.stat().st_size, "checksum": sha256_of(p)})

# IDEMPOTENT ON generatedAt. Only stamp a new time when a file's bytes actually changed, or
# when a switch the app reads changed (see the docstring: otherwise the flip never reaches
# a device).
#
# This matters because the app's ReferenceContentLoader decides whether to use CDN content
# by comparing the CDN manifest's generatedAt against the one baked into the build. Bumping
# it on every run would tell every installed app that the reference data changed each time
# this script runs, including on website-only deploys where not one byte of v1/ moved.
#
# It also lets this script run safely inside the Pages deploy: regenerating on every deploy
# guarantees the published manifest always matches the published files, without inventing a
# content change to announce.
unchanged = existing_entries == entries and bool(existing_generated) and not flags_changed
generated_at = existing_generated if unchanged else datetime.datetime.now(
    datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

manifest = {
    "contentVersion": version,
    "generatedAt": generated_at,
}
# Switches go BEFORE files (matches the app's bundled manifest ordering).
for k in KNOWN_FLAGS:
    if k in flags:
        manifest[k] = flags[k]
manifest.update(others)
manifest["files"] = entries

with open(MANIFEST, "w") as f:
    json.dump(manifest, f, indent=2)
    f.write("\n")

pc_label = json.dumps(flags["pcExtensionLive"]) if "pcExtensionLive" in flags else "(none)"
print(f"wrote {MANIFEST.relative_to(ROOT)}  version={version}  files={len(entries)}  "
      f"paywallActiveDate={flags.get('paywallActiveDate') or '(none)'}  pcExtensionLive={pc_label}")
if flags_changed:
    print(f"   switch changed, generatedAt restamped to {generated_at} so installed apps fetch it")
if others:
    print(f"   kept other top-level keys as they were: {', '.join(others)}")
