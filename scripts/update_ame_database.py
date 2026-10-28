#!/usr/bin/env python3
"""Monthly FAA AME list from the FAA Designee Locator (designee.faa.gov).

Rebuilt 2026-10-27 from a Grok draft whose clicks were guessed and timed out on the real
page ("Location Search" sits inside a collapsed "Select Search Criteria" panel). This
version opens the real locator in Chromium, accepts the FAA System Use Notice (Ryan
approved 10/27), then sends the site's OWN search request (the one its Search button
sends, captured from the page) once per state, with a pause between requests.

Per state: one request for every AME (with --hims, a second with the site's HIMS filter).

Output (AME_OUT, default ~/Downloads/pilotmedicalguardian/ame), nothing is published:
  ame_database.json  every AME row with the fields below, plus last_updated / source / counts
  ame_database.csv   the same, flat
  ame_raw.json       the site's raw records per state, untouched, for audit

Run:  python3 update_ame_database.py            (visible browser; add --hims to mark HIMS AMEs)
      python3 update_ame_database.py --headless
Needs: pip install playwright && playwright install chromium
"""
import asyncio
import csv
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

from playwright.async_api import async_playwright

LOCATOR = "https://designee.faa.gov/#/designeeLocator"
OUT_DIR = Path(os.environ.get("AME_OUT", "~/Downloads/pilotmedicalguardian/ame")).expanduser()
PAUSE_MS = 1500
CONCURRENCY = 4  # states in flight at once
HEADLESS = "--headless" in sys.argv
WITH_HIMS = "--hims" in sys.argv  # off by default: doubles the run on a slow FAA server

LOOKUPS_JS = "async () => (await fetch('/designeeapi/api/LookupValues/init/anonymous')).json()"

# The body the page's Search button posts (captured 2026-10-27); only stateId, himsAME
# and the paging change here.
SEARCH_JS = """
async ({stateId, countryId, typeId, hims, first, rows}) => {
  const body = {statuses: [], selectedFunctionCodes: [],
    pageModel: {first, rows, sortOrder: 1, filters: {}, globalFilter: null},
    isInternal: false, countryId, designeeTypeId: typeId, isLocationSearch: true,
    firstName: null, lastName: null, designator: null, city: null, county: null,
    stateId, zipCode: null, firstClassAME: false, secondThirdClassAME: false,
    examinerAME: false, himsAME: hims, male: false, female: false};
  const r = await fetch('/designeeapi/api/Cloa/Search/', {method: 'POST',
    headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)});
  if (!r.ok) return {error: r.status};
  return await r.json();
}
"""


def fmt_zip(z):
    d = re.sub(r"\D", "", z or "")
    if len(d) == 9 and not d.endswith("0000"):
        return f"{d[:5]}-{d[5:]}"
    return d[:5] if len(d) >= 5 else (z or "").strip()


def fmt_phone(p):
    d = re.sub(r"\D", "", p or "")
    return f"({d[:3]}) {d[3:6]}-{d[6:]}" if len(d) == 10 else (p or "").strip()


def flatten(rec, hims_numbers):
    a = rec.get("address") or {}
    state = (a.get("state") or {}).get("name") or ""
    country = (a.get("country") or {}).get("name") or ""
    return {
        "designee_number": rec.get("designeeNumber") or "",
        "name": (rec.get("fullName") or "").strip(),
        "class": rec.get("classType") or "",
        "status": rec.get("status") or "",
        "hims": rec.get("designeeNumber") in hims_numbers,
        "practice": (a.get("name") or "").strip(),
        "address1": (a.get("address1") or "").strip(),
        "address2": (a.get("address2") or "").strip(),
        "city": (a.get("city") or "").strip(),
        "county": (a.get("county") or "").strip(),
        "state": state,
        "zip": fmt_zip(a.get("zipCode")),
        "country": country,
        "phone": fmt_phone(rec.get("phoneNumber") or a.get("phoneNumber")),
        "email": (rec.get("email") or a.get("email") or "").strip(),
        "faa_office": rec.get("officeName") or "",
        "gender": rec.get("gender") or "",
    }


async def search_all(page, ids, state_id, hims):
    """Every record for one state, paging until the site's own total is reached."""
    rows, first, out = 250, 0, []
    while True:
        res = None
        for attempt in range(2):
            res = await page.evaluate(SEARCH_JS, {**ids, "stateId": state_id, "hims": hims,
                                                  "first": first, "rows": rows})
            if "error" not in res:
                break
            await page.wait_for_timeout(5000)
        if "error" in res:
            raise RuntimeError(f"HTTP {res['error']}")
        out.extend(res.get("data") or [])
        total = res.get("total") or 0
        if len(out) >= total or not res.get("data"):
            return out, total
        first += rows
        await page.wait_for_timeout(PAUSE_MS)


