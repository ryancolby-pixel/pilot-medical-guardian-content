#!/usr/bin/env python3
"""The one way this repo stamps `envelope.lastVerified`.

WHY THIS EXISTS
---------------
`lastVerified` means exactly one thing: THE MOMENT SOMEONE ACTUALLY COMPARED AN ENTRY
AGAINST THE FAA SOURCE IT CITES. It is the last honest freshness signal the content has,
after `reviewStatus: "reviewed"` was stripped for asserting a review no AME ever performed.

It is also load-bearing for tooling. Both `check-cdn-drift.py` and `sync-bundle-from-cdn.py`
decide "does this branch hold work nobody published?" by comparing the newest stamp on each
side. That comparison is strict, so TWO COPIES CARRYING THE SAME STAMP ARE INDISTINGUISHABLE.

🚨 AND THAT TIE WAS THE COMMON CASE. Measured 2026-08-17: **406 of 655 published entries
sit at a bare `T00:00:00Z`**, and every one of the 11 content files was AT equality with the
app bundle. A rewrite made on the same calendar day moved nothing either tool could read.
Proven by harness: 81 rewritten SI requirement texts with the stamp untouched made the drift
check exit 0 while printing the instruction that destroys them, and made the sync script
overwrite them outright.

Second precision is what closes that: two independent verification passes do not land on the
same second, so the newer copy is always identifiable.

🚫 WHAT THIS DOES *NOT* DO — AND MUST NOT.
The 406 historical midnight stamps are NOT rewritten to add seconds. Nobody recorded a time
for them; the record is a DATE. Inventing `T14:23:11Z` where the evidence says "2026-08-14"
would fabricate precision we never had, which is the same species of error as the fabricated
date of birth (2026-07-19) and as bumping `lastVerified` without redoing the comparison.
**A stamp is a claim about work someone did. Do not manufacture one.**
Those entries become second-precision the next time somebody genuinely re-verifies them.

USAGE
-----
    from content_time import now_stamp, is_day_only
    entry["envelope"]["lastVerified"] = now_stamp()
"""
from datetime import datetime, timezone

# The format every stamp in v1/ uses: ISO-8601, UTC, second precision, trailing Z.
STAMP_FORMAT = "%Y-%m-%dT%H:%M:%SZ"


def now_stamp() -> str:
    """The current instant, to the second, in the repo's canonical stamp format.

    Microseconds are dropped deliberately: they add no distinguishing power a second does
    not already give, and they make hand-comparing two stamps harder than it needs to be.
    """
    return datetime.now(timezone.utc).strftime(STAMP_FORMAT)


def is_day_only(stamp: str) -> bool:
    """True for a stamp carrying no time of day, e.g. `2026-08-14T00:00:00Z`.

    Midnight-UTC is treated as day-only rather than as a real instant. That loses the
    vanishingly rare genuine midnight verification, and it is the right trade: a stamp
    indistinguishable from "no time recorded" should be handled as if none were.

    ⚠️ It is also the value that renders WRONG. A `T00:00:00Z` stamp formatted in local time
    shows the PREVIOUS DAY everywhere west of UTC — measured in America/New_York,
    America/Chicago and America/Denver, i.e. every pilot this app has. The app now formats
    every provenance date in UTC (`ReferenceEnvelope.verifiedDateStyle`), so the display is
    correct regardless; this is a second reason not to author new ones.
    """
    return isinstance(stamp, str) and stamp.endswith("T00:00:00Z")
