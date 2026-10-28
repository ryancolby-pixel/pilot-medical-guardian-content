#!/usr/bin/env python3
"""Build the AME directory from the FAA Designee Locator, the ONLY source (Ryan 10/28: "This just
needs to pull all info from all AMEs including HIMS. Addresses are a must. No more PDF scraping").

Inputs
  --faa PATH   ame_database.json from update_ame_database.py --hims
               (default: scripts/data/faa_ame_locator.json, the committed snapshot)
  scripts/data/zip_centroids.csv     US Census 2024 ZCTA internal points (public domain)
  scripts/data/legacy_ame_codes.json  locator code -> the old ame-hims-NNN code (frozen)

Outputs (same entry format; old builds ignore streetAddress)
  v1/ame_directory_full.json   every AME office. Read by iOS 2.3.4 / Mac 1.2.4 and later.
  v1/ame_directory.json        the HIMS-trained AMEs, ONE entry per AME (the office holding its
                               old code, else its first). Older builds read THIS file under a
                               "This in-app list is N HIMS-trained AMEs" banner, so it must stay
                               HIMS-only and N must count AMEs, not offices.

Rules (each is load-bearing):
  * CODES NEVER CHANGE. A pilot's saved AMEs are stored by envelope.code
    (PilotProfile.favoriteAMECodes, which must never be disturbed). A locator office gets
    ame-faa-<designee number>-<zip5> (+ an address hash only when one AME has two offices in
    one ZIP), the same every month. The offices that were HIMS-PDF entries before 2026-10-28
    keep their old ame-hims-NNN code through legacy_ame_codes.json, which was made once
    (--make-legacy-map) and is never regenerated.
  * HIMS comes from the locator's own HIMS filter. Without that pass (the input's
    hims_checked is false) the build refuses, rather than mark every AME "not HIMS".
  * Names, practice names and street addresses are the FAA's own text, HTML codes decoded and
    runs of spaces collapsed; only the city is title-cased for the "City, ST ZIP" line.
  * Coordinates are the ZIP's Census internal point (rounded to 4 places): good enough for
    distance sorting, not a street-level pin. No ZIP match = null.
"""
import argparse
import csv
import hashlib
import html
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
V1 = ROOT / "v1"
DATA = Path(__file__).resolve().parent / "data"
OUT_FULL = V1 / "ame_directory_full.json"
OUT_HIMS = V1 / "ame_directory.json"
ZIPS = DATA / "zip_centroids.csv"
LEGACY = DATA / "legacy_ame_codes.json"

SOURCE_CITATION = "FAA Designee Locator (designee.faa.gov), active Aviation Medical Examiners"
SOURCE_URL = "https://designee.faa.gov/#/designeeLocator"
SUFFIXES = {"jr", "sr", "ii", "iii", "iv", "md", "do", "m.d.", "d.o."}


def tidy(s):
    # The locator returns some text HTML-escaped, sometimes twice ("PATEL &amp;amp; PULLIAM",
    # seen 2026-10-28). Decode until stable, then collapse runs of spaces.
    s = s or ""
    while (u := html.unescape(s)) != s:
        s = u
    return re.sub(r"\s+", " ", s).strip() or None


def norm(s):
    return re.sub(r"[^a-z]", "", (s or "").lower())


def title_city(c):
    return " ".join(w.capitalize() if w.isalpha() else w for w in (c or "").lower().split())


def canonical_stamp(iso):
    # validate.py wants "YYYY-MM-DDTHH:MM:SSZ"
    t = datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(timezone.utc)
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


def street(a):
    return tidy(", ".join(x for x in (a.get("address1"), a.get("address2")) if x and x.strip()))


def classes(c):
    if c == "First Class":
        return ["Senior AME", "Class I, II, III"]
    if c == "Second Class/Third Class":
        return ["Class II, III"]
    return []


def locator_codes(ames):
    """The stable ame-faa-... code for each locator row, in row order."""
    codes, seen = [], set()
    for a in ames:
        zip5 = (a.get("zip") or "")[:5]
        code = f"ame-faa-{a['designee_number']}-{zip5 or 'nozip'}"
        if code in seen:
            code += "-" + hashlib.sha1((a["address1"] or "").upper().encode()).hexdigest()[:6]
        seen.add(code)
        codes.append(code)
    return codes


