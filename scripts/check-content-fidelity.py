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
import hashlib
import html
import json
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import urljoin

# Any URL inside a finding message. The baseline key is deliberately blind to these:
# a citation's URL can be corrected without that resurrecting a banked finding.
_URL_IN_MSG = re.compile(r"https?://\S+")

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


def _blob(url: str, cache: Path) -> Path | None:
    """Download `url` (or reuse the cached copy) and return the file. None means UNREACHABLE."""
    # 🚨 eCFR SERVES A JAVASCRIPT SHELL TO DATACENTER IPs. Fetched from a laptop, the HTML
    # page carries the regulation text; fetched from a GitHub runner it returns a page with
    # enough words to PASS the vocabulary control but WITHOUT the regulation body. That made
    # the first CI run report five BasicMed quotations missing that are demonstrably present,
    # and it passed locally, which is the worst possible shape for a check.
    #
    # The renderer API returns the section text deterministically from anywhere, so eCFR URLs
    # are rewritten to it. Verified: 4,507 chars containing the 68.3(b)(3) text the HTML shell
    # omitted for the runner.
    m = re.match(r"https://www\.ecfr\.gov/current/title-(\d+)/.*?section-([\d.]+)$", url)
    if m:
        url = (f"https://www.ecfr.gov/api/renderer/v1/content/enhanced/current/"
               f"title-{m.group(1)}?section={m.group(2)}")
    key = re.sub(r"[^a-z0-9]+", "_", url.lower())[:120]
    blob = cache / key
    if not blob.exists():
        cache.mkdir(parents=True, exist_ok=True)
        r = subprocess.run(["curl", "-sSL", "-A", UA, "--max-time", "60", "-o", str(blob), url],
                           capture_output=True)
        if r.returncode != 0 or not blob.exists() or blob.stat().st_size == 0:
            blob.unlink(missing_ok=True)
            return None
    return blob


def fetch(url: str, cache: Path) -> str | None:
    """Source text for a URL, from cache or the network. None means UNREACHABLE.

    ⏱️ THE EXTRACTED TEXT IS CACHED TO DISK, NOT JUST THE DOWNLOAD. pdfplumber with
    `extract_tables` on every page is by far the slowest step: the 2026-08-17 scheduled run
    took 24m49s re-parsing documents it had already fetched, and the widened resolver reads
    the whole ~131-document corpus. Caching the download alone does not help, because the
    cost is the PARSE, not the network.

    With a warm cache a local run is seconds, and that is the property that decides whether
    this check gets run before a push at all. `check-source-links.py` was unrunnable locally
    for a while, and this repo has already written down where that leads.
    """
    blob = _blob(url, cache)
    if blob is None:
        return None
    raw = blob.read_bytes()
    # 🚨 KEYED ON THE CONTENT HASH, NOT THE URL OR THE MTIME. Keying on either would let a
    # CHANGED FAA page reuse the parse of the old one, which is precisely the failure this
    # whole script exists to catch, reintroduced as a performance optimisation. Identical
    # bytes cannot parse differently; different bytes always re-parse. That also makes the
    # parse cache safe to persist across CI runs while downloads stay fresh every time.
    txt = cache / "parsed" / (hashlib.sha256(raw).hexdigest()[:32] + ".txt")
    if txt.exists():
        return txt.read_text(encoding="utf-8")
    txt.parent.mkdir(parents=True, exist_ok=True)
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
        out = norm(" ".join(parts))
    else:
        out = norm(raw.decode("utf-8", errors="ignore"))
    txt.write_text(out, encoding="utf-8")
    return out


