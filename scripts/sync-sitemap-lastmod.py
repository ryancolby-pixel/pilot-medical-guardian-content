#!/usr/bin/env python3
"""Rewrite every <lastmod> in sitemap.xml from git history.

WHY THIS EXISTS. On 2026-08-06 all 9 URLs in sitemap.xml were declaring a
lastmod that was three to four weeks stale. The homepage said 2026-07-12
while index.html had been committed six times since, most recently that day.
Nobody had bumped a date by hand since 7/31, which is exactly what happens to
a hand-maintained date field.

WHY IT MATTERS, AND WHY IT MATTERS LESS THAN IT SOUNDS. Google's documented
position is that it uses lastmod only if the value is "consistently and
verifiably accurate," and Gary Illyes has put it more bluntly: trust in the
signal is binary, either they trust the file or they don't. So a half-fixed
sitemap buys nothing. That cuts both ways. It is why this script does all
nine at once rather than the page you happen to be editing, and it is also
why nobody should expect a ranking change from running it. John Mueller has
said plainly that hand-bumping lastmod is not a recrawl hack. The reason to
be accurate here is that it costs nothing to be accurate.

Note that Google ignores <changefreq> and <priority> entirely. They are left
in the file because removing them changes nothing either way.

USAGE
    python3 scripts/sync-sitemap-lastmod.py          # rewrite in place
    python3 scripts/sync-sitemap-lastmod.py --check  # report drift, exit 1

Run --check before a content push. The date used is the last commit that
touched that file, so run this AFTER committing the content change, or the
new commit will not be reflected yet.
"""

import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SITEMAP = REPO / "sitemap.xml"
ENTRY = re.compile(
    r"(<loc>https://pilotmedicalguardian\.com)([^<]*)</loc>(\s*)<lastmod>([^<]+)</lastmod>"
)


class ShallowCloneError(RuntimeError):
    """The repo is shallow, so per-file history is not merely missing but WRONG."""


def assert_full_history() -> None:
    """Refuse to run against a shallow clone.

    This is checked up front with `git rev-parse --is-shallow-repository` rather
    than inferred from an empty `git log`, because an empty log NEVER happens here
    and reasoning from that assumption produced a guard that did not fire.

    What a shallow clone actually does: `git clone --depth 1` fetches a single
    grafted commit that CONTAINS EVERY FILE. So `git log -1 -- <any file>` returns
    that commit, successfully, for all of them. The failure mode is not a missing
    date. It is nine confidently wrong dates, all equal to the head commit, written
    into a file whose entire purpose is telling Google when each page really
    changed. Verified by cloning this repo at --depth 1 on 2026-08-06: all nine
    URLs came back stamped with that day.

    A wrong date is worse than a stale one. Google's documented position is that it
    uses lastmod only when the value is verifiably accurate, and Gary Illyes has
    said trust in it is binary. Stamping every page as changed on every deploy is
    the fastest way to spend that trust.
    """
    out = subprocess.run(
        ["git", "rev-parse", "--is-shallow-repository"],
        cwd=REPO, capture_output=True, text=True,
    ).stdout.strip()
    if out == "true":
        raise ShallowCloneError(
            "this is a SHALLOW clone, so every file would be dated to the single "
            "fetched commit. In GitHub Actions set `fetch-depth: 0` on "
            "actions/checkout; locally run `git fetch --unshallow`."
        )


def last_commit_date(loc_path: str) -> str | None:
    """Date of the last commit touching the file this URL serves."""
    filename = "index.html" if loc_path == "/" else loc_path.lstrip("/")
    if not (REPO / filename).exists():
        print(f"  WARNING: {loc_path} maps to {filename}, which does not exist")
        return None
    out = subprocess.run(
        ["git", "log", "-1", "--format=%ad", "--date=format:%Y-%m-%d", "--", filename],
        cwd=REPO, capture_output=True, text=True,
    ).stdout.strip()
    if not out:
        print(f"  WARNING: git knows no commit for {filename}; leaving its date alone")
        return None
    return out


def main() -> int:
    check_only = "--check" in sys.argv

    try:
        assert_full_history()
    except ShallowCloneError as exc:
        print(f"REFUSING TO RUN: {exc}")
        return 3

    text = SITEMAP.read_text()
    drift = []

    def replace(match: re.Match) -> str:
        prefix, loc, gap, declared = match.groups()
        actual = last_commit_date(loc)
        if not actual or actual == declared:
            return match.group(0)
        drift.append((loc, declared, actual))
        return f"{prefix}{loc}</loc>{gap}<lastmod>{actual}</lastmod>"

    updated = ENTRY.sub(replace, text)

    if not drift:
        print("sitemap.xml lastmod dates are accurate, nothing to do")
        return 0

    for loc, declared, actual in drift:
        print(f"  {loc:<32} {declared} -> {actual}")

    if check_only:
        print(f"{len(drift)} stale lastmod value(s). Run without --check to fix.")
        return 1

    # Never write a file that would not parse. A malformed sitemap is worse
    # than a stale one: Google drops the whole file, not the bad entry.
    try:
        ET.fromstring(updated)
    except ET.ParseError as exc:
        print(f"REFUSING TO WRITE: result is not valid XML ({exc})")
        return 2

    SITEMAP.write_text(updated)
    print(f"updated {len(drift)} lastmod value(s) in sitemap.xml")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
