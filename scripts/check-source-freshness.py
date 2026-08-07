#!/usr/bin/env python3
"""Notice when an FAA page we cite has been UPDATED, while its URL still works.

WHY THIS EXISTS, and why the existing link checker cannot do it.

On 2026-08-07 an audit found the app telling post-cardiac-event pilots to get annual
functional cardiac testing "such as a stress test". The FAA had published the opposite,
in a highlighted note on the page we cite:

    "NOTE: As of 05/29/24 - For routine cases, follow-up stress test is no longer
     required provided ALL items on the CHD/CAD Recertification Status Summary are in
     the 'YES' column."
    https://www.faa.gov/ame_guide/special_iss/third_class/chd

That change was 26 months old. The URL never moved, so check-source-links.py passed it
every single week, correctly: it asks whether the page is THERE, not whether it still
says what we claim. A pilot following our checklist was booking a yearly nuclear stress
test nobody had required since 2024.

THE MECHANISM. The FAA publishes its own change signal. Every ame_guide page carries a
"Last updated: <weekday>, <Month> <D>, <YYYY>" line, and it is trustworthy: the CHD page
reads "Last updated: Wednesday, May 29, 2024", the exact date of the rule change above.
Had anything been watching that one field, we would have caught this the week it landed.

So we record the FAA's date per cited URL and speak up when it moves. We do NOT hash the
page. A whole-page hash fires on nav tweaks, banners and build timestamps, which means
weekly noise, and a noisy alert is worse than none: it teaches its reader to ignore it.
That lesson is already written into check-source-links.yml and it applies double here.
Four of the eight pages sampled while designing this had not moved since 2023, so the
real-world signal rate is low and every firing means something.

WHAT THIS CANNOT DO. It tells you WHEN to look. It never tells you WHAT to conclude.
Deciding whether our sentence still fairly summarises a changed FAA page is a human
reading the two side by side. What this buys is that the human re-reads the 2 pages that
moved this month instead of re-reading all 65.

It also cannot catch text that was WRONG WHEN WRITTEN. There is no change to detect. The
2026-08-07 audit exists for that, and no watcher replaces it.

THE REGISTRY lives at repo root, deliberately NOT in v1/. gen_manifest.py builds the
manifest from v1/*.json only, so a file here cannot enter the manifest, cannot bump
generatedAt, and cannot reach a pilot's device. This is our bookkeeping, not content.

USAGE
    python3 scripts/check-source-freshness.py --seed    # record today's dates, no alerts
    python3 scripts/check-source-freshness.py           # compare; exit 1 if anything moved
    python3 scripts/check-source-freshness.py --quiet   # only print problems
"""

import glob
import hashlib
import json
import pathlib
import re
import subprocess
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone

ROOT = pathlib.Path(__file__).resolve().parent.parent
REGISTRY = ROOT / "source-dates.json"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")
TIMEOUT = 30
PAUSE = 0.4  # polite to faa.gov

SEED = "--seed" in sys.argv
QUIET = "--quiet" in sys.argv

# "Last updated: Wednesday, May 29, 2024"
DATE_RE = re.compile(
    r"Last\s+updated:\s*(?:[A-Za-z]+day,\s*)?([A-Za-z]+\s+\d{1,2},\s*\d{4})", re.I)


def cited_urls() -> dict[str, dict[str, list[str]]]:
    """URL -> {filename: [entry codes]}.

    Entry codes matter: when a page moves, the actionable output is "these named entries
    cite it, go re-read them", not just "a page changed".
    """
    where: dict[str, dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))
    for path in sorted(glob.glob(str(ROOT / "v1" / "*.json"))):
        name = pathlib.Path(path).name
        if name == "manifest.json":
            continue
        try:
            data = json.loads(pathlib.Path(path).read_text())
        except json.JSONDecodeError:
            continue
        if not isinstance(data, list):
            continue
        for entry in data:
            env = entry.get("envelope") or {}
            url, code = env.get("sourceURL"), env.get("code")
            if url:
                where[url][name].append(code or "?")
    return {u: dict(v) for u, v in where.items()}


