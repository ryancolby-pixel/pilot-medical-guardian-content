#!/usr/bin/env python3
"""Fail when published content has gone too long without being re-read against its source.

WHY THIS EXISTS.

check-content-fidelity.py verifies what we SAID: every quotation and every numeric claim
must appear in the cited source. It cannot verify what we NEVER said, and omission was the
defect class that did the damage on 2026-08-14:

    Item 18v      asked about DWI only; the FAA asks about anything "affecting driving
                  privileges". No quotation, no number, nothing for a checker to test. A
                  pilot whose licence was suspended for points answers No on a form
                  carrying the 18 U.S.C. 1001 falsification notice.
    BasicMed      listed six of the seven conditions in 14 CFR 61.23(c)(3).
    prostate      named two deferral triggers where the FAA names three.

The obligation-coverage heuristic in check-content-fidelity.py points at that gap, but the
only thing that reliably closes it is a human or an agent reading the source and our text
side by side. That is not a regex job, so it cannot be a CI job.

What CI *can* do is refuse to let the absence of that pass stay invisible. Before
2026-08-14, seven content files had NEVER been source-verified by anyone, and nothing
anywhere said so. `ame_directory.json` was serving a snapshot 99 days old, four of whose
AMEs the FAA had since removed from its HIMS list, while the app told pilots on a HIMS
pathway they were HIMS-trained.

So this script watches `envelope.lastVerified` and gets loud when it ages. It does not
check correctness. It checks that somebody looked, recently, and it makes "nobody has
looked at this in five months" a red build instead of a thing nobody knew.

⚠️ lastVerified means ONE thing: the date a person or agent last compared this entry against
the source it cites. It is NOT a review verdict, and it must never be bumped to silence this
check without doing the comparison. Doing that converts the only remaining signal into a
lie, which is exactly what `reviewStatus: "reviewed"` was before it was stripped.

Usage:
    python3 scripts/check-verification-age.py [--max-age-days 120] [--warn-days 90]
"""
import argparse
import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
V1 = ROOT / "v1"

# Files whose content is FAA rules a pilot acts on. These age fastest in consequence, not
# in likelihood: the FAA rarely edits them, but being wrong about one costs a certificate.
CRITICAL = {
    "si_requirements.json", "si_conditions.json", "medications.json",
    "item18.json", "cert_durations.json", "thresholds.json",
    "basicmed_requirements.json", "caci_worksheets.json",
    "regulation_requirements.json", "faa_submission_addresses.json",
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-age-days", type=int, default=120,
                    help="fail above this age (default 120, about two content cycles)")
    ap.add_argument("--warn-days", type=int, default=90)
    args = ap.parse_args()

    now = datetime.now(timezone.utc)
    oldest: dict[str, tuple[int, str]] = {}
    counts: dict[str, dict[int, int]] = defaultdict(lambda: defaultdict(int))

    for path in sorted(V1.glob("*.json")):
        if path.name == "manifest.json":
            continue
        entries = json.loads(path.read_text())
        if not isinstance(entries, list):
            continue
        for e in entries:
            lv = ((e.get("envelope") or {}).get("lastVerified") or "")[:10]
            if not lv:
                continue
            try:
                age = (now - datetime.fromisoformat(lv).replace(tzinfo=timezone.utc)).days
            except ValueError:
                continue
            counts[path.name][age] += 1
            code = (e.get("envelope") or {}).get("code", "?")
            if path.name not in oldest or age > oldest[path.name][0]:
                oldest[path.name] = (age, code)

    failed, warned = [], []
    print(f"{'file':34s} {'entries':>7s} {'oldest':>7s}  status")
    for name in sorted(counts):
        n = sum(counts[name].values())
        age, code = oldest[name]
        if age > args.max_age_days and name in CRITICAL:
            status, bucket = "FAIL", failed
        elif age > args.warn_days:
            status, bucket = "warn", warned
        else:
            status, bucket = "ok", None
        print(f"{name:34s} {n:7d} {age:6d}d  {status}")
        if bucket is not None:
            bucket.append(f"{name}: oldest entry is {age} days old ({code})")

    if warned:
        print(f"\n⚠️  {len(warned)} file(s) approaching the re-verification deadline:")
        for w in warned:
            print("   " + w)
    if failed:
        print(f"\n❌ {len(failed)} file(s) have not been re-read against their FAA sources in "
              f"over {args.max_age_days} days:")
        for f in failed:
            print("   " + f)
        print("\n   This is not a claim that the content is wrong. It is a claim that nobody\n"
              "   has checked, which is the state every one of these files was in on\n"
              "   2026-08-14 when 89 defects were found in the first file anyone looked at.\n"
              "\n   To clear it: re-verify the entries against the sources they cite, correct\n"
              "   what is wrong, and set lastVerified to the date you actually looked.\n"
              "   Bumping the date without doing the comparison turns the last remaining\n"
              "   signal into a lie.")
        Path("verification-age-report.md").write_text(
            "# Content past its re-verification deadline\n\n"
            + "\n".join(f"- {f}" for f in failed)
            + ("\n\n## Approaching\n\n" + "\n".join(f"- {w}" for w in warned) if warned else "")
        )
        return 1
    print("\n✅ every content file has been re-read against its source within "
          f"{args.max_age_days} days.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
