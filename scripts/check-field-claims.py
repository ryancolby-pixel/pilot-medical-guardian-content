#!/usr/bin/env python3
"""Field-claim verification: numeric and structured facts vs the FAA's own pages.

The layer no existing check covers. check-content-fidelity verifies QUOTED SPANS;
check-med-claims verifies three medication claim classes. Nothing has ever compared a
NUMBER or a STRUCTURED FIELD (a duration, a threshold, an item-18 letter description,
an address line) against the source that the record cites.

Born 2026-08-26, the day "calendar months" was answered wrong from a single document.

Method notes (from GOTCHAS_VERIFY):
- curl with a browser UA, never urllib.
- Every source gets a CONTROL probe before any negative is believed.
- A source that cannot be fetched is a HARD ERROR, never a silent skip.
- PDFs via pdfplumber.
"""
import json, re, subprocess, sys, html
from pathlib import Path

V1 = Path("/Users/ryan/pilot-medical-guardian-content/v1")
CACHE = Path(sys.argv[1] if len(sys.argv) > 1 else "/tmp/faa-cache"); CACHE.mkdir(parents=True, exist_ok=True)
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36"

def fetch(url):
    key = re.sub(r'[^A-Za-z0-9]+', '_', url)[-120:]
    fp = CACHE / key
    if not fp.exists():
        r = subprocess.run(["curl", "-sL", "--max-time", "60", "-A", UA, url, "-o", str(fp), "-w", "%{http_code}"],
                           capture_output=True, text=True)
        if r.stdout.strip() != "200":
            fp.unlink(missing_ok=True)
            return None, f"HTTP {r.stdout.strip()}"
    raw = fp.read_bytes()
    if url.lower().endswith(".pdf") or raw[:4] == b"%PDF":
        try:
            import pdfplumber
            with pdfplumber.open(fp) as pdf:
                parts = []
                for pg in pdf.pages:
                    parts.append(pg.extract_text() or "")
                    for tb in (pg.extract_tables() or []):
                        parts.append(" ".join(" ".join(c or "" for c in row) for row in tb))
                text = " ".join(parts)
        except Exception as e:
            return None, f"pdf: {e}"
    else:
        text = raw.decode("utf-8", "replace")
        text = re.sub(r'<(script|style)[^>]*>.*?</\1>', ' ', text, flags=re.S | re.I)
        text = html.unescape(re.sub(r'<[^>]+>', ' ', text))
    return re.sub(r'\s+', ' ', text).lower(), None

def norm(s): return re.sub(r'\s+', ' ', s.replace("’","'").replace("–","-").replace("—","-")).lower().strip()

findings, checked = [], 0
def check(ok, label, detail=""):
    global checked; checked += 1
    if not ok: findings.append(f"{label}: {detail}")

def load(name):
    d = json.load(open(V1 / f"{name}.json"))
    return d if isinstance(d, list) else d.get("entries", [])

# ---------- 1. cert_durations vs the AME Guide validity page ----------
VALIDITY = "https://www.faa.gov/ame_guide/app_process/general/validity"
page, err = fetch(VALIDITY)
if err: findings.append(f"FETCH FAIL {VALIDITY}: {err}")
else:
    assert "calendar months" in page and "remainder of the month of issue" in page, "CONTROL failed on validity page"
    # The FAA matrix: (cert class, privilege class, under-40?) -> months
    faa = {("first","first",True):12, ("first","first",False):6, ("first","second",None):12,
           ("first","third",False):24, ("first","third",True):60,
           ("second","second",None):12, ("second","third",False):24, ("second","third",True):60,
           ("third","third",False):24, ("third","third",True):60}
    for e in load("cert_durations"):
        cert, priv = e["certificateClassRaw"], e["privilegeClassRaw"]
        bracket = True if e.get("ageThreshold") else (None if (cert,priv,None) in faa else False)
        want = faa.get((cert, priv, bracket))
        check(want == e["durationMonths"],
              f"cert_durations/{e['envelope']['code']}",
              f"record says {e['durationMonths']} months; AME Guide matrix says {want}")
        # The record must also agree with the words on the page: "N calendar months"
        check(f"{e['durationMonths']} calendar months" in page or f"{e['durationMonths']}-calendar months" in page,
              f"cert_durations/{e['envelope']['code']}/phrase",
              f"'{e['durationMonths']} calendar months' not on validity page")

