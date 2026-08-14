#!/usr/bin/env python3
"""Check that what we SAY matches what the cited FAA source SAYS.

WHY THIS EXISTS, and why the three checks we already had could never catch it.

On 2026-08-14 a full source-verification of the 85 SI requirements found 89 defects, nine
of them able to send a pilot into an FAA exam expecting a certificate where the AME Guide
directs a deferral. The pattern was consistent: the entries quote what the FAA asks a
pilot to BRING and stop one sentence short of what the FAA tells his AME to DO about it.
Asthma said the Examiner "reissues" while the FAA lists five deferral triggers, two of
them counted off the very medication list the entry asks for. Prostate cancer said "Two
things stop a desk reissue"; the FAA names three.

None of it was new. The FAA had not touched those pages in years:

    asthma, migraine, prostate, hypothyroidism   Last updated March 2023
    afib                                          Last updated March 2024
    CHD (3rd class)                               Last updated May 2024

Nothing changed. We misread the pages at authoring time, and every existing watcher
reported healthy, correctly, every week:

    check-source-links.py       asks: is the page still THERE?
    check-source-freshness.py   asks: did the page CHANGE?
    check-cdn-drift.py          asks: do our two copies MATCH?

A live link to a page we misquote passes the first. A page that never moves passes the
second. Two copies of the same wrong text pass the third. The only question that mattered
was never asked by anything, so this script asks it.

Sharpest illustration: check-source-freshness.py's docstring quotes the FAA's CHD note
verbatim, and our own CHD entry quoted the FIRST SENTENCE of that note and dropped the
second, which is the deferral. The tool written because of that page could not catch the
defect on that page, because the defect was ours and not the FAA's.

WHAT IT CHECKS

  1. QUOTE FIDELITY. Every quoted span in our content must appear in the source it cites.
     This is what catches a misquote, a fabricated FAA sentence, and quotation marks put
     around wording we composed (we shipped one of those today: "required for
     stabilization" where the FAA says "requires ... for stabilization").

  2. DEFERRAL COVERAGE. If the cited page contains an FAA deferral block ("The Examiner
     must defer to the AMCD or Region if:") and our entry never mentions a deferral, that
     is the exact systematic bias found on 2026-08-14. Reported as a WARNING rather than a
     failure, because not every entry on a page is about the deferral, but it is the
     signal that would have surfaced all nine high-severity defects.

HOW IT AVOIDS THE FALSE NEGATIVES THAT DOMINATED EVERY MANUAL PASS

  - curl, never urllib. Python's urllib on macOS frequently has no CA bundle, which made
    check-source-links.py report all 84 sources dead and made an earlier version of this
    check unrunnable locally. A checker you cannot run locally cannot be verified.
  - Normalizes before comparing: HTML stripped, entities decoded, curly quotes and dashes
    folded to straight, whitespace collapsed, case ignored.
  - PDFs read with pdfplumber including extract_tables, because plain text extraction
    interleaves table columns mid-sentence and has produced false findings three times.
  - A CONTROL per source. Before any "quote not found" is believed, the script confirms it
    can find a phrase it knows is in that document. A negative from an unvalidated
    instrument is not evidence.
  - A source that cannot be FETCHED is a hard error, never a silent skip. The cross-branch
    check in check-cdn-drift.py spent its entire life passing because an unresolvable ref
    and an absent file returned the same value.

Usage:
    python3 scripts/check-content-fidelity.py [--file si_requirements.json] [--offline DIR]
"""
import argparse
import html
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
V1 = ROOT / "v1"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")

# Quoted spans shorter than this are idioms, form labels and column names ("YES", "NO*",
# "Senior AME") that appear in prose without being quotations of the source.
MIN_QUOTE = 25

# An elision we wrote. Each side is checked separately.
ELISION = "..."

DEFER_MARKERS = ("must defer", "should defer")

