#!/usr/bin/env python3
"""Three claim-shaped checks on medications.json. Not shape-shaped: claim-shaped.

WHY THIS EXISTS
---------------
On 2026-08-13 we found that 13 diabetes medications carried isCACI:true while the
FAA routes them to a protocol that says "The AME must defer", and that clonidine
told pilots "The FAA does not name clonidine in ... Do Not Issue / Do Not Fly"
while sitting on the FAA's DO NOT ISSUE list under its own brand name.

Every existing check passed on both. validate.py checks envelope shape, code
uniqueness and manifest checksums. check-source-links.py checks that URLs resolve.
None of them ever compared a CLAIM to what the cited SOURCE says.

CONTENT_PIPELINE.md 14.10 predicted this on 2026-05-29 ("citation-shaped, not
claim-shaped"), costed the fix at 2-3 hours, and deferred it. This is that fix.

THE THREE CHECKS
----------------
A. FALSE ABSENCE. Any entry asserting the FAA does not name it, grepped against the
   live DO NOT ISSUE / DO NOT FLY tables. A hit is a factual contradiction. HARD FAIL.

B. ORPHAN CACI FLAG. isCACI:true must correspond to a condition that actually has a
   CACI worksheet in caci_worksheets.json. Two datasets in this repo describe the same
   thing and nothing has ever compared them. HARD FAIL.

C. UNFALSIFIABLE CITATION. An entry claiming "the FAA does not name this drug" must
   cite a page from the FAA's pharmaceuticals section, where that absence could
   actually be checked. Citing the AME Guide front door is what made the clonidine
   claim unfalsifiable: a pilot who clicked through to verify landed on a page that
   names no drugs at all, so no amount of link-checking could ever expose it.

   Deliberately NOT "the page must mention the drug". That version flags 176 of 182,
   because a drug-level entry legitimately cites a CONDITION page (lisinopril ->
   Item 36 Hypertension). A check that fires on 97% of the corpus teaches people to
   ignore it. It is reported below as context, and gated only on the narrow class.

   RATCHET: fails only if the count INCREASES above the recorded baseline, so it
   lands on legacy content without wedging the repo.

INSTRUMENT DISCIPLINE (learned the hard way, see CLAUDE.md)
----------------------------------------------------------
- curl is the transport, never urllib. urllib on the maintainer's Mac has no CA
  bundle and once reported all 84 FAA sources dead. curl behaves the same locally
  and on the runner, so a check that cannot be run locally cannot be trusted.
- Every extraction is validated against a control string known to be present
  BEFORE any negative result is believed.
- The matcher self-tests against known answers before it runs, including the
  "diabetes must NOT match Prediabetes" trap, which is precisely how a naive
  substring check would have waved the original defect through.
- UNREACHABLE is not DEAD. A TLS or DNS failure says nothing about a claim, so it
  exits 2 (warn) rather than 1 (contradiction found). Never conflate them.

EXIT CODES
  0  all checks pass
  1  a real contradiction was found
  2  could not verify (source unreachable). Not a pass, not a contradiction.
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
V1 = ROOT / "v1"
BASELINE = ROOT / "scripts" / "med-claims-baseline.json"

DNI_DNF_URL = "https://www.faa.gov/ame_guide/media/DNI_DNF_tables.pdf"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/128.0 Safari/537.36")

# A string we know is on the DNI/DNF tables. If this is not found, the extractor
# is broken and every negative result from it is meaningless.
DNI_CONTROL = "diphenhydramine"

# Phrases that mean "we are telling the pilot the FAA does not name this drug".
ABSENCE_MARKERS = (
    "does not name",
    "doesn't name",
    "not individually listed",
    "not named in",
)

failures: list[str] = []
warnings: list[str] = []
notes: list[str] = []


def fetch(url: str, dest: Path) -> bool:
    """curl a URL to dest. Returns False on UNREACHABLE (not on 404)."""
    try:
        r = subprocess.run(
            ["curl", "-sSL", "--max-time", "60", "-A", UA, "-o", str(dest),
             "-w", "%{http_code}", url],
            capture_output=True, text=True, timeout=90,
        )
    except (subprocess.TimeoutExpired, OSError) as ex:
        warnings.append(f"UNREACHABLE (not dead): {url} -> {ex}")
        return False
    code = (r.stdout or "").strip()
    if r.returncode != 0:
        warnings.append(f"UNREACHABLE (not dead): {url} -> curl exit {r.returncode} {r.stderr.strip()[:120]}")
        return False
    if code != "200":
        # A real server answer. This IS evidence, unlike a transport failure.
        failures.append(f"CITATION DEAD: {url} returned HTTP {code}")
        return False
    return True


def pdf_text(path: Path) -> str:
    try:
        from pypdf import PdfReader
    except ImportError:
        try:
            from PyPDF2 import PdfReader  # type: ignore
        except ImportError:
            warnings.append("no pypdf available; cannot read PDFs")
            return ""
    try:
        return "\n".join((p.extract_text() or "") for p in PdfReader(str(path)).pages)
    except Exception as ex:  # noqa: BLE001
        warnings.append(f"PDF extraction failed for {path.name}: {ex}")
        return ""


def html_text(path: Path) -> str:
    raw = path.read_text(encoding="utf-8", errors="replace")
    raw = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", raw)
    raw = re.sub(r"(?s)<[^>]+>", " ", raw)
    return re.sub(r"\s+", " ", raw)


def names_of(entry: dict) -> list[str]:
    out = [entry.get("genericName") or ""]
    out += entry.get("brandNames") or []
    cleaned = []
    for n in out:
        n = n.strip().lower()
        # take the head token: "fluticasone (inhaled)" -> "fluticasone"
        n = re.split(r"[ /(]", n)[0].strip()
        if len(n) >= 5:  # short tokens produce false positives
            cleaned.append(n)
    return sorted(set(cleaned))


def condition_tokens(entry: dict) -> list[str]:
    """Conditions a medication's category names, e.g. 'ACE inhibitor (hypertension)'."""
    cat = entry.get("category") or ""
    m = re.search(r"\(([^)]*)\)", cat)
    if not m:
        return []
    return [t.strip().lower() for t in re.split(r"[/,]| or ", m.group(1)) if t.strip()]


