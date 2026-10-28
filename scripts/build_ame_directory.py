#!/usr/bin/env python3
"""Build v1/ame_directory_full.json: the curated HIMS directory + every active AME from the
FAA Designee Locator (Ryan 2026-10-27: "put them all in the app").

Inputs
  --faa PATH      ame_database.json from update_ame_database.py (default: scripts/data/faa_ame_locator.json,
                  the committed snapshot, so a HIMS-list refresh can re-run this merge)
  v1/ame_directory.json            the curated HIMS list (UNCHANGED, still served to older apps)
  scripts/data/zip_centroids.csv   US Census 2024 ZCTA internal points (public domain)

Output
  v1/ame_directory_full.json       same entry format as ame_directory.json

Rules (each is load-bearing):
  * Curated HIMS entries are copied VERBATIM, codes included. A pilot's saved AMEs are stored
    by envelope.code (PilotProfile.favoriteAMECodes, which must never be disturbed), so a code
    that changed would silently drop a favorite.
  * FAA AMEs who are already in the curated list are NOT added again (matched on last name,
    first initial and state). The curated entry carries the HIMS facts.
  * A new entry's code is ame-faa-<designee number>-<zip5> (+ a short address hash only when one
    AME has two offices in one ZIP), so it is the same every month and favorites survive.
  * isHIMSTrained is left null (unknown) for FAA-only entries, never false: the locator run
    does not mark HIMS by default, and "false" would be a claim we have not checked.
  * Names, practice names and addresses are the FAA's own text; only the city is title-cased
    for the "City, ST" location line the app already uses.
  * Coordinates are the ZIP's Census internal point (rounded to 4 places). No ZIP match = null,
    and the app simply leaves that AME out of distance sorting.
"""
import argparse
import csv
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
V1 = ROOT / "v1"
CURATED = V1 / "ame_directory.json"
OUT = V1 / "ame_directory_full.json"
ZIPS = Path(__file__).resolve().parent / "data" / "zip_centroids.csv"

SOURCE_CITATION = "FAA Designee Locator (designee.faa.gov), active Aviation Medical Examiners"
SOURCE_URL = "https://designee.faa.gov/#/designeeLocator"
SUFFIXES = {"jr", "sr", "ii", "iii", "iv", "md", "do", "m.d.", "d.o."}


def norm(s):
    return re.sub(r"[^a-z]", "", (s or "").lower())


def faa_key(full_name, state):
    parts = [p for p in re.split(r"\s+", (full_name or "").strip()) if p]
    while parts and parts[-1].lower().strip(".,") in SUFFIXES:
        parts.pop()
    if len(parts) < 2:
        return None
    return (norm(parts[-1]), norm(parts[0])[:1], state.upper()), norm(parts[0])


def curated_key(entry):
    # "Alford, Clarence (Terry), M.D."  +  location "Lagrange, GA"
    name = entry.get("name") or ""
    if "," not in name:
        return None
    last, rest = name.split(",", 1)
    first = re.sub(r"\(.*?\)", "", rest).strip().split()
    state = (entry.get("location") or "").rsplit(",", 1)[-1].strip().upper()
    if not first or len(state) != 2:
        return None
    return (norm(last), norm(first[0])[:1], state), norm(first[0])


def title_city(c):
    return " ".join(w.capitalize() if w.isalpha() else w for w in (c or "").lower().split())


def canonical_stamp(iso):
    # validate.py wants "YYYY-MM-DDTHH:MM:SSZ"
    t = datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(timezone.utc)
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


def tidy(s):
    return re.sub(r"\s+", " ", s or "").strip() or None


def classes(c):
    if c == "First Class":
        return ["Senior AME", "Class I, II, III"]
    if c == "Second Class/Third Class":
        return ["Class II, III"]
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--faa", default=str(Path(__file__).resolve().parent / "data" / "faa_ame_locator.json"),
                    help="ame_database.json from update_ame_database.py (default: the committed snapshot)")
    args = ap.parse_args()

    faa = json.loads(Path(args.faa).expanduser().read_text())
    curated = json.loads(CURATED.read_text())
    zips = {}
    with ZIPS.open() as f:
        for row in csv.reader(line for line in f if not line.startswith("#")):
            if row and row[0] != "zip":
                zips[row[0]] = (float(row[1]), float(row[2]))

    stamp = canonical_stamp(faa["last_updated"])
    version = "faa-locator-" + stamp[:10]
    # (last, first initial, state) -> curated first names. When two FAA AMEs share a key
    # (measured: R. Smith, TX), only the one whose full first name matches is the curated one.
    curated_keys = {}
    for k in filter(None, (curated_key(e) for e in curated)):
        curated_keys.setdefault(k[0], set()).add(k[1])
    designees_per_key = {}
    for a in faa["ames"]:
        k = faa_key(a["name"], a["state"])
        if k:
            designees_per_key.setdefault(k[0], set()).add(a["designee_number"])

    out = list(curated)
    seen_codes = {e["envelope"]["code"] for e in curated}
    skipped_curated, no_coords = 0, 0
    for a in faa["ames"]:
        key = faa_key(a["name"], a["state"])
        if key and key[0] in curated_keys and (
                len(designees_per_key[key[0]]) == 1 or key[1] in curated_keys[key[0]]):
            skipped_curated += 1
            continue
        zip5 = (a.get("zip") or "")[:5]
        code = f"ame-faa-{a['designee_number']}-{zip5 or 'nozip'}"
        if code in seen_codes:
            code += "-" + hashlib.sha1(a["address1"].upper().encode()).hexdigest()[:6]
        if code in seen_codes:
            continue  # an exact repeat of the same office
        seen_codes.add(code)
        lat, lon = zips.get(zip5, (None, None))
        if lat is None:
            no_coords += 1
        city = title_city(a["city"])
        out.append({
            "envelope": {
                "code": code,
                "contentVersion": version,
                "lastVerified": stamp,
                "sourceCitation": SOURCE_CITATION,
                "sourceURL": SOURCE_URL,
            },
            "name": tidy(a["name"]),
            "clinicName": tidy(a.get("practice")),
            "location": f"{city}, {a['state']}" if city else a["state"],
            "phone": a.get("phone") or None,
            "website": None,
            "email": a.get("email") or None,
            "yearsAsAME": None,
            "handlesConditionCodes": None,
            "isHIMSTrained": None,
            "languages": None,
            "examStyleIndicators": classes(a.get("class")),
            "latitude": lat,
            "longitude": lon,
        })

    # One entry per line: a third the size of indented JSON, and the monthly PR diff reads
    # as one changed line per changed AME.
    OUT.write_text("[\n" + ",\n".join(json.dumps(e, ensure_ascii=False, separators=(",", ":"))
                                        for e in out) + "\n]\n")
    added = len(out) - len(curated)
    print(f"curated kept: {len(curated)} | FAA rows: {len(faa['ames'])} | already curated: {skipped_curated}"
          f" | added: {added} | no coordinates: {no_coords} | total entries: {len(out)}")
    print(f"wrote {OUT.relative_to(ROOT)}")
    # Guard for the monthly job: a broken FAA page must never shrink the directory.
    if added < 0.8 * max(1, len(faa["ames"]) - skipped_curated):
        sys.exit("added fewer than 80% of usable FAA rows; refusing")


if __name__ == "__main__":
    main()