# ---------- 2. thresholds: BP numbers vs Item 55 ----------
ITEM55 = "https://www.faa.gov/ame_guide/app_process/exam_tech/item55/amd"
page, err = fetch(ITEM55)
if err: findings.append(f"FETCH FAIL {ITEM55}: {err}")
else:
    assert "blood pressure" in page, "CONTROL failed on item55"
    for e in load("thresholds"):
        if e["envelope"]["sourceURL"] != ITEM55: continue
        n = e.get("numericThreshold")
        if n: check(str(int(n)) in page, f"thresholds/{e['envelope']['code']}",
                    f"numericThreshold {n} not found on Item 55 page")
        # every quoted number inside the description must be on the page
        for num in re.findall(r'\b\d{2,3}\b', e["thresholdDescription"]):
            check(num in page, f"thresholds/{e['envelope']['code']}/num{num}",
                  f"number {num} in description absent from Item 55 page")

# ---------- 3. BasicMed months vs eCFR 61.23(c)(3) / 68.3 / 68.7 ----------
ECFR6123 = "https://www.ecfr.gov/current/title-14/chapter-I/subchapter-D/part-61/subpart-A/section-61.23"
page, err = fetch(ECFR6123)
if err: findings.append(f"FETCH FAIL {ECFR6123}: {err}")
else:
    # eCFR serves partial content to non-browser agents; the two BasicMed clauses survived
    # the earlier curl. CONTROL on them specifically.
    ok24 = "24 calendar months" in page; ok48 = "48 calendar months" in page
    check(ok24, "basicmed/61.23-course", "'24 calendar months' not in fetched 61.23")
    check(ok48, "basicmed/61.23-exam", "'48 calendar months' not in fetched 61.23")
    for e in load("basicmed_requirements"):
        body = norm(e.get("body", ""))
        for m in re.findall(r'(\d{2}) calendar months', body):
            check(f"{m} calendar months" in page, f"basicmed/{e['envelope']['code']}/{m}mo",
                  f"'{m} calendar months' claimed, absent from 61.23")

# ---------- 4. item18: each letter's description vs its cited page ----------
for e in load("item18"):
    url = e["envelope"]["sourceURL"]
    page, err = fetch(url)
    if err: findings.append(f"FETCH FAIL {url}: {err}"); continue
    check("item 18" in page or "8500-8" in page or "applicant history" in page,
          f"item18/{e['envelope']['code']}/control", "control phrase missing from cited page")
    # the letter's own description, normalised, should appear on the page
    desc = norm(e["description"])
    frag = desc.split(". ")[0][:60]  # first sentence, first 60 chars
    check(frag in page, f"item18/{e['envelope']['code']}",
          f"description fragment not on cited page: {frag!r}")

# ---------- 5. submission addresses vs the coversheet PDF ----------
for e in load("faa_submission_addresses"):
    url = e["envelope"]["sourceURL"]
    page, err = fetch(url)
    if err: findings.append(f"FETCH FAIL {url}: {err}"); continue
    check("aerospace medical certification" in page, f"addr/{e['envelope']['code']}/control", "control missing")
    for line in e["recipientLines"]:
        l = norm(line)
        if l in ("federal aviation administration",): continue
        check(l in page, f"addr/{e['envelope']['code']}",
              f"address line not in coversheet PDF: {line!r}")

print(f"CHECKED {checked} claims")
if findings:
    print(f"\n{len(findings)} FINDINGS:")
    for f in findings: print(f"  ❌ {f}")
    sys.exit(1)
print("✅ all field claims verified against their cited sources")