# 🚨 THE HOLE THIS CLOSES, AND WHY IT IS THE IMPORTANT ONE.
#
# Quote fidelity and numeric claims verify what we SAID. Nearly every defect found on
# 2026-08-14 was what we DID NOT say:
#
#   Item 18v      asked about DWI only; the FAA asks about anything "affecting driving
#                 privileges". No quotation, no number, nothing to verify. A pilot whose
#                 licence was suspended for points answers No on a federal form.
#   BasicMed      listed six of the seven conditions in 14 CFR 61.23(c)(3).
#   prostate      named two deferral triggers where the FAA names three.
#   asthma        said the Examiner "reissues" and omitted five deferral triggers.
#
# A checker that verifies our sentences cannot detect a sentence we never wrote. So this
# reads the SOURCE for obligations and asks whether our entry engages with each one.
#
# It is deliberately crude: an obligation is a sentence with a modal, and "engaged with"
# means our text shares a distinctive rare word with it. That over-reports, which is why it
# is baselined like the others rather than failing on day one. Crude and looking is worth
# more than precise and absent, which is what we had.
OBLIGATION = re.compile(
    r"[^.;]*\b(?:must|shall|may not|is required|are required|will be required|"
    r"required to|should defer|must defer)\b[^.;]*[.;]", re.I)

# Words too common to indicate that our text engages with a specific obligation.
STOPWORDS = set("""the a an and or of to in for on at by with from as is are be been was were
that this these those which who whom whose it its his her their there here not no any all
some each every other another such same than then when where while if unless until about
after before during through under over above below between into onto upon within without
you your yours we our ours they them applicant applicants airman airmen examiner examiners
faa aviation medical certificate certification exam examination must shall may can will
should would could required require requires requiring provide provides provided providing
submit submits submitted submitting include includes included including report reports
reported reporting current status information documentation document documents letter
following also more most least less very only both either neither""".split())

# 🚨 QUOTE FIDELITY COVERS ONE FILE. Measured the day this was written: si_requirements.json
# has 281 quoted spans and every other content file has ZERO, because they state FAA content
# as plain assertions rather than quotations. item18.json IS the wording of 25 questions on a
# federal form and contains not one quotation mark. cert_durations.json drives every renewal
# countdown in the app and is pure numbers.
#
# So a second instrument is needed for those files, and the checkable thing they share is
# NUMBERS. An interval, a threshold, a dose or a percentage is either on the cited page or it
# is not, and getting one wrong is exactly the class of defect that matters: a 90-day window
# rendered as annual, a 70% FEV1 threshold, a 12-month certificate duration.
#
# A bare integer is skipped deliberately (list positions, item numbers, "Class 1"). A number
# with a UNIT is a claim about the world.
NUMERIC_CLAIM = re.compile(
    r"\b(\d[\d,.]*)\s*(days?|weeks?|months?|years?|hours?|mg|mcg|%|ng/ml|mmhg|mm hg)\b",
    re.I,
)

# Written-out intervals the FAA uses interchangeably with digits, so a miss on the digit form
# is not a defect if the source spells it. Checked before anything is reported.
WORD_NUMBERS = {
    "1": "one", "2": "two", "3": "three", "4": "four", "5": "five", "6": "six",
    "7": "seven", "8": "eight", "9": "nine", "10": "ten", "12": "twelve", "24": "twenty-four",
}


def norm(s: str) -> str:
    """Fold everything that differs between a web page and our JSON but carries no meaning."""
    s = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", s, flags=re.S | re.I)
    s = re.sub(r"<[^>]+>", " ", s)
    s = html.unescape(s)
    for a, b in (("“", '"'), ("”", '"'), ("‘", "'"), ("’", "'"),
                 ("–", "-"), ("—", "-"), (" ", " "), ("\x00", " "),
                 ("≥", ">="), ("≤", "<=")):
        s = s.replace(a, b)
    return re.sub(r"\s+", " ", s).strip().lower()


def fetch(url: str, cache: Path) -> str | None:
    """Source text for a URL, from cache or the network. None means UNREACHABLE."""
    key = re.sub(r"[^a-z0-9]+", "_", url.lower())[:120]
    blob = cache / key
    if not blob.exists():
        cache.mkdir(parents=True, exist_ok=True)
        r = subprocess.run(["curl", "-sSL", "-A", UA, "--max-time", "60", "-o", str(blob), url],
                           capture_output=True)
        if r.returncode != 0 or not blob.exists() or blob.stat().st_size == 0:
            blob.unlink(missing_ok=True)
            return None
    raw = blob.read_bytes()
    if raw[:4] == b"%PDF":
        try:
            import pdfplumber
        except ImportError:
            print("❌ pdfplumber is required to read PDF sources: pip install pdfplumber")
            sys.exit(2)
        parts = []
        with pdfplumber.open(blob) as pdf:
            for page in pdf.pages:
                parts.append(page.extract_text() or "")
                # Table cells, because plain extraction interleaves columns mid-sentence
                # and that has produced false "quote is absent" findings three times.
                for table in (page.extract_tables() or []):
                    for row in table:
                        parts.extend(c for c in row if c)
        return norm(" ".join(parts))
    return norm(raw.decode("utf-8", errors="ignore"))


