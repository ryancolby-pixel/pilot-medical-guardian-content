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

windowsSetupLive: the app's switch for the Windows rows on MedXPress Prep (Send to a computer
and the Chrome/Edge steps) in builds that carry the corrected Windows sheet, read as
`manifest.windowsSetupLive` (ReferenceManifest.swift, SendToComputer.isAvailable). Absent means
off, and the app does NOT remember it, so dropping the key hides the rows again on every
installed copy. Preserved from the existing manifest. WINDOWS_SETUP_LIVE=true sets it;
WINDOWS_SETUP_LIVE=false removes the key; any other value (empty included) stops the run before
anything is written. Launch day:

    WINDOWS_SETUP_LIVE=true CONTENT_VERSION=YYYY-MM-DD.N python3 scripts/gen_manifest.py

pcExtensionLive: 🚫 RETIRED FOR VISIBILITY 2026-11-12 (Ryan: "Yes, new switch"). It was the first
Windows switch, and App Store 2.3.8 reads it: setting it would show 2.3.8's OLD Windows sheet. It
is never set again, so every build up to 2.3.8 stays hidden. Still preserved if present, and
PC_EXTENSION_LIVE=true|false still works (with a warning), only so nothing that calls it breaks.

appUpdate: the latest App Store version per platform, for the app's one-per-version "Update Available"
alert (2026-11-18, Ryan: "I want it in this build"; app side UpdateAvailable.swift, ReferenceManifest.appUpdate).
Shape: {"ios": {"version": "2.5.0", "minimumOS": "18.0", "notes": ["...", "..."]}, "mac": {...}}. Set each
platform ONLY after the App Store shows that version on that platform (/release-day), and the notes are
public copy Ryan reviews first. Older builds ignore the key; builds that read it decode it leniently.

    APP_UPDATE_IOS='{"version":"2.5.0","notes":["Line one.","Line two."]}' CONTENT_VERSION=YYYY-MM-DD.N python3 scripts/gen_manifest.py
    APP_UPDATE_MAC=none python3 scripts/gen_manifest.py      # removes the Mac entry (pull)

version is REQUIRED (the release's own number) and must EQUAL Apple's store lookup for that platform (iOS: the
plain lookup; Mac: entity=desktopSoftware), so a typo, the other platform's number or a lookup still showing the
previous release stops the run (Hub 11/18). minimumOS is filled from the same lookup (or must equal it if given).
No lookup answer: nothing is written.
The script also refuses notes that are not 1 to 3 single lines of at most 160 characters, an em dash, an
en dash or "--", and any other key. Plain rebuilds (no APP_UPDATE env) never call the lookup.

Any OTHER top-level key already in the manifest is kept as it is, so a future switch cannot be
wiped by a rebuild before this script learns its name.

🚨 CHANGING A SWITCH RESTAMPS generatedAt. Installed apps download a new manifest only when
the CDN's generatedAt is LATER than the one they hold (ReferenceContentLoader; contentVersion
is a label and does not gate delivery). A switch flipped without a new stamp would sit on the
CDN and never reach a device that already holds the current manifest. So a value changed
through PAYWALL_ACTIVE_DATE, WINDOWS_SETUP_LIVE or PC_EXTENSION_LIVE stamps a new generatedAt even when no file
changed. Change switches ONLY through those env vars: a hand edit of manifest.json followed by
a rebuild keeps the old stamp, and devices never see it.

🚨 A WRONG TYPE BREAKS EVERY DEVICE'S UPDATES, not just the switch: the app decodes the
manifest with Codable, and one bad value fails the whole decode. So this script refuses to
write a windowsSetupLive or pcExtensionLive that is not true/false, or a paywallActiveDate the app's .iso8601
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
KNOWN_FLAGS = ("paywallActiveDate", "pcExtensionLive", "windowsSetupLive", "appUpdate")

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

ws = os.environ.get("WINDOWS_SETUP_LIVE")
if ws is not None:
    if ws.lower() == "true":
        flags["windowsSetupLive"] = True
    elif ws.lower() == "false":
        flags.pop("windowsSetupLive", None)
    else:
        fail(f"WINDOWS_SETUP_LIVE must be true or false, got {ws!r}. Nothing written.")