def fetch_updated(url: str) -> tuple[str | None, str | None]:
    """Return (iso_date, error).

    curl, not urllib, for the same reason check-source-links.py uses it: urllib's cert
    handling differs between this Mac and the runner, and the first version of that script
    reported all 84 sources dead locally while curl fetched every one. A checker you cannot
    run on the machine you write it on is a checker you cannot verify.

    error is non-None ONLY for transport failures. A page that simply publishes no date is
    (None, None) -- that is a fact about the page, not a fault, and must never alarm.
    """
    # A PDF is bytes, not text, and several cited sources ARE PDFs (the AASI worksheets).
    # Skipping them is honest rather than lazy: a PDF carries no "Last updated:" line, and
    # the CACI/HIMS SHA checkers already watch PDFs for reissue, which is the right
    # mechanism for a binary. Found by RUNNING this: text=True died on the first one with
    # a UnicodeDecodeError mid-seed.
    if url.lower().endswith(".pdf"):
        return None, None

    cmd = ["curl", "-s", "-A", UA, "-L", "--max-time", str(TIMEOUT), url]
    for attempt in range(2):
        try:
            # bytes, then decode defensively. faa.gov serves stray non-UTF-8 in places and
            # a decode error must not take down a check of 65 pages.
            r = subprocess.run(cmd, capture_output=True, timeout=TIMEOUT + 15)
        except subprocess.TimeoutExpired:
            if attempt == 0:
                time.sleep(2)
                continue
            return None, "timeout"
        if r.returncode != 0 or not r.stdout:
            if attempt == 0:
                time.sleep(2)
                continue
            return None, f"curl exit {r.returncode}"
        text = r.stdout.decode("utf-8", errors="replace")
        body = re.sub(r"<script.*?</script>|<style.*?</style>", " ", text, flags=re.S)
        body = re.sub(r"<[^>]+>", " ", body)
        body = re.sub(r"\s+", " ", body)
        m = DATE_RE.search(body)
        if not m:
            return None, None
        try:
            return datetime.strptime(m.group(1).replace(",", ""), "%B %d %Y").date().isoformat(), None
        except ValueError:
            return None, None
    return None, "unknown"


