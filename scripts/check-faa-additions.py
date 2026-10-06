#!/usr/bin/env python3
"""Ask the one question every other check here skips: what does the FAA NAME that we do not?

WHY (Ryan 2026-10-05). Every safeguard in this repo iterates OUR data and asks whether each
row is still right. None iterates the FAA's lists and asks what is missing. On 09/30/2026 the
FAA added "orforglipron (Foundayo)" to its Weight Loss Management CACI worksheet; fidelity
passed (we quote none of that drug list), the date checker cannot read PDFs, and nothing
compared the list against ours. A pilot searching "Foundayo" got nothing until a hand sweep
found it. GOTCHAS_VERIFY.md §57 recorded the same blind spot a month earlier (the OTC chart's
AVOID column named nine drugs and we carried four).

WHAT IT READS. A FIXED list, never a search of faa.gov:
  - the FAA's Do Not Issue / Do Not Fly tables (DNI_DNF_tables.pdf)
  - every CACI worksheet PDF our content cites: caci_worksheets.json's sourceURL and
    worksheetURL, plus any *CACI* PDF a medication entry cites. (Until 2026-10-06 only the
    sourceURL was read, and the arthritis entry's sourceURL is the disposition TABLE, so the
    arthritis WORKSHEET and its 22 drugs were never read; 11 of them were missing.)
  - the detailed drug lists those worksheets send the AME to (DRUG_LISTS below). Added
    2026-10-06: Headache_Migraine.pdf says "Detailed list of migraine medications can be found
    Pharmaceuticals - Migraine Medications", and 8 drugs on that page were absent from our file
    with this check green (rimegepant, zolmitriptan, lasmiditan...).
It pulls drug names the way the FAA writes them: "generic (Brand)" or "generic [Brand]"
anywhere, plus bulleted lowercase names in the DNI/DNF tables. The generic may be capitalised
("Rimegepant (Nurtec)") or tall-man ("ZOLMitriptan (Zomig)"); until 2026-10-06 only lowercase
generics were read, which is how rimegepant was skipped on the migraine worksheet.

WHAT COUNTS AS OURS. A name a pilot's search would find: it appears, as whole words, in any
medication entry's genericName, brandNames, faaStatusDescription, informationalNote, category
or treatedConditionNote (the fields ReferenceSearchIndex.swift indexes), or in
search_synonyms.json. A drug mentioned inside a class entry IS findable, so it is not a gap.

NOT A DRUG. The extraction is deliberately crude ("angiography (CTA)", "blockers (Inderal)"),
so non-drug words live in scripts/faa-additions-ignore.json with a reason. Add a term there
only when it is not a medication, or when we deliberately do not carry it AND say why. An
ignore entry is a decision, not a mute button.

INSTRUMENT DISCIPLINE (GOTCHAS_VERIFY §1, §13): before any result is believed, the DNI text
must contain a known drug, the weight-loss CACI must yield orforglipron, the migraine
worksheet must yield the capitalised "Rimegepant", and the migraine drug list must yield the
tall-man "ZOLMitriptan". A self-test then
removes orforglipron from our side and requires the check to flag it. Any control failing
exits 2 (broken instrument), never 0 or 1.

EXIT CODES: 0 nothing missing · 1 names missing (report written) · 2 could not verify
"""

import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
IGNORE = ROOT / "scripts" / "faa-additions-ignore.json"
DNI_URL = "https://www.faa.gov/ame_guide/media/DNI_DNF_tables.pdf"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")
DNI_CONTROL = "diphenhydramine"
CACI_CONTROL = ("CACI_weight_loss_management.pdf", "orforglipron")
CASE_CONTROLS = (("Headache_Migraine.pdf", "rimegepant"), ("Migraine_Medication.pdf", "zolmitriptan"))
DRUG_LISTS = ["https://www.faa.gov/ame_guide/media/Migraine_Medication.pdf",
              # The FAA's list for the biologic/targeted drugs on the arthritis, colitis and EoE
              # worksheets; it also names 11 drugs no worksheet does (added 2026-10-06).
              "https://www.faa.gov/ame_guide/media/Biologics_Biosimilars_Non-Biologics.pdf"]

PAIR = re.compile(r"\b([A-Za-z][A-Za-z\-]{3,}(?: [A-Za-z][A-Za-z\-]{3,})?)\s*\*?\s*[\(\[]\s*([A-Z][A-Za-z0-9\- ]{1,30})")
BULLET = re.compile(r"(?m)^\s*(?:•|o|-)\s+([a-z][a-z\-]{4,})\b")
ACRONYM = re.compile(r"^[A-Z0-9]{2,6}\b")
SEARCHED = ("genericName", "faaStatusDescription", "informationalNote", "category", "treatedConditionNote")