async def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    started = datetime.now(timezone.utc).isoformat(timespec="seconds")
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=HEADLESS)
        page = await browser.new_page()
        print("Opening the FAA Designee Locator ...", flush=True)
        await page.goto(LOCATOR, wait_until="domcontentloaded")

        # The landing page is ".../#/designeeLocator"; the search page is ".../designeeLocator"
        # (no hash). "Find Designees" first shows the FAA System Use Notice; after "I Agree"
        # the landing page comes back and needs "Find Designees" once more.
        def on_search(url):
            return "#/" not in url and url.rstrip("/").endswith("/designeeLocator")

        # MEASURED 2026-10-27: in a fresh browser the FAA System Use Notice opens ON LOAD and
        # its mask blocks every other click, so it is dismissed first. "I Agree" is a real
        # <button> (span label inside). Ryan's approach: a normal click, then a JS click.
        agreed = False
        try:
            await page.locator('button:has-text("I Agree")').first.click(timeout=15000)
            agreed = True
        except Exception:
            agreed = await page.evaluate("""() => {
                const b = [...document.querySelectorAll('button')].find(b => b.innerText.includes('I Agree'));
                if (b) { b.click(); return true; } return false; }""")
        if agreed:
            await page.locator(".p-dialog-mask").first.wait_for(state="hidden", timeout=10000)
            print("Accepted the FAA System Use Notice.", flush=True)

        for _ in range(3):
            if on_search(page.url):
                break
            await page.get_by_text("Find Designees").first.click()
            try:
                await page.wait_for_url(on_search, timeout=15000)
            except Exception:
                pass
        if not on_search(page.url):
            raise SystemExit(f"Could not reach the Designee Locator search page (at {page.url})")
        print("On the search page.", flush=True)

        lookups = await page.evaluate(LOOKUPS_JS)
        type_id = next(t["id"] for t in lookups["designeeTypes"] if t.get("code") == "AME")
        country_id = next(c["id"] for c in lookups["countries"] if c.get("name") == "United States")
        ids = {"countryId": country_id, "typeId": type_id}
        # The 50 states and DC first, then territories and military mail codes.
        others = {"AE", "AP", "Guam", "American Samoa", "Marshall Islands", "North Mariana Islands",
                  "US Minor Outlying Islands", "Puerto Rico", "Virgin Islands"}
        states = sorted((s for s in lookups["states"] if s.get("name") not in ("N/A",)),
                        key=lambda s: (s["name"] in others, s["name"]))

        # 🚨 SAVED AS IT GOES, RESUMED ON RESTART (Ryan 10/27: "Why are you searching states
        # ... we already did"). Every finished state is written to ame_progress.json at once;
        # a rerun skips those. Delete that file (or pass --fresh) for a new monthly pull.
        progress_path = OUT_DIR / "ame_progress.json"
        progress = {}
        if progress_path.exists() and "--fresh" not in sys.argv:
            progress = json.loads(progress_path.read_text())
        todo = [s for s in states if s["name"] not in progress]
        print(f"{len(states)} states and territories; {len(progress)} already saved, "
              f"{len(todo)} to collect.\n", flush=True)

        # ⏱️ 4 STATES AT A TIME (Ryan 10/27, "now"). MEASURED: a search takes ~13 s from a
        # normal browser and up to ~3 min from this automated one, so one-at-a-time was ~3 h.
        # Four in flight is still light use of a public site. Each finished state is saved
        # immediately (asyncio runs one task at a time between awaits, so no write races).
        failures, done = [], [0]
        gate = asyncio.Semaphore(CONCURRENCY)

        async def collect(st):
            async with gate:
                try:
                    recs, total = await search_all(page, ids, st["id"], hims=False)
                    hims_numbers = []
                    if WITH_HIMS:  # a second request per state; the FAA also publishes its HIMS list
                        hims_recs, _ = await search_all(page, ids, st["id"], hims=True)
                        hims_numbers = sorted({r.get("designeeNumber") for r in hims_recs})
                    progress[st["name"]] = {"records": recs, "hims": hims_numbers, "total": total}
                    tmp = progress_path.with_suffix(".tmp")
                    tmp.write_text(json.dumps(progress))
                    tmp.replace(progress_path)
                    done[0] += 1
                    hims_note = f" ({len(hims_numbers)} HIMS)" if WITH_HIMS else ""
                    print(f"[{done[0]:>2}/{len(todo)}] {st['name']}: {len(recs)} AMEs{hims_note}, saved"
                          f"{'' if len(recs) == total else f'  site total {total}'}", flush=True)
                except Exception as e:
                    failures.append(st["name"])
                    print(f"[--/{len(todo)}] {st['name']}: FAILED ({e}); rerun to retry it", flush=True)
                await asyncio.sleep(PAUSE_MS / 1000)

        await asyncio.gather(*(collect(st) for st in todo))
        await browser.close()

    rows, raw = [], {}
    for name, entry in progress.items():
        raw[name] = entry["records"]
        hims_set = set(entry.get("hims") or [])
        rows.extend(flatten(r, hims_set) for r in entry["records"])

    # One row per AME per practice address.
    seen, unique = set(), []
    for r in rows:
        key = (r["designee_number"], r["address1"].upper(), r["zip"])
        if key not in seen:
            seen.add(key)
            unique.append(r)
    unique.sort(key=lambda r: (r["state"], r["city"], r["name"]))
    ames = len({r["designee_number"] for r in unique})

    out = {
        "last_updated": started,
        "source": "FAA Designee Locator (designee.faa.gov), AME location search by state",
        "count_rows": len(unique),
        "count_ames": ames,
        "count_hims": len({r["designee_number"] for r in unique if r["hims"]}),
        "states_failed": failures,
        "ames": unique,
    }
    (OUT_DIR / "ame_database.json").write_text(json.dumps(out, indent=2))
    (OUT_DIR / "ame_raw.json").write_text(json.dumps(raw, indent=1))
    if unique:
        with (OUT_DIR / "ame_database.csv").open("w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(unique[0].keys()))
            w.writeheader()
            w.writerows(unique)
    print(f"\nDone: {ames} AMEs ({len(unique)} practice addresses), "
          f"{out['count_hims']} HIMS, {len(failures)} states failed.", flush=True)
    print(f"Saved to {OUT_DIR}", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