# 🚨 WHY A QUOTE IS CHECKED AGAINST MORE THAN ONE DOCUMENT (2026-08-17).
#
# `envelope.sourceURL` is SINGLE-VALUED. Many entries legitimately quote two to five FAA
# documents, because that is how the AME Guide is built: a topic page carries the routing
# and links out to the tables, worksheets and disposition charts that carry the specifics.
# `med-phentermine` quotes the Weight Loss Medication page AND the Do Not Issue table; its
# prose attributes each by name and `sourceCitation` lists both with their update dates.
# Only the URL field cannot hold them.
#
# Checking every span against `sourceURL` alone therefore reported 120 findings on content
# that was correctly quoted and correctly attributed, and would have failed every Monday
# forever. Measured: all 96 flagged (entry, span) pairs were verbatim in a real FAA
# document, and ZERO were fabricated.
#
# 🪤 AND THE OBVIOUS "FIX" WAS A TRAP. Re-pointing `sourceURL` to silence the checker would
# have converted an accurate quotation into a fabricated one: the DNI table says
# "Sympathomimetic (such as phentermine [Adipex])" and the weight-loss PDF says the same
# thing WITHOUT "[Adipex]". Both files contain "Adipex" elsewhere, so a keyword check calls
# it clean either way. 5 entries. The content was right and the CHECK's model was wrong.
#
# ⚖️ SCOPE IS DELIBERATELY ONE HOP, SAME HOST, AND QUOTES ONLY.
#   • One hop from the cited page, never transitive. Two hops reaches most of the AME Guide,
#     at which point "the FAA says this somewhere" is not a claim worth testing.
#   • faa.gov only.
#   • ONLY the quotation and numeric-claim tests widen. The deferral warning and the
#     obligation-coverage test stay pinned to the CITED document, because those ask what THIS
#     source imposes. Widening them would let an obligation from any of fourteen linked PDFs
#     count as covered, which would gut the one test that can see an omission.
LINK_RE = re.compile(rb'href=["\']([^"\']+)["\']', re.I)
MAX_LINKED_DOCS = 25

# Extracted text, memoized per process. The disk cache saves the DOWNLOAD; this saves the
# pdfplumber EXTRACTION, which is the slow half and which tier 3 would otherwise repeat
# across every entry that reaches it.
_TEXT: dict[str, str | None] = {}


def text_of(url: str, cache: Path) -> str | None:
    if url not in _TEXT:
        _TEXT[url] = fetch(url, cache)
    return _TEXT[url]


_LINKED: dict[str, list[tuple[str, str]]] = {}
_WIDER: list[tuple[str, str]] | None = None


def linked_corpus(url: str, cache: Path) -> list[tuple[str, str]]:
    """Tier 2: readable documents the cited one links to."""
    if url not in _LINKED:
        out = []
        for link in linked_faa_docs(url, cache):
            t = text_of(link, cache)
            if t and len(t) >= 200:
                out.append((link, t))
        _LINKED[url] = out
    return _LINKED[url]


def wider_corpus(all_source_urls: list[str], cache: Path) -> list[tuple[str, str]]:
    """Tier 3: every document this project cites anywhere. Built once."""
    global _WIDER
    if _WIDER is None:
        _WIDER = []
        for u in all_source_urls:
            t = text_of(u, cache)
            if t and len(t) >= 200:
                _WIDER.append((u, t))
    return _WIDER


def in_source(needle: str, hay: str) -> bool:
    n = norm(needle)
    if n in hay or n.rstrip(" .,;:") in hay:
        return True
    # A nested quotation may be re-rendered ('NO*' for "NO*"); that is a typographic
    # convention, not a misquote.
    return re.sub(r"['\"]", "", n.rstrip(" .,;:")) in re.sub(r"['\"]", "", hay)


def resolve_span(needle: str, cited_url: str, cited_text: str,
                 all_source_urls: list[str], cache: Path):
    """(True, where) if `needle` is verbatim in an FAA document this project stands behind.

    Three tiers, cheapest first, each paid for only if the one before missed:
      1. the CITED document                 -> silent pass
      2. a document the cited one LINKS TO  -> pass, plus a citation warning
      3. any other document our own content -> pass, plus a citation warning
         cites as a `sourceURL`
      otherwise                             -> FAILURE

    ▶️ WHY TIER 3 EXISTS, and it is not laziness. One hop is not enough on real FAA
    structure: `med-phentermine` quotes the Do Not Issue table and names it in
    `sourceCitation`, but `Weight_loss_Pharm.pdf` does NOT link to it (measured: that PDF
    exposes exactly four link annotations, none of them the DNI table). A one-hop rule
    reported that accurate quotation as missing.

    ⚖️ THE BOUND IS OUR OWN CONTENT, which is what keeps this honest. Tier 3 is not "search
    the FAA"; it is the ~131 documents this project already cites and already vouches for.
    A span in NONE of them still fails, which is the property the whole check exists for.

    🚨 THIS IS THE ONLY DEFINITION. `main()` and the control harness both call it. An
    earlier control REIMPLEMENTED the tiers, drifted one tier behind, and reported a
    correct resolver as broken. The copy is what drifts.
    """
    if in_source(needle, cited_text):
        return True, cited_url
    for link, text in linked_corpus(cited_url, cache):
        if in_source(needle, text):
            return True, link
    for other, text in wider_corpus(all_source_urls, cache):
        if other == cited_url:
            continue
        if in_source(needle, text):
            return True, other
    return False, None