def main() -> int:
    urls = cited_urls()
    prior = {}
    if REGISTRY.exists():
        prior = json.loads(REGISTRY.read_text()).get("sources", {})

    if not QUIET:
        print(f"checking the FAA's own 'Last updated' date on {len(urls)} cited pages\n")

    moved, new, undated, unreachable = [], [], [], []
    record: dict[str, dict] = {}

    for url in sorted(urls):
        iso, err = fetch_updated(url)
        cites = urls[url]
        n = sum(len(v) for v in cites.values())
        was = (prior.get(url) or {}).get("faaLastUpdated")

        if err:
            unreachable.append((url, err))
            # Carry the prior value forward so a flaky week cannot erase our baseline.
            if url in prior:
                record[url] = prior[url]
            print(f"  ?      UNREACHABLE  {url}  ({err})")
            time.sleep(PAUSE)
            continue

        record[url] = {"faaLastUpdated": iso, "entryCount": n,
                       "citedBy": {f: sorted(c) for f, c in sorted(cites.items())}}

        if iso is None:
            undated.append(url)
            if not QUIET:
                print(f"  -      no date published  {url}")
        elif url not in prior:
            new.append((url, iso, n))
            if not QUIET:
                print(f"  new    {iso}  {url}  ({n} entries)")
        elif was != iso:
            moved.append((url, was, iso, cites, n))
            print(f"  MOVED  {was} -> {iso}  {url}  ({n} entries)")
        elif not QUIET:
            print(f"  ok     {iso}  {url}")
        time.sleep(PAUSE)

    # If NOTHING could be fetched, this runner is broken, not the FAA. Say so and write
    # nothing, rather than filing a report claiming every source changed.
    if unreachable and len(unreachable) == len(urls):
        print(f"\nCOULD NOT REACH ANY of the {len(urls)} pages. That is this runner "
              f"(TLS, DNS, network), not the FAA. Registry left untouched.")
        return 2

    watched = sum(1 for v in record.values() if v.get("faaLastUpdated"))
    payload = {
        "_comment": ("What the FAA itself says it last changed each page we cite. Compared "
                     "weekly by scripts/check-source-freshness.py. NOT shipped content: this "
                     "lives outside v1/, so it never enters the manifest or reaches a device."),
        "updated": datetime.now(timezone.utc).replace(microsecond=0, tzinfo=None).isoformat() + "Z",
        "watchedPages": watched,
        "undatedPages": len(undated),
        "sources": dict(sorted(record.items())),
    }

    if SEED:
        REGISTRY.write_text(json.dumps(payload, indent=1) + "\n")
        print(f"\nseeded {len(record)} pages ({watched} publish a date, "
              f"{len(undated)} do not) -> {REGISTRY.name}")
        return 0

    print()
    if undated:
        print(f"{len(undated)} cited page(s) publish no 'Last updated' date, so they cannot "
              f"be watched this way. Mostly PDFs and eCFR, which the PDF SHA checkers cover.")
    if unreachable:
        print(f"{len(unreachable)} page(s) unreachable this run; prior dates kept.")

    if not moved and not new:
        print(f"No cited FAA page has changed. {watched} of {len(urls)} watched.")
        REGISTRY.write_text(json.dumps(payload, indent=1) + "\n")
        return 0

    # New URLs are recorded silently. They are ours (someone added a citation), not the
    # FAA changing something under us, and alerting on our own edits is noise.
    if new and not moved:
        print(f"{len(new)} newly cited page(s) recorded. Nothing has moved.")
        REGISTRY.write_text(json.dumps(payload, indent=1) + "\n")
        return 0

    entries_hit = sum(m[4] for m in moved)
    report = [
        f"The FAA has updated {len(moved)} page(s) we cite. "
        f"{entries_hit} reference entr{'y' if entries_hit == 1 else 'ies'} depend on them.",
        "",
        "The links still work, so the link checker passed. What changed is what the page "
        "SAYS. This is the failure mode that let us tell cardiac pilots to get an annual "
        "stress test for 26 months after the FAA stopped requiring one.",
        "",
    ]
    for url, was, now, cites, n in moved:
        report += [f"- `{url}`", f"    - FAA last updated: **{was} -> {now}**",
                   f"    - {n} entries depend on it:"]
        for fname, codes in sorted(cites.items()):
            report.append(f"        - `{fname}`: {', '.join(f'`{c}`' for c in sorted(codes))}")
        report.append("")
    report += [
        "**What to do.** Open the page, find what changed, and read it against the "
        "`requirementText` of each entry above. Then either confirm ours still holds, or "
        "correct it. A CDN publish reaches every installed build on its next refresh, so "
        "a correction ships the same day with no app build and no App Review.",
        "",
        "**Do not bulk-update the dates to silence this.** The registry is the memory of "
        "what we have actually read. Re-seeding without reading is how this check becomes "
        "the thing it was built to prevent.",
    ]

    fingerprint = hashlib.sha256(
        "\n".join(f"{u}:{n}" for u, _, n, _, _ in moved).encode()).hexdigest()[:16]
    (ROOT / "source-freshness-report.md").write_text(
        "\n".join(report) + f"\n\n<!-- fingerprint:{fingerprint} -->\n")
    (ROOT / "source-freshness-fingerprint.txt").write_text(fingerprint + "\n")

    # Registry is NOT advanced here. It advances only when a human commits the reviewed
    # change, so an unread update keeps firing instead of being silently absorbed.
    print(f"{len(moved)} cited FAA page(s) changed. Wrote source-freshness-report.md")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
