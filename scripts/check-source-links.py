#!/usr/bin/env python3
"""Check that every FAA source we cite still resolves.

WHY THIS EXISTS. On 2026-08-07 three cited URLs were found to be 404, covering 176 of
the 622 reference entries the app ships. They had rotted silently when the FAA
reorganised its site, and nothing noticed. The app's promise, and the answer published
on the public site the same morning, is that where it describes an FAA rule in its own
words it names the FAA document and links straight to it "so you can read the original
and judge for yourself whether I summarized it fairly". A dead link makes that hollow,
and a pilot who takes us up on it gets a page-not-found instead of the FAA.

The existing watchers cover different ground: check-faa-caci-pdfs.yml and
check-faa-hims-pdf.yml track whether specific FAA PDFs have been REISSUED (by SHA), and
cdn-drift-check.py (app repo) tracks whether the CDN and the app bundle agree. Neither
asks the simplest question: is the thing we point at still there?

WHAT IT CHECKS
  - every envelope.sourceURL in v1/*.json (the reference content the app loads)
  - every external faa.gov / ecfr.gov link in the published site's HTML

A redirect is reported but not treated as a failure: the FAA redirects freely and a 301
to a live page is fine. It is surfaced because a redirect is often the first sign that a
section moved, and the destination is worth a look before it becomes a 404.

USAGE
    python3 scripts/check-source-links.py            # check everything, exit 1 on any dead link
    python3 scripts/check-source-links.py --quiet     # only print problems
"""

import glob
import hashlib
import json
import pathlib
import re
import sys
import time
import subprocess
from collections import defaultdict

ROOT = pathlib.Path(__file__).resolve().parent.parent
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")
TIMEOUT = 30
PAUSE = 0.4  # be polite to faa.gov; 66 URLs at this rate is under a minute

QUIET = "--quiet" in sys.argv


def cited_urls() -> dict[str, set[str]]:
    """Every URL we point a pilot at, mapped to the places that cite it."""
    where: dict[str, set[str]] = defaultdict(set)

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
            url = (entry.get("envelope") or {}).get("sourceURL")
            if url:
                where[url].add(name)

    # The published site cites the FAA directly too, and those rot the same way.
    for path in sorted(glob.glob(str(ROOT / "*.html"))):
        name = pathlib.Path(path).name
        text = pathlib.Path(path).read_text()
        for url in re.findall(r'href="(https://(?:www\.)?(?:faa\.gov|ecfr\.gov)[^"]*)"', text):
            where[url].add(name)

    return where