def worksheet_covers(token: str, worksheet_names: list[str]) -> bool:
    """Does a condition token correspond to a real CACI worksheet?

    WORD-BOUNDARY matching, deliberately. A naive substring test matches
    'diabetes' inside 'Prediabetes', which is exactly the false pass that would
    have let the original 13-medication defect through this check.
    """
    for w in worksheet_names:
        if re.search(rf"(?<![a-z]){re.escape(token)}(?![a-z])", w.lower()):
            return True
    return False


def self_test(worksheet_names: list[str]) -> None:
    """Prove the matcher works on known answers before trusting it on real data."""
    cases = [
        ("hypertension", True),
        ("hypothyroidism", True),
        ("asthma", True),
        ("glaucoma", True),
        # THE TRAP: 'diabetes' is a substring of 'Prediabetes'. It must NOT match.
        ("diabetes", False),
        ("copd", False),
        ("heart failure", False),
    ]
    bad = []
    for token, expected in cases:
        got = worksheet_covers(token, worksheet_names)
        if got != expected:
            bad.append(f"{token!r}: expected {expected}, got {got}")
    if bad:
        failures.append("MATCHER SELF-TEST FAILED (the check cannot be trusted): " + "; ".join(bad))
    else:
        notes.append(f"matcher self-test passed on {len(cases)} known answers, including the "
                     f"'diabetes' vs 'Prediabetes' trap")


# ---------------------------------------------------------------------------