def make_legacy_map(faa):
    """ONE-TIME (2026-10-28): match each old HIMS-PDF entry to its locator office by last
    name, first initial and state (full first name when two AMEs share those), preferring the
    office in the entry's city, else the AME's only office. Unmatched entries (not on the
    locator) get no mapping."""
    curated = json.loads(OUT_HIMS.read_text())

    def faa_key(a):
        parts = [p for p in (a["name"] or "").split() if p]
        while parts and parts[-1].lower().strip(".,") in SUFFIXES:
            parts.pop()
        if len(parts) < 2:
            return None
        return (norm(parts[-1]), norm(parts[0])[:1], a["state"].upper()), norm(parts[0])

    rows = {}
    for a, code in zip(faa["ames"], locator_codes(faa["ames"])):
        k = faa_key(a)
        if k:
            rows.setdefault(k[0], []).append((a, code, k[1]))
    mapping = {}
    for e in curated:
        last, rest = (e["name"].split(",", 1) + [""])[:2]
        first = re.sub(r"\(.*?\)", "", rest).strip().split()
        city, _, state = (e["location"] or "").rpartition(",")
        if not first:
            continue
        cands = rows.get((norm(last), norm(first[0])[:1], state.strip().upper()), [])
        if len({a["designee_number"] for a, _, _ in cands}) > 1:
            cands = [c for c in cands if c[2] == norm(first[0])]
        pick = [c for c in cands if norm(c[0]["city"]) == norm(city)] or (cands if len(cands) == 1 else [])
        if pick:
            mapping[pick[0][1]] = e["envelope"]["code"]
    LEGACY.write_text(json.dumps(dict(sorted(mapping.items())), indent=1) + "\n")
    print(f"legacy map: {len(mapping)} of {len(curated)} old HIMS entries matched -> {LEGACY.name}")


def write(path, entries):
    # One entry per line: a third the size of indented JSON, and the monthly PR diff reads
    # as one changed line per changed AME.
    path.write_text("[\n" + ",\n".join(json.dumps(e, ensure_ascii=False, separators=(",", ":"))
                                      for e in entries) + "\n]\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--faa", default=str(DATA / "faa_ame_locator.json"),
                    help="ame_database.json from update_ame_database.py --hims")
    ap.add_argument("--make-legacy-map", action="store_true", help="one-time; see make_legacy_map")
    args = ap.parse_args()

    faa = json.loads(Path(args.faa).expanduser().read_text())
    if args.make_legacy_map:
        return make_legacy_map(faa)
    if not faa.get("hims_checked", faa.get("count_hims", 0) > 0):
        sys.exit("this read has no HIMS pass (run update_ame_database.py --hims); refusing")

    legacy = json.loads(LEGACY.read_text())
    zips = {}
    with ZIPS.open() as f:
        for row in csv.reader(line for line in f if not line.startswith("#")):
            if row and row[0] != "zip":
                zips[row[0]] = (float(row[1]), float(row[2]))

    stamp = canonical_stamp(faa["last_updated"])
    envelope = {"contentVersion": "faa-locator-" + stamp[:10], "lastVerified": stamp,
                "sourceCitation": SOURCE_CITATION, "sourceURL": SOURCE_URL}
    out, designee, no_coords = [], [], 0
    for a, code in zip(faa["ames"], locator_codes(faa["ames"])):
        designee.append(a["designee_number"])
        zip5 = (a.get("zip") or "")[:5]
        lat, lon = zips.get(zip5, (None, None))
        no_coords += lat is None
        city = title_city(tidy(a["city"]))
        hims = bool(a.get("hims"))
        out.append({
            "envelope": {"code": legacy.get(code, code), **envelope},
            "name": tidy(a["name"]),
            "clinicName": tidy(a.get("practice")),
            "location": " ".join(x for x in (f"{city}," if city else "", a["state"], zip5) if x),
            "streetAddress": street(a),
            "phone": tidy(a.get("phone")),
            "website": None,
            "email": tidy(a.get("email")),
            "yearsAsAME": None,
            "handlesConditionCodes": None,
            "isHIMSTrained": hims,
            "languages": None,
            "examStyleIndicators": (["HIMS-trained"] if hims else []) + classes(a.get("class")) or None,
            "latitude": lat,
            "longitude": lon,
        })

    one_per_ame = {}
    for num, e in zip(designee, out):
        if e["isHIMSTrained"] and (num not in one_per_ame or e["envelope"]["code"].startswith("ame-hims-")):
            one_per_ame[num] = e
    hims = [e for e in out if e in one_per_ame.values()]
    kept = sum(1 for e in out if e["envelope"]["code"].startswith("ame-hims-"))
    write(OUT_FULL, out)
    write(OUT_HIMS, hims)
    print(f"locator rows: {len(faa['ames'])} | entries: {len(out)}"
          f" | HIMS-trained: {sum(1 for e in out if e['isHIMSTrained'])} listings, {len(hims)} AMEs"
          f" | old HIMS codes kept: {kept} of {len(legacy)} | no coordinates: {no_coords}")
    print(f"wrote {OUT_FULL.relative_to(ROOT)} and {OUT_HIMS.relative_to(ROOT)} (HIMS only, for older builds)")
    if kept != len(legacy):
        sys.exit("an old ame-hims code lost its office; saved AMEs would disappear. Check the read.")


if __name__ == "__main__":
    main()