def check(url: str) -> tuple[int | str, str | None]:
    """Return (status, final_url_if_redirected).

    Uses curl rather than urllib DELIBERATELY. urllib's certificate handling differs
    between this Mac and the GitHub runner, and the first version of this script reported
    all 84 sources dead locally because Python had no CA bundle while curl fetched every
    one of them fine. A checker you cannot run on the machine you are writing it on is a
    checker you cannot verify, and an unverified checker is how a false alarm ships.

    An int means the server ANSWERED and that is the answer. A string means we could not
    reach it, which says nothing about whether the FAA still hosts the page. Conflating
    the two is what turns an alert into noise.
    """
    cmd = ["curl", "-s", "-o", "/dev/null", "-A", UA, "-L",
           "--max-time", str(TIMEOUT), "-w", "%{http_code} %{url_effective}", url]

    # 🚨 5xx IS RETRIED, AND THAT IS A COVERAGE FIX, NOT A FALSE-ALARM FIX (2026-08-24, later).
    #
    # Routing 5xx to `unchecked` (below) stopped the checker CRYING WOLF. It did not make the
    # URL checked. eCFR 503s deep section pages constantly, so those citations landed in
    # `unchecked` on every single run — permanently unverified, and REAL link rot on them would
    # have been invisible. A watcher that always says "could not tell" about the same four URLs
    # is not watching them (`GOTCHAS_VERIFY §12`: a watcher only catches the axis it measures).
    #
    # MEASURED on 2026-08-24 from a residential connection, which is the point: single-shot gave
    #     503  .../part-61/section-61.113
    #     503  .../part-68/section-68.3
    #     503  .../title-14/section-68.3
    # and the SAME three returned 200 with 75-83KB of real content under retry-with-backoff.
    # Controlled first, because "eCFR is down" and "this page is gone" look identical: the eCFR
    # root and /current/title-14 both answered 200 throughout, so the service was up and only
    # deep pages were shedding load.
    #
    # 🚫 403/429 are NOT retried. Those are a bot wall saying no on purpose, and hammering it is
    # both useless and rude. They stay `unchecked` on the first answer.
    RETRYABLE_ATTEMPTS = 4
    last_code = None
    for attempt in range(RETRYABLE_ATTEMPTS):
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=TIMEOUT + 15)
        except subprocess.TimeoutExpired:
            if attempt < RETRYABLE_ATTEMPTS - 1:
                time.sleep(2 * (attempt + 1))
                continue
            return "unchecked: timeout", None
        if r.returncode != 0:
            if attempt < RETRYABLE_ATTEMPTS - 1:
                time.sleep(2 * (attempt + 1))
                continue
            return f"unchecked: curl exit {r.returncode}", None
        parts = r.stdout.strip().split(" ", 1)
        code = int(parts[0]) if parts and parts[0].isdigit() else 0
        final = parts[1] if len(parts) > 1 else url
        if code == 0:
            if attempt < RETRYABLE_ATTEMPTS - 1:
                time.sleep(2 * (attempt + 1))
                continue
            return "unchecked: no status", None
        if 500 <= code <= 599 and attempt < RETRYABLE_ATTEMPTS - 1:
            last_code = code
            time.sleep(2 * (attempt + 1))
            continue
        return code, (final if final.rstrip("/") != url.rstrip("/") else None)
    # Exhausted the retries still 5xx. Report the real code so `unreachable_reason` files it
    # as unchecked rather than dead - the distinction the 2026-08-24 false alarm turned on.
    return (last_code if last_code is not None else "unchecked: unknown"), None


# Status codes that mean "we did not get an answer ABOUT THE RESOURCE", as opposed to
# "the FAA no longer hosts this".
#
# 🚨 THIS EXISTS BECAUSE THE CHECKER CRIED WOLF ON 2026-08-24. It filed a report naming four
# eCFR URLs as no longer resolving, with status 503. All four returned **200** when fetched
# from a residential connection minutes later. eCFR serves 5xx to datacenter IP ranges, which
# is every GitHub Actions runner (`GOTCHAS_VERIFY §13`, `GOTCHAS_CONTENT §7`). Nothing was
# wrong with the citations; a pilot following them got the page.
#
# ⚖️ The docstring on `check()` already states the principle this got wrong: "An int means the
# server ANSWERED and that is the answer." That is true of 404. It is NOT true of 503, which is
# the server answering about ITSELF. Same for 403 and 429, which are how a bot wall says no.
# Only 4xx-that-means-gone is link rot.
#
# 🚫 Do NOT "fix" a future false alarm by muting the workflow or widening this to all 4xx. A
# 404 or 410 on a cited FAA source is the exact thing this check exists to catch.
UNREACHABLE_CODES = {403, 429}


def unreachable_reason(status: "int | str") -> str | None:
    """Why this status tells us nothing about the resource, or None if it does tell us."""
    if isinstance(status, str):
        return status if status.startswith("unchecked") else None
    if status in UNREACHABLE_CODES:
        return f"unchecked: HTTP {status} - blocked or rate-limited, not link rot"
    if 500 <= status <= 599:
        return f"unchecked: HTTP {status} - server unavailable, not link rot"
    return None


def _selftest() -> int:
    """Negative controls alongside the positive ones.

    ⚖️ A control is only valid if it is tested against KNOWN-BAD input (`GOTCHAS_VERIFY §13`).
    The bug this replaces would have passed any test that only fed it 200s and 404s.
    """
    cases = [
        # (status, should_be_unreachable, label)
        (200, False, "200 is a live page"),
        (404, False, "404 IS link rot and must still fail the run"),
        (410, False, "410 IS link rot and must still fail the run"),
        (503, True,  "503 is the eCFR datacenter block that caused the 2026-08-24 false alarm"),
        (500, True,  "500 is a server fault"),
        (502, True,  "502 is a gateway fault"),
        (403, True,  "403 is a bot wall"),
        (429, True,  "429 is rate limiting"),
        ("unchecked: timeout", True, "transport failure"),
    ]
    bad = 0
    for status, expect_unreachable, label in cases:
        got = unreachable_reason(status) is not None
        ok = got == expect_unreachable
        print(f"  {'ok  ' if ok else 'FAIL'}  {str(status):<22} {label}")
        if not ok:
            bad += 1
    print()
    if bad:
        print(f"{bad} selftest case(s) FAILED")
        return 1
    print(f"all {len(cases)} selftest cases pass")
    return 0