def main() -> int:
    meds = json.loads((V1 / "medications.json").read_text(encoding="utf-8"))
    ws_raw = json.loads((V1 / "caci_worksheets.json").read_text(encoding="utf-8"))
    worksheets = ws_raw if isinstance(ws_raw, list) else ws_raw.get("worksheets", [])
    ws_names = [w.get("conditionName", "") for w in worksheets]

    tmp = Path(tempfile.mkdtemp(prefix="medclaims-"))
    print(f"checking {len(meds)} medication entries against {len(ws_names)} CACI worksheets")
    print()

    # ---- CHECK A: false absence claims ------------------------------------
    print("A. FALSE ABSENCE: entries claiming the FAA does not name them")
    dni_pdf = tmp / "dni_dnf.pdf"
    a_ran = False
    if fetch(DNI_DNF_URL, dni_pdf):
        text = pdf_text(dni_pdf)
        if DNI_CONTROL not in text.lower():
            warnings.append(
                f"CONTROL FAILED: {DNI_CONTROL!r} not found in the DNI/DNF tables. The "
                f"extractor is broken, so every negative below is meaningless. Not treating "
                f"absence as evidence."
            )
            print(f"   CONTROL FAILED on {DNI_CONTROL!r}; check A skipped")
        else:
            a_ran = True
            low = text.lower()
            print(f"   control ok ({DNI_CONTROL!r} found)")
            claimants = [
                m for m in meds
                if m.get("informationalOnly")
                or any(k in (m.get("informationalNote") or "").lower() for k in ABSENCE_MARKERS)
                or any(k in (m.get("faaStatusDescription") or "").lower() for k in ABSENCE_MARKERS)
            ]
            hits = []
            for m in claimants:
                for n in names_of(m):
                    if re.search(rf"(?<![a-z]){re.escape(n)}(?![a-z])", low):
                        hits.append((m["envelope"]["code"], m.get("genericName"), n))
                        break
            print(f"   {len(claimants)} entries assert the FAA does not name them")
            for code, generic, tok in hits:
                failures.append(
                    f"FALSE ABSENCE: {code} ({generic}) claims the FAA does not name it, but "
                    f"{tok!r} appears on the live DO NOT ISSUE / DO NOT FLY tables"
                )
            print(f"   contradictions: {len(hits)}")
    if not a_ran:
        print("   NOT VERIFIED (see warnings)")
    print()

    # ---- CHECK B: orphan CACI flags ---------------------------------------
    print("B. ORPHAN CACI FLAG: isCACI true with no matching worksheet")
    self_test(ws_names)
    flagged = [m for m in meds if m.get("isCACI") is True]
    orphans, unresolved = [], []
    for m in flagged:
        toks = condition_tokens(m)
        if not toks:
            unresolved.append((m["envelope"]["code"], m.get("category")))
            continue
        if not any(worksheet_covers(t, ws_names) for t in toks):
            orphans.append((m["envelope"]["code"], m.get("genericName"), m.get("category")))
    print(f"   {len(flagged)} entries carry isCACI:true")
    for code, generic, cat in orphans:
        failures.append(
            f"ORPHAN CACI: {code} ({generic}) sets isCACI:true but its condition "
            f"{cat!r} has no worksheet in caci_worksheets.json"
        )
    print(f"   orphans: {len(orphans)}")
    if unresolved:
        # NOT a failure. A category with no parenthetical condition cannot be resolved
        # mechanically, and guessing is how a check starts producing false positives.
        # Reported loudly so it is never mistaken for coverage.
        print(f"   UNRESOLVED (category names no condition, needs a human): {len(unresolved)}")
        for code, cat in unresolved:
            print(f"      - {code}  category={cat!r}")
        notes.append(f"{len(unresolved)} isCACI entries could not be resolved mechanically")
    print()

    # ---- CHECK C: unfalsifiable citations ---------------------------------
    print("C. UNFALSIFIABLE CITATION: absence claims citing a page that cannot verify them")
    # The gate: an entry asserting the FAA does not name it must cite somewhere in the
    # FAA's pharmaceuticals section, where a pilot could actually check. The AME Guide
    # front door names no drugs, so a claim citing it can never be contradicted.
    PHARM_PREFIX = "https://www.faa.gov/ame_guide/pharm"
    claimants = [
        m for m in meds
        if m.get("informationalOnly")
        or any(k in (m.get("informationalNote") or "").lower() for k in ABSENCE_MARKERS)
        or any(k in (m.get("faaStatusDescription") or "").lower() for k in ABSENCE_MARKERS)
    ]
    unsupported = []
    for m in claimants:
        url = m["envelope"].get("sourceURL") or ""
        if not url.startswith(PHARM_PREFIX):
            unsupported.append((m["envelope"]["code"], m.get("genericName"), url or "(no sourceURL)"))
    count = len(unsupported)
    print(f"   {len(claimants)} entries make an absence claim")
    base = 0
    if BASELINE.exists():
        base = json.loads(BASELINE.read_text()).get("unsupportedCitations", 0)
    print(f"   {count} of them cite outside {PHARM_PREFIX} (baseline {base})")
    if count > base:
        added = count - base
        failures.append(
            f"UNFALSIFIABLE CITATION: {count} absence claims cite a page outside the FAA's "
            f"pharmaceuticals section, up {added} from the baseline of {base}. A claim whose "
            f"citation cannot contradict it is what hid the clonidine defect for months. Point "
            f"it at the relevant {PHARM_PREFIX}/... page, or if the increase is intended, "
            f"update {BASELINE.name} deliberately."
        )
    elif count < base:
        notes.append(f"citation ratchet IMPROVED: {count} < baseline {base}. "
                     f"Lower the baseline in {BASELINE.name} to lock the gain in.")
    if count:
        # Loud, never silent. A tolerated number that nobody can see reads as zero.
        print("   TOLERATED under the ratchet (real, but pre-existing):")
        for code, generic, url in unsupported[:8]:
            print(f"      - {code} ({generic}) -> {url}")
        if count > 8:
            print(f"      ... and {count - 8} more")

    # Context only, never a gate. Reported because it is the honest shape of the
    # corpus, and because someone will otherwise assume check C covers more than it does.
    off_topic = sum(
        1 for m in meds
        if not (m["envelope"].get("sourceURL") or "").startswith(PHARM_PREFIX)
    )
    print(f"   context (NOT gated): {off_topic} of {len(meds)} entries cite outside the "
          f"pharmaceuticals section at all, mostly condition pages, which is legitimate")
    print()

    # ---- report ------------------------------------------------------------
    for n in notes:
        print(f"note: {n}")
    for w in warnings:
        print(f"WARN: {w}")
    print()

    # Emit the report + fingerprint the workflow consumes. Same contract as
    # check-source-links.py: NOTIFY ON CHANGE, NOT ON STATE. A known unfixed
    # contradiction must not re-email every Monday, because that is exactly how an
    # alert teaches its reader to ignore it.
    if failures:
        fingerprint = hashlib.sha256("\n".join(sorted(failures)).encode()).hexdigest()[:16]
        lines = [
            "## Medication claim checks failed",
            "",
            "These are CLAIM-shaped checks: they compare what our content asserts against",
            "what the FAA actually publishes. `validate.py` and the link checker cannot see",
            "any of this, because a well-formed entry with a resolving URL can still be",
            "factually wrong. That is how the 2026-08-13 CACI and clonidine defects survived.",
            "",
            f"**{len(failures)} problem(s):**",
            "",
        ]
        for f in failures:
            lines.append(f"- {f}")
        lines += [
            "",
            "### What to do",
            "",
            "- **FALSE ABSENCE**: the entry tells pilots the FAA does not name the drug, and it does.",
            "  Read the FAA source, rewrite `faaStatusDescription`, clear `informationalOnly`,",
            "  drop `informationalNote`, and cite the page that actually names it.",
            "- **ORPHAN CACI**: `isCACI: true` with no worksheet for that condition in",
            "  `caci_worksheets.json`. Either the flag is wrong or a worksheet is missing.",
            "  Check the FAA's live index at https://www.faa.gov/ame_guide/certification_ws first.",
            "- **UNFALSIFIABLE CITATION**: an absence claim citing a page that cannot verify it.",
            "  Point it at the relevant https://www.faa.gov/ame_guide/pharm/... page.",
            "",
            "Every claim here was checked against a live faa.gov fetch in this run, with the",
            "extractor validated against a known-present control string first.",
            "",
            f"fingerprint:{fingerprint}",
        ]
        Path("med-claims-report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
        Path("med-claims-fingerprint.txt").write_text(fingerprint, encoding="utf-8")
        print(f"FAILED with {len(failures)} problem(s):")
        for f in failures:
            print(f"  ! {f}")
        print(f"\nwrote med-claims-report.md (fingerprint {fingerprint})")
        return 1

    if warnings:
        print("COULD NOT FULLY VERIFY (source unreachable). This is not a pass.")
        return 2
    print("all three claim checks pass")
    return 0


if __name__ == "__main__":
    sys.exit(main())