pc = os.environ.get("PC_EXTENSION_LIVE")
if pc:
    print("⚠️  gen_manifest: PC_EXTENSION_LIVE is RETIRED for visibility (Ryan 11/12). Builds with the "
          "corrected Windows sheet read windowsSetupLive (WINDOWS_SETUP_LIVE=true|false); pcExtensionLive=true "
          "would show App Store 2.3.8's OLD Windows sheet.", file=sys.stderr)
    if pc.lower() == "true":
        flags["pcExtensionLive"] = True
    elif pc.lower() == "false":
        flags.pop("pcExtensionLive", None)
    else:
        fail(f"PC_EXTENSION_LIVE must be true or false, got {pc!r}. Nothing written.")

for _k, _env in (("windowsSetupLive", "WINDOWS_SETUP_LIVE"), ("pcExtensionLive", "PC_EXTENSION_LIVE")):
    if _k in flags and not isinstance(flags[_k], bool):
        fail(f"{_k} is {flags[_k]!r}, not true/false. The app would fail to decode the whole "
             f"manifest. Fix it with {_env}=true|false. Nothing written.")
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

VERSION = re.compile(r"[0-9]{1,6}(\.[0-9]{1,6}){0,3}")   # use fullmatch: ASCII digits, no trailing newline
UPDATE_PLATFORMS = ("ios", "mac")
UPDATE_ENTRY_KEYS = {"version", "minimumOS", "notes"}

def _update_entry_problem(platform, entry):
    """Why the app could not use this entry, or None. Stricter than the app, which reads a bad
    entry as no alert: this script stops instead, so a typo never ships silently."""
    if not isinstance(entry, dict):
        return f"{platform} must be an object"
    extra = set(entry) - UPDATE_ENTRY_KEYS
    if extra:
        return f"{platform} has unknown keys {sorted(extra)}"
    if not (isinstance(entry.get("version"), str) and VERSION.fullmatch(entry["version"])):
        return f"{platform}.version must look like 2.5.0, got {entry.get('version')!r}"
    if not (isinstance(entry.get("minimumOS"), str) and VERSION.fullmatch(entry["minimumOS"])):
        return f"{platform}.minimumOS is required and must look like 18.6, got {entry.get('minimumOS')!r}"
    notes = entry.get("notes", [])
    if not (isinstance(notes, list) and 1 <= len(notes) <= 3):
        return f"{platform}.notes must be a list of 1 to 3 lines"
    for line in notes:
        if not (isinstance(line, str) and line.strip() and len(line) <= 160):
            return f"{platform}.notes lines must be non-empty text of at most 160 characters, got {line!r}"
        if "\n" in line or "\r" in line:
            return f"{platform}.notes lines must be single lines: {line!r}"
        if "\u2014" in line or "\u2013" in line or "--" in line:
            return f"{platform}.notes must not use an em dash, en dash or -- (house style): {line!r}"
    return None

APP_ID = 6772534988
STORE_LOOKUP = {
    "ios": f"https://itunes.apple.com/lookup?id={APP_ID}&country=us",
    "mac": f"https://itunes.apple.com/lookup?id={APP_ID}&country=us&entity=desktopSoftware",
}

def _store_lookup(platform):
    """The live App Store version and minimum OS for one platform, or stop. Public data, no secrets."""
    # System curl, not urllib: a python.org Python on macOS often has no CA bundle and cannot verify
    # Apple's certificate (seen 11/18); curl uses the Mac's own trust store.
    import subprocess
    try:
        out = subprocess.run(["curl", "-sS", "--fail", "--max-time", "20", STORE_LOOKUP[platform]],
                             capture_output=True, text=True, check=True).stdout
        data = json.loads(out)
    except subprocess.CalledProcessError as e:
        fail(f"could not read the {platform} store lookup (curl exit {e.returncode}: {e.stderr.strip()}). Nothing written.")
    except Exception as e:
        fail(f"could not read the {platform} store lookup ({type(e).__name__}: {e}). Nothing written.")
    if not isinstance(data, dict) or not isinstance(data.get("results"), list):
        fail(f"the {platform} store lookup did not return the expected JSON object. Nothing written.")
    hit = next((r for r in data["results"] if isinstance(r, dict) and r.get("trackId") == APP_ID), None)
    if hit is None or "version" not in hit or "minimumOsVersion" not in hit:
        fail(f"the {platform} store lookup has no result for trackId {APP_ID} "
             f"(resultCount {data.get('resultCount')}). Nothing written.")
    version, minimum = str(hit["version"]), str(hit["minimumOsVersion"])
    if not (VERSION.fullmatch(version) and VERSION.fullmatch(minimum)):
        fail(f"the {platform} store lookup gave {version!r} / {minimum!r}. Nothing written.")
    return {"version": version, "minimumOS": minimum}