def main() -> int:
    urls = cited_urls()
    dead: list[str] = []
    unchecked: list[str] = []
    redirected: list[str] = []

    if not QUIET:
        print(f"checking {len(urls)} distinct cited URLs\n")

    for url in sorted(urls):
        status, final = check(url)
        cites = ", ".join(sorted(urls[url]))
        reason = unreachable_reason(status)
        if reason:
            unchecked.append(f"- `{url}` ({reason}), cited by: {cites}")
            print(f"  {'?':<6} UNCHECKED  {url}  ({reason})")
        elif status != 200:
            dead.append(f"- `{url}`\n    - status: **{status}**\n    - cited by: {cites}")
            print(f"  {status:<6} DEAD  {url}\n           cited by: {cites}")
        else:
            if final:
                redirected.append(f"- `{url}`\n    - now redirects to `{final}`\n    - cited by: {cites}")
            if not QUIET:
                print(f"  200    ok    {url}{'  (redirects)' if final else ''}")
        time.sleep(PAUSE)

    print()
    if redirected:
        print(f"{len(redirected)} cited URL(s) redirect. Not a failure, but worth a look:")
        for r in redirected:
            print("  " + r.splitlines()[0].strip("- "))
        print()

    # If we could not reach ANYTHING, the checker is broken, not the FAA. Say so plainly and
    # fail on that, rather than filing a report claiming every source has vanished.
    if unchecked and not dead and len(unchecked) == len(urls):
        print(f"COULD NOT CHECK ANY of the {len(urls)} URLs. This is a problem with this "
              f"runner (TLS, DNS or network), not with the citations. No report written.")
        for u in unchecked[:3]:
            print("  " + u)
        return 2

    if unchecked:
        print(f"{len(unchecked)} URL(s) could not be checked (transport failures, not 404s):")
        for u in unchecked:
            print("  " + u)
        print()

    if not dead:
        print(f"All {len(urls) - len(unchecked)} reachable cited sources resolve.")
        return 0

    entries_affected = sum(1 for _ in dead)
    report = [
        "One or more FAA sources the app cites no longer resolve.",
        "",
        "A pilot who follows the citation to read the FAA's original gets a page-not-found. "
        "That undercuts the promise the app and the website both make about naming the source.",
        "",
        *dead,
    ]
    if redirected:
        report += ["", "Redirects (not failures, but the FAA may be reorganising these):", *redirected]
    report += [
        "",
        "**Fix:** find the current FAA location for each, verify the replacement actually covers "
        "the subject the citing entries assert (a URL that merely returns 200 is not enough), then "
        "update `envelope.sourceURL` in the affected `v1/*.json` files and push. The manifest "
        "rebuilds itself.",
    ]
    # A stable fingerprint of WHICH urls are dead, so the workflow can tell a new failure
    # from the same known one it already reported. Weekly re-notification about a problem
    # already filed is how an alert trains its reader to ignore it.
    dead_urls = sorted(re.findall(r"`(https?://[^`]+)`", "\n".join(dead)))
    fingerprint = hashlib.sha256("\n".join(dead_urls).encode()).hexdigest()[:16]
    (ROOT / "source-link-report.md").write_text(
        "\n".join(report) + f"\n\n<!-- fingerprint:{fingerprint} -->\n")
    (ROOT / "source-link-fingerprint.txt").write_text(fingerprint + "\n")

    print(f"{len(dead)} cited source(s) are dead. Wrote source-link-report.md")
    return 1


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        raise SystemExit(_selftest())
    raise SystemExit(main())