def fetch_text(url: str, tmp: Path) -> str | None:
    dest = tmp / re.sub(r"[^A-Za-z0-9.]+", "_", url.rsplit("/", 1)[-1])
    r = subprocess.run(["curl", "-sSL", "--fail", "--max-time", "60", "-A", UA, "-o", str(dest), url],
                       capture_output=True, text=True)
    if r.returncode != 0:
        return None
    try:
        from pypdf import PdfReader
    except ImportError:
        print("❌ pypdf is required: pip install pypdf")
        sys.exit(2)
    try:
        return "\n".join((p.extract_text() or "") for p in PdfReader(str(dest)).pages)
    except Exception as ex:  # noqa: BLE001
        print(f"  could not read {url}: {ex}")
        return None


def candidates(text: str, bullets: bool) -> set[str]:
    out = set()
    for m in PAIR.finditer(text):
        if not ACRONYM.match(m.group(2)):
            out.add(m.group(1).strip().lower())
    if bullets:
        out.update(m.group(1) for m in BULLET.finditer(text))
    return out


def our_text() -> str:
    parts = []
    for e in json.loads((ROOT / "v1" / "medications.json").read_text()):
        parts += [str(e.get(f) or "") for f in SEARCHED]
        parts += e.get("brandNames") or []
    syn = json.loads((ROOT / "v1" / "search_synonyms.json").read_text())
    for s in syn.get("entries", []):
        parts += s.get("aliases", []) + s.get("expandsTo", [])
    return " \n ".join(parts).lower()


def covered(name: str, ours: str) -> bool:
    return re.search(r"(?<![a-z])" + re.escape(name) + r"(?![a-z])", ours) is not None


def main() -> int:
    ignore = json.loads(IGNORE.read_text()).get("terms", {})
    caci = json.loads((ROOT / "v1" / "caci_worksheets.json").read_text())
    cited = set()
    for e in caci:
        cited |= {e["envelope"]["sourceURL"], e.get("worksheetURL") or ""}
    for e in json.loads((ROOT / "v1" / "medications.json").read_text()):
        for u in [e["envelope"].get("sourceURL") or ""] + [l.get("url", "") for l in e.get("links") or []]:
            if "caci" in u.rsplit("/", 1)[-1].lower():
                cited.add(u)
    caci_urls = sorted({u for u in cited if u.lower().endswith(".pdf")} | set(DRUG_LISTS))
    found: dict[str, set[str]] = {}
    unreadable = []
    with tempfile.TemporaryDirectory() as tmp:
        for url in [DNI_URL] + caci_urls:
            text = fetch_text(url, Path(tmp))
            if text is None:
                unreadable.append(url)
                continue
            name = url.rsplit("/", 1)[-1]
            if url == DNI_URL and DNI_CONTROL not in text.lower():
                print(f"❌ CONTROL FAILED: '{DNI_CONTROL}' not read from {url}. Extraction is broken.")
                return 2
            got = candidates(text, bullets=(url == DNI_URL))
            if name == CACI_CONTROL[0] and CACI_CONTROL[1] not in got:
                print(f"❌ CONTROL FAILED: '{CACI_CONTROL[1]}' not extracted from {name}.")
                return 2
            for doc, drug in CASE_CONTROLS:
                if name == doc and drug not in got:
                    print(f"❌ CONTROL FAILED: '{drug}' not extracted from {name} (capitalised name).")
                    return 2
            for c in got:
                found.setdefault(c, set()).add(name)
    if DNI_URL in unreadable or len(unreadable) == len(caci_urls) + 1:
        print(f"Could not read the FAA lists ({len(unreadable)} unreadable). Not a finding.")
        return 2

    ours = our_text()
    # NEGATIVE CONTROL: with orforglipron removed from our side, it must be reported.
    if "orforglipron" not in found or covered("orforglipron", ours.replace("orforglipron", "x")):
        print("❌ SELF-TEST FAILED: removing orforglipron from our names did not uncover it.")
        return 2

    missing = {n: srcs for n, srcs in found.items() if n not in ignore and not covered(n, ours)}
    stale = sorted(t for t in ignore if t not in found)
    print(f"read {1 + len(caci_urls) - len(unreadable)} FAA lists, {len(found)} names, "
          f"{len(missing)} not in our medication file")
    for n in sorted(missing):
        print(f"   {n:30s} {', '.join(sorted(missing[n]))}")
    if stale:
        print(f"note: {len(stale)} ignore term(s) no longer appear in any FAA list: {', '.join(stale)}")
    if unreadable:
        print(f"note: {len(unreadable)} list(s) unreadable this run: {', '.join(unreadable)}")
    if not missing:
        print("✅ every drug the FAA names in these lists is findable in our medication file.")
        return 0
    lines = [f"- `{n}` (named in {', '.join(sorted(missing[n]))})" for n in sorted(missing)]
    Path("faa-additions-report.md").write_text(
        f"# Drugs the FAA names that our medication file does not\n\n"
        f"{len(missing)} name(s) appear on the FAA's Do Not Issue / Do Not Fly tables or a CACI "
        f"worksheet and nowhere a pilot's search would find them in `v1/medications.json`.\n\n"
        + "\n".join(lines)
        + "\n\n## What to do\n\nFor each: add an entry quoting the FAA document that names it, or, if it "
          "is not a medication or we deliberately do not carry it, add it to "
          "`scripts/faa-additions-ignore.json` with the reason.\n")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