for _platform, _env in (("ios", "APP_UPDATE_IOS"), ("mac", "APP_UPDATE_MAC")):
    _raw = os.environ.get(_env)
    if _raw is None:
        continue
    _update = dict(flags.get("appUpdate") or {})
    if _raw.strip().lower() == "none":
        _update.pop(_platform, None)
    else:
        try:
            _entry = json.loads(_raw)
        except json.JSONDecodeError as e:
            fail(f"{_env} is not JSON ({e}). Nothing written.")
        if not isinstance(_entry, dict):
            fail(f"{_env} must be a JSON object. Nothing written.")
        if not isinstance(_entry.get("version"), str):
            fail(f"{_env} must give the release's version, e.g. \"version\":\"2.5.0\" (checked against the "
                 f"{_platform} store lookup, so a lookup still on the old release stops here). Nothing written.")
        _live = _store_lookup(_platform)
        for _key in ("version", "minimumOS"):
            if _key in _entry and _entry[_key] != _live[_key]:
                fail(f"{_env} {_key} {_entry[_key]!r} does not match the {_platform} store lookup ({_live[_key]!r}). "
                     "Set it only after the store shows that version. Nothing written.")
        _update[_platform] = {"version": _live["version"], "minimumOS": _live["minimumOS"],
                              **{k: v for k, v in _entry.items() if k not in ("version", "minimumOS")}}
    if _update:
        flags["appUpdate"] = _update
    else:
        flags.pop("appUpdate", None)

if "appUpdate" in flags:
    _au = flags["appUpdate"]
    if not isinstance(_au, dict) or not _au or set(_au) - set(UPDATE_PLATFORMS):
        fail(f"appUpdate must be an object with only ios and/or mac, got {_au!r}. Nothing written.")
    for _platform, _entry in _au.items():
        _problem = _update_entry_problem(_platform, _entry)
        if _problem:
            fail(f"appUpdate: {_problem}. Nothing written.")

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
def _new_stamp():
    """Now, but always STRICTLY LATER than the stamp being replaced. The app fetches only a later
    generatedAt, and the stamp has whole seconds: two runs inside one second (or an old stamp
    ahead of this clock) would otherwise republish the same time and the change would never
    reach a device that holds the previous manifest."""
    now = datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0)
    try:
        prev = datetime.datetime.fromisoformat(str(existing_generated).replace("Z", "+00:00"))
        if prev.tzinfo is not None and now <= prev:
            now = prev.astimezone(datetime.timezone.utc) + datetime.timedelta(seconds=1)
    except ValueError:
        pass
    return now.strftime("%Y-%m-%dT%H:%M:%SZ")
generated_at = existing_generated if unchanged else _new_stamp()

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
ws_label = json.dumps(flags["windowsSetupLive"]) if "windowsSetupLive" in flags else "(none)"
print(f"wrote {MANIFEST.relative_to(ROOT)}  version={version}  files={len(entries)}  "
      f"paywallActiveDate={flags.get('paywallActiveDate') or '(none)'}  windowsSetupLive={ws_label}  "
      f"pcExtensionLive={pc_label} (retired)  "
      f"appUpdate={json.dumps(flags['appUpdate']) if 'appUpdate' in flags else '(none)'}")
if flags_changed:
    print(f"   switch changed, generatedAt restamped to {generated_at} so installed apps fetch it")
if others:
    print(f"   kept other top-level keys as they were: {', '.join(others)}")