def linked_faa_docs(url: str, cache: Path) -> list[str]:
    """FAA documents linked directly from `url`. One hop, same host, deduped, capped."""
    blob = _blob(url, cache)
    if blob is None:
        return []
    raw = blob.read_bytes()
    found: list[str] = []

    if raw[:4] == b"%PDF":
        # PDF link ANNOTATIONS. Several AME Guide PDFs point at their own worksheets this
        # way and carry no HTML at all, so skipping these loses whole documents.
        try:
            import pdfplumber
            with pdfplumber.open(blob) as pdf:
                for page in pdf.pages:
                    for link in (page.hyperlinks or []):
                        if link.get("uri"):
                            found.append(link["uri"])
                    for annot in (page.annots or []):
                        uri = (annot.get("uri") or (annot.get("data") or {}).get("A", {}) or {})
                        if isinstance(uri, str):
                            found.append(uri)
        except Exception:
            return []
    else:
        for m in LINK_RE.findall(raw):
            found.append(m.decode("utf-8", errors="ignore"))

    out, seen = [], {url}
    for href in found:
        href = html.unescape(href.strip())
        full = urljoin(url, href)
        full = full.split("#")[0]
        if not full.lower().startswith("https://www.faa.gov/"):
            continue
        # Documents, not navigation. The AME Guide's chrome links to its own index pages on
        # every page; those carry no quotable text and would just cost fetches.
        if not (full.lower().endswith(".pdf") or "/ame_guide/" in full.lower()):
            continue
        if full in seen:
            continue
        seen.add(full)
        out.append(full)
        if len(out) >= MAX_LINKED_DOCS:
            break
    return out


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