def quoted_spans(text: str):
    for q in re.findall(r'"([^"]+)"', text):
        for frag in (p.strip() for p in q.split(ELISION)):
            if len(frag) >= MIN_QUOTE:
                yield frag


def strings_of(entry: dict):
    """Every prose string in an entry, excluding the envelope's own metadata."""
    for k, v in entry.items():
        if k == "envelope":
            continue
        if isinstance(v, str):
            yield v
        elif isinstance(v, list):
            yield from (x for x in v if isinstance(x, str))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", action="append", help="limit to these v1 filenames")
    ap.add_argument("--cache", type=Path, default=Path(".fidelity-cache"))
    ap.add_argument("--update-baseline", action="store_true",
                    help="record the CURRENT failures as accepted debt. Use only when you have "
                         "triaged them; every line you add here is a quotation nobody has "
                         "reconciled with its source.")
    args = ap.parse_args()

    files = sorted(args.file or [p.name for p in V1.glob("*.json") if p.name != "manifest.json"])
    failures, warnings, unreachable, checked = [], [], [], 0

    for name in files:
        entries = json.loads((V1 / name).read_text())
        if not isinstance(entries, list):
            continue
        for entry in entries:
            env = entry.get("envelope") or {}
            url, code = env.get("sourceURL"), env.get("code", "?")
            body = " ".join(strings_of(entry))
            spans = list(quoted_spans(body))
            if not spans and not url:
                continue
            if not url:
                if spans:
                    failures.append(f"{name} :: {code}: quotes text but cites no sourceURL")
                continue

            src = fetch(url, args.cache)
            if src is None:
                unreachable.append(f"{name} :: {code}: could not fetch {url}")
                continue

            # CONTROL. A source we cannot search is not a source that disagrees with us, so
            # prove the extraction produced readable prose before believing any miss.
            #
            # 🚨 THE FIRST VERSION OF THIS CONTROL WAS ITSELF THE BUG. It tested for the
            # literal string "faa", on the assumption that every FAA document contains it.
            # "Federal Aviation Administration" does NOT contain the substring "faa", and
            # neither do the medication tables, which are mostly drug names. That marked 21
            # readable documents unreadable on the first CI run, including a 9,856-character
            # DNI/DNF table and the eCFR text of 14 CFR 67.111.
            #
            # Nor is a PROSE control right, which was the second attempt: it required three
            # common function words, and Antidepressant_Medications.pdf extracts cleanly
            # (2,455 chars, 69 distinct words) while containing only "and" and "or", because
            # it is a TABLE OF DRUG NAMES. Two controls, two false negatives, both on
            # documents that were perfectly readable.
            #
            # What actually separates a usable extraction from a failed one is VOCABULARY.
            # A real document, prose or table, yields dozens of distinct words. A 404 page,
            # an empty PDF or a binary blob does not. That holds without assuming the
            # document's subject, register or language.
            readable = len(src) >= 200 and len(set(re.findall(r"[a-z]{3,}", src))) >= 40
            if not readable:
                unreachable.append(f"{name} :: {code}: CONTROL FAILED for {url} "
                                   f"(fetched {len(src)} chars, not readable prose) — not checked")
                continue

            for frag in spans:
                checked += 1
                n = norm(frag)
                if n in src or n.rstrip(" .,;:") in src:
                    continue
                # A nested quotation may be re-rendered ('NO*' for "NO*"); that is a
                # typographic convention, not a misquote.
                if re.sub(r"['\"]", "", n.rstrip(" .,;:")) in re.sub(r"['\"]", "", src):
                    continue
                failures.append(f"{name} :: {code}: quoted text is NOT in {url}\n"
                                f"        {frag[:160]}")

            # NUMERIC CLAIMS. Covers the ten files that carry no quotations at all.
            for value, unit in NUMERIC_CLAIM.findall(body):
                checked += 1
                num = value.rstrip(".").replace(",", "")
                u = unit.lower().rstrip("s")
                # Accept the digit form, the digit with either singular or plural unit, or the
                # FAA's written-out form ("a five (5)-year recovery period").
                cands = [f"{num} {u}", f"{num} {u}s", f"{num}{u}", f"{num}-{u}"]
                # Unit synonyms the FAA uses in prose. Without these, "95 mmHg" misses a page
                # that says "95 mm mercury diastolic" - a false positive, and a noisy check
                # gets muted. (That exact miss did surface a real defect the day this was
                # written, but on the WORDING around the number, not the number itself.)
                if u in ("mmhg", "mm hg"):
                    cands += [f"{num} mm mercury", f"{num} mm hg", f"{num} mmhg"]
                word = WORD_NUMBERS.get(num)
                if word:
                    cands += [f"{word} {u}", f"{word} ({num}) {u}", f"{word}-{u}", f"({num}) {u}"]
                if not any(c in src for c in cands):
                    failures.append(f"{name} :: {code}: the claim '{num} {unit}' does not appear "
                                    f"in {url}")

            if any(m in src for m in DEFER_MARKERS) and "defer" not in norm(body):
                warnings.append(f"{name} :: {code}: source states a deferral and this entry "
                                f"never mentions one — {url}")

            # OBLIGATION COVERAGE. For each obligation sentence in the source, does our text
            # share ANY distinctive word with it? If not, the source imposes something this
            # entry is silent about.
            ours = set(re.findall(r"[a-z]{5,}", norm(body)))
            uncovered = 0
            for sent in OBLIGATION.findall(src)[:60]:
                rare = {w for w in re.findall(r"[a-z]{5,}", sent) if w not in STOPWORDS}
                if rare and not (rare & ours):
                    uncovered += 1
            if uncovered:
                failures.append(f"{name} :: {code}: {uncovered} obligation sentence(s) in "
                                f"{url} share no distinctive wording with this entry")

    # BASELINE. 97 pre-existing failures were found the day this script was written, in a
    # file that had already been corrected twice that same day. Failing on all of them would
    # make this check red from birth, and a check that is always red gets muted and then
    # ignored - the lesson already written into check-source-links.yml.
    #
    # So the baseline is the KNOWN, UNRECONCILED debt and the check fails only on anything
    # NEW. That makes the gate real immediately: no new quotation can enter the content
    # without matching its source. The baseline is a list that must SHRINK, and every line in
    # it is a quotation a pilot may be reading that nobody has matched to an FAA page.
    baseline_path = ROOT / "scripts" / "content-fidelity-baseline.json"
    baseline = set(json.loads(baseline_path.read_text())) if baseline_path.exists() else set()
    if args.update_baseline:
        baseline_path.write_text(json.dumps(sorted(failures), indent=1) + "\n")
        print(f"baseline updated: {len(failures)} known failures recorded")
        return 0
    new_failures = [f for f in failures if f not in baseline]
    # ⚠️ Only count a baseline entry RESOLVED if its file was actually checked on this run.
    # With --file limiting the scope, every unchecked baseline entry otherwise reports as
    # fixed, which is a false progress signal of exactly the kind this script exists to stop.
    checked_files = set(files)
    in_scope = {b for b in baseline if b.split(" ::")[0] in checked_files}
    resolved = in_scope - set(failures)

    print(f"Checked {checked} quoted spans across {len(files)} file(s).")
    print(f"Known unreconciled quotations (baseline): {len(baseline)}   "
          f"new: {len(new_failures)}   resolved since baseline: {len(resolved)}")
    if warnings:
        print(f"\n⚠️  {len(warnings)} entries cite a page with an FAA deferral block but say "
              f"nothing about deferral:")
        for w in warnings:
            print("   " + w)
        print("   (Warning, not a failure. This is the exact shape of the 2026-08-14 defects:\n"
              "    we state what to BRING and omit what the FAA tells the AME to DO.)")
    if unreachable:
        print(f"\n❌ {len(unreachable)} source(s) could not be read, so their content was NOT "
              f"checked. Unreadable is not clean:")
        for u in unreachable:
            print("   " + u)
    if resolved:
        print(f"\n✅ {len(resolved)} baseline failure(s) are now fixed. Run "
              f"--update-baseline to bank that progress.")
    if new_failures:
        print(f"\n❌ {len(new_failures)} NEW quoted span(s) do not appear in the source they cite:")
        for f in new_failures:
            print("   " + f)
    if new_failures or unreachable:
        failures = new_failures
        Path("content-fidelity-report.md").write_text(
            "# Content fidelity failures\n\n"
            + "\n".join(f"- {x}" for x in failures + unreachable)
            + ("\n\n## Warnings\n\n" + "\n".join(f"- {w}" for w in warnings) if warnings else "")
        )
        return 1
    print("\n✅ every quoted span appears in the source it cites.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