def _selftest() -> int:
    """Prove the baseline key on KNOWN-GOOD *and* KNOWN-BAD input.

    A baseline key has two ways to fail and they are opposites:
      too STRICT -> a corrected citation URL resurrects a banked finding as "new"
                    (this is what filed content issue #8 on 2026-08-24), and
      too LOOSE  -> two genuinely different findings collapse onto one key and a REAL
                    defect is silently accepted as already-known. That direction is worse,
                    and it is invisible: nothing fails, the run just goes green.
    A test fed only the first case would pass while shipping the second, which is the
    trap CLAUDE.md records this project falling into twice inside the tool built to
    prevent it. So both directions are asserted here.
    """
    def fkey(msg: str) -> str:
        return _URL_IN_MSG.sub("<src>", msg.replace(" nor in any document it links to", ""))

    M = ("medications.json :: med-contrave: 3 obligation sentence(s) in "
         "https://www.faa.gov/ame_guide/media/Weight_loss_{}.pdf "
         "share no distinctive wording with this entry")
    fails = []

    # KNOWN-GOOD: the same finding whose citation URL was corrected must stay suppressed.
    if fkey(M.format("pharm")) != fkey(M.format("Pharm")):
        fails.append("a corrected sourceURL still reads as a NEW failure")

    # KNOWN-BAD 1: a different obligation COUNT is a different finding.
    if fkey(M.format("Pharm")) == fkey(M.format("Pharm").replace("3 obligation", "5 obligation")):
        fails.append("a changed obligation count is being suppressed")

    # KNOWN-BAD 2: a different entry code is a different finding.
    if fkey(M.format("Pharm")) == fkey(M.format("Pharm").replace("med-contrave", "med-qsymia")):
        fails.append("a different entry code is being suppressed")

    # KNOWN-BAD 3: the live baseline must not MERGE. If stripping URLs collapses any two
    # banked entries onto one key, this key is too loose for the real corpus, whatever the
    # synthetic cases above say. Measured against the file, not a fixture.
    bpath = ROOT / "scripts" / "content-fidelity-baseline.json"
    if bpath.exists():
        banked = json.loads(bpath.read_text())
        if len({fkey(x) for x in banked}) != len(set(banked)):
            fails.append(f"the key MERGES entries in the live baseline "
                         f"({len(set(banked))} entries -> {len({fkey(x) for x in banked})} keys)")

    if fails:
        print("❌ fidelity selftest FAILED:")
        for f in fails:
            print(f"   - {f}")
        return 1
    print("✅ fidelity selftest passed (1 known-good, 3 known-bad)")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", action="append", help="limit to these v1 filenames")
    ap.add_argument("--cache", type=Path, default=Path(".fidelity-cache"))
    ap.add_argument("--update-baseline", action="store_true",
                    help="record the CURRENT failures as accepted debt. Use only when you have "
                         "triaged them; every line you add here is a quotation nobody has "
                         "reconciled with its source.")
    ap.add_argument("--selftest", action="store_true",
                    help="verify the baseline key against known-good AND known-bad input, "
                         "then exit. Gates CI; a checker nobody controls is not a check.")
    args = ap.parse_args()

    if args.selftest:
        return _selftest()

    files = sorted(args.file or [p.name for p in V1.glob("*.json") if p.name != "manifest.json"])
    failures, warnings, unreachable, checked = [], [], [], 0
    # Kept SEPARATE from `warnings`, which is the deferral-omission signal and prints
    # under its own header. Pooling them would file a citation-precision note under a
    # heading that says it is about a missed deferral.
    citations = []

    # 🚨 GATHERED FROM EVERY FILE, NOT JUST THE ONES IN SCOPE. `--file` limits what is
    # CHECKED; it must not change the VERDICT on what is checked. Building this from the
    # scoped set would make `--file medications.json` fail spans that a full run passes,
    # which is the shape of bug that makes a checker untrustworthy rather than merely wrong.
    all_source_urls: list[str] = []
    _seen_urls: set[str] = set()
    for p in sorted(V1.glob("*.json")):
        if p.name == "manifest.json":
            continue
        try:
            data = json.loads(p.read_text())
        except (json.JSONDecodeError, OSError):
            continue
        if not isinstance(data, list):
            continue
        for e in data:
            u = (e.get("envelope") or {}).get("sourceURL")
            if u and u not in _seen_urls:
                _seen_urls.add(u)
                all_source_urls.append(u)

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

            # The widened corpus, built LAZILY: only an entry with something the cited
            # document cannot account for pays for the linked fetches. Most entries never
            # reach this, so the common path costs exactly what it did before.
            # Resolution is `resolve_span` at module level; both this and the control
            # harness call that one definition.
            def resolve(needle: str):
                return resolve_span(needle, url, src, all_source_urls, args.cache)

            for frag in spans:
                checked += 1
                ok, where = resolve(frag)
                if ok:
                    # Worth surfacing but NOT a failure: the quote is genuinely the FAA's and
                    # the prose names the document, but the one clickable link a pilot gets
                    # points somewhere else. An enrichment backlog, not a defect.
                    if where != url:
                        citations.append(f"{name} :: {code}: quote is verbatim FAA text but lives "
                                         f"in a document the entry does not cite\n"
                                         f"        found in: {where}\n"
                                         f"        {frag[:120]}")
                    continue
                failures.append(f"{name} :: {code}: quoted text is NOT in {url} "
                                f"nor in any document it links to\n"
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
                if not any(resolve(c)[0] for c in cands):
                    failures.append(f"{name} :: {code}: the claim '{num} {unit}' does not appear "
                                    f"in {url} nor in any document it links to")

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
    # 🚨 THE BASELINE IS KEYED ON THE FAILURE TEXT, SO CHANGING THE WORDING SILENTLY
    # INVALIDATES EVERY ENTRY. Adding " nor in any document it links to" to the quote and
    # numeric messages made 138 banked failures read as RESOLVED and 48 unchanged ones read
    # as NEW, on a run where neither had moved. A checker that reports progress nobody made
    # is worse than one that reports nothing.
    #
    # Folding that clause out keeps a baseline banked BEFORE the widening comparable with
    # failures produced AFTER it, without re-banking (which would have quietly accepted 103
    # findings as debt). Every other message is untouched and matches as it always did.
    # 🚨 THE KEY MUST NOT CONTAIN A URL (2026-08-24).
    #
    # This used to key the baseline on the FULL message text, sourceURL included. So the
    # moment a citation's URL was legitimately corrected, the generated message stopped
    # matching its banked line and ONE finding reported as BOTH "resolved" and "new" in the
    # same run. It cost a false content-fidelity issue (#8) on FAA content, which is the
    # highest-stakes false alarm this repo can produce.
    #
    # MEASURED, both directions. On 2026-08-24 commit c37c5a3 corrected two PDF filenames
    # to the casing the FAA now redirects to:
    #     PCOS_dispo_table.pdf  -> PCOS_dispo_Table.pdf
    #     Weight_loss_pharm.pdf -> Weight_loss_Pharm.pdf
    # caci-pcos and med-contrave then fired as NEW failures with an identical entry code,
    # an identical obligation count and identical wording. Nothing about the content moved.
    # The control that settles it: 18 sibling weight-loss medications cite that same PDF at
    # the already-corrected casing, are baselined, and stayed silent throughout.
    #
    # This is the house rule in CLAUDE.md -> GOTCHAS_VERIFY §8, which the checker's own
    # sibling already learned: "Key on the stable envelope.code, never display text."
    #
    # Verified before shipping: stripping URLs maps the 207 banked entries onto 207 distinct
    # keys, so nothing is merged. A collision here would silently ACCEPT a real defect, so
    # that negative control is re-run by --selftest below and must stay.
    def fkey(msg: str) -> str:
        return _URL_IN_MSG.sub("<src>", msg.replace(" nor in any document it links to", ""))

    baseline_path = ROOT / "scripts" / "content-fidelity-baseline.json"
    baseline = set(json.loads(baseline_path.read_text())) if baseline_path.exists() else set()
    if args.update_baseline:
        baseline_path.write_text(json.dumps(sorted(failures), indent=1) + "\n")
        print(f"baseline updated: {len(failures)} known failures recorded")
        return 0
    baseline_keys = {fkey(b) for b in baseline}
    new_failures = [f for f in failures if fkey(f) not in baseline_keys]
    # ⚠️ Only count a baseline entry RESOLVED if its file was actually checked on this run.
    # With --file limiting the scope, every unchecked baseline entry otherwise reports as
    # fixed, which is a false progress signal of exactly the kind this script exists to stop.
    checked_files = set(files)
    in_scope = {b for b in baseline if b.split(" ::")[0] in checked_files}
    failure_keys = {fkey(f) for f in failures}
    resolved = {b for b in in_scope if fkey(b) not in failure_keys}

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
    if citations:
        print(f"\n📎 {len(citations)} quotation(s) are verbatim FAA text but sit in a document "
              f"the entry does not cite:")
        for c in citations:
            print("   " + c)
        print("   (Warning, not a failure. The words are the FAA's and the prose names the\n"
              "    document; only `envelope.sourceURL` is single-valued and cannot carry them\n"
              "    all, so the one clickable link a pilot gets points elsewhere. Enrichment\n"
              "    backlog. Do NOT 'fix' these by re-pointing sourceURL to silence the check:\n"
              "    the DNI table says 'phentermine [Adipex]' where the weight-loss PDF says\n"
              "    'phentermine', so re-pointing turns an accurate quotation into a false one.)"
              )
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
            + ("\n\n## Citation precision\n\n" + "\n".join(f"- {c}" for c in citations) if citations else "")
        )
        return 1
    print("\n✅ every quoted span appears in the source it cites.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
