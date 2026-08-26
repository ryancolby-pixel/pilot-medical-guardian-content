# FAA source audit — 2026-08-26

**Why this exists.** Ryan, after I answered "calendar months" wrong from a single document:
*"You need to double check everything in this database against the FAA website. This cant happen."*

Every record that carries a checkable claim was read against the FAA source it cites. The FAA
documents were fetched fresh that day (51 unique sources, HTML + PDF, 0 fetch failures).

## What was run

| pass | scope | result |
|---|---|---|
| `check-content-fidelity.py` (existing) | 778 quoted spans, 11 files | **1 new failure** — a fabricated FAA quote |
| `check-med-claims.py` (existing) | 3 claim classes on 214 meds | pass |
| `validate.py` (existing) | shape + manifest | pass |
| `scripts/check-field-claims.py` (**new, this day**) | 100 numeric/structured claims | 5 findings, 3 resolved as non-defects |
| **Reading pass** (61 agents) | **260 records vs their cited source** | **306 raw findings** |
| Adversarial verify | 123 priority candidates | **61 verified · 26 confirmed · 35 refuted** |

## 🚨 UNFINISHED — this is the resume point

- **62 of the 123 priority candidates were never verified.** The run was stopped on Ryan's call
  ("You are burning through a lot of tokens"). The real defect count is higher than 26.
- **20 confirmed MEDIUM are unfixed.** Dominant pattern: CACI records citing a **disposition table**
  rather than the **CACI worksheet** — the PDFs say so in their own headers.
- ⚖️ **173 of the 306 raw findings are an expected noise class** ("claim lives in a sibling FAA doc
  the record names in prose"). Do not treat those as defects without reading them.

## Files

- `AUDIT-RESULTS.json` — the 61 verdicts, joined to their finding. `isReal` is the verdict.
- `priority-findings.json` — the 123 HIGH/MEDIUM candidates, indexed. `AUDIT-RESULTS.index` keys into this.
- `all-findings.json` — all 306 raw findings, including the noise class.

🚫 The fetched FAA corpus was NOT committed (session scratchpad, ~450KB). Re-fetch it; fresher is better.

## Fixed and PUBLISHED LIVE the same day (content `46a3610`)

See that commit message for the full account. Six HIGH defects, each re-checked by hand against the
cached source before editing, all gates re-run, and **verified on the live CDN**, not merely pushed.

## ⚠️ Two process facts worth carrying forward

1. **The push did not deploy.** Remote `HEAD` was the fix commit while the CDN still served the old
   bytes; no Pages run fired. Recovered with `gh workflow run "Deploy site to Pages"` and confirmed by
   `last-modified` on the live URL. `GOTCHAS_CONTENT §2`, live again. **Nobody would have noticed.**
2. **A gate improved a fix.** After correcting `med-fexofenadine`, obligation-coverage flagged that the
   entry was silent on *"Airmen who are exhibiting symptoms, regardless of the treatment used, must not
   fly."* Being on an acceptable medication is not clearance to fly, and the entry had never said so.
   That check is the only one that can see OMISSION.

---

# Session 2, 2026-08-26 evening — the confirmed list is DONE; two clusters remain

Resumed at the stopping point above. **No agents, no workflows.** Everything below was read
against a freshly fetched FAA source, with negative controls, before anything was edited.
Published live and verified on the CDN (content `61e110a`, `generatedAt 2026-08-26T21:47:50Z`,
confirmed by `last-modified` and by reading four corrected records back off the live URL).

## 🚨 THE FAA REPUBLISHED SIX DOCUMENTS WE CITE, ON 2026-08-26

Measured by re-downloading all **61 cited PDFs** and hashing against the local cache:
**56 unchanged, 0 fetch failures, 6 changed** — all stamped `08/26/2026`.

| document | was | now |
|---|---|---|
| `Weight_loss_Pharm.pdf` | 04/29/2026 | 08/26/2026 |
| `CACI-Pre-Diabetes_Worksheet.pdf` | 04/29/2026 | 08/26/2026 |
| `CACI_weight_loss_management.pdf` | 04/29/2026 | 08/26/2026 |
| `diabetesmeds_acceptablecomb.pdf` | 08/27/2025 | 08/26/2026 |
| `SSRI_Recertification_Aid.pdf` | **12/28/2022** | 08/26/2026 |
| `HIMS_AME_Checklist_SSRI_Recertification.pdf` | **12/28/2022** | 08/26/2026 |

The weight-loss PDF **halved its observation period**: `"Two (2) weeks after starting for weight
loss."` became `"One (1) week"`. Four of our records quoted the superseded sentence. Confirmed
against the Wayback copy of 08/27/2025, which still reads two weeks. ⚖️ Our text was correct when
written; the source moved under it.

⚠️ **The full fidelity check was re-run against the new copies of all six: 841 spans, 0 new
failures.** So nothing else we quote was invalidated by this FAA publication run.

## ✅ FIXED AND LIVE THIS SESSION (content `61e110a`)

| what | records | direction |
|---|---|---|
| Sleep aids dropped the FAA's `"Daily/nightly use of sleep aids is not allowed regardless of the underlying cause or reason."` | 5 (+1 note) | **more restrictive** |
| Hypertension said CACI applies with **no qualifier at all**; Item 36 requires `"Treated with 3 or fewer* acceptable medications"` and defers otherwise | 10 | **more restrictive** |
| Weight-loss observation period, superseded quote | 4 (+19 citation dates) | matches source |
| A disposition table cited as a `"CACI ... Worksheet"` | 14 | naming only |
| Diabetes row B's 4th disposition line (`"Follow up Special Issuances - See Diabetes Mellitus - Type II, Medication Controlled (Not Insulin)"`) was cut | 4 | additive |
| `med-dofetilide` carried `faaStatus: notAcceptable` on an `informationalOnly` record | 1 | see below |
| `med-tamsulosin` asserted `"Generally acceptable"` | 1 (2 fields) | more conservative |
| `med-zyban` attached `> 6 months` to *recurrent* treatment as well as *extended* therapy | 1 | more restrictive |
| `med-pioglitazone` put a rationale in the FAA's mouth | 1 | descriptive |
| BasicMed stated 61.113(a) as a blanket bar, dropping its own `"Except as provided in paragraphs (b) through (h)"` | 2 | **more permissive** |

⚖️ **The audit under-counted almost every cluster.** It flagged 5 hypertension records; **8 had no
qualifier at all** and 2 more were only partly scoped. It flagged 3 sleep aids; **5** dropped the
prohibition. It flagged 8 CACI citations; **all 14** disposition tables were misnamed. ⇒ when a
finding names a pattern, **sweep the whole file for that pattern** rather than fixing the named rows.

## 🔬 TWO MECHANICAL CHECKS THAT GENERALISED A SINGLE FINDING

- **`informationalOnly` implies no interpretive status** (the invariant is written into
  `FAAMedicationEntry.swift`). Swept all 214: **exactly one violation**, `med-dofetilide`. 77 other
  `informationalOnly` records pass, which is the control that makes the negative meaningful.
- **Acceptability-verdict sweep** over `faaStatusDescription` / `treatedConditionNote` /
  `informationalNote`: **one unattributed verdict**, `med-tamsulosin`. The one other hit
  (`med-orlistat`) is inside a quoted FAA phrase and is fine. All 15 sibling `treatedConditionNote`s
  are descriptive.

## 🛑 STILL OPEN — 53 of the 62, in two clusters

**1. DNI/DNF conflation — 18 findings, 26 records carry the wording.** Records say the drug is
*"addressed under FAA Do Not Issue / Do Not Fly guidance; the AME does not issue without FAA
review."* The source keeps these **separate**: DNI = *"AMEs cannot issue. Clearance from the FAA
required."*; DNF = *"AMEs must provide additional safety information ... and caution them not to
fly"*, deferring only *"if applicant is using the following medications routinely"*. The merged
label attaches the **DNI consequence** to DNF drugs.

🚫 **NOT MECHANICALLY RESOLVABLE, AND DELIBERATELY LEFT ALONE.** The tables list *classes* with
"including but not limited to", so most of our drugs are not named at all. Classifying them means
clinical judgement in both directions, and a wrong call is harmful either way:
- benzodiazepines are DNF under `ANTI-ANXIETY` — but clonazepam is also an anticonvulsant, and
  `SEIZURE MEDICATIONS` is **DNI** *"even if used for non-seizure conditions"*
- gabapentin / pregabalin: are gabapentinoids "seizure medications" for FAA purposes?
- ADHD agents (incl. non-stimulant atomoxetine) read as **DNI** under `PSYCHIATRIC OR PSYCHOTROPIC`
- opioids and muscle relaxants read as **DNF**
- `med-ondansetron` (antiemetic) and `med-levocetirizine` (2nd-gen antihistamine; the DNF entry is
  **1st**-generation) appear in **neither** table and may not belong in this cluster at all

▶️ **This is the first thing in the audit that wants an AME's eye rather than a careful reader's.**

**2. "The cited page indexes a class-level document" — 35 findings.** Records say *"Not individually
listed in an FAA medication list"* while citing `pharm/`, whose own index links a dedicated FAA
document for that class (Cholesterol Medication, Contraceptives and HRT, Over the Counter,
Erectile Dysfunction and BPH, Migraine, Osteoporosis...). ⚖️ **This is the UNDERSELLING shape of
`GOTCHAS_CONTENT §17`, not overclaiming** — we tell a pilot the FAA is silent when a class-specific
FAA document exists. Lower stakes than cluster 1, and a well-defined batch: for each record, check
whether the class document names the drug, and repoint the citation if it does.

## 🚨 AND THE TWO WATCHERS CANNOT SEE ANY OF THIS

- **`check-source-freshness.py` is blind to PDFs.** It reads the HTML `Last updated:` line, and
  scores **32 of 38 HTML pages dated, 0 of 34 PDFs**. FAA PDFs carry `(Updated MM/DD/YYYY)` *inside
  the document*. It is the gate built for exactly today's event and it could not have fired.
  ⚠️ The registry is also **stale**: seeded 2026-08-07, and `Weight_loss_Pharm.pdf` — the file that
  actually moved — **is not in it at all**.
- **`check-content-fidelity.py` never re-downloads.** `_blob()` is `if not blob.exists(): download`,
  so a cached FAA document is reused forever, while `fetch()`'s own docstring claims *"downloads stay
  fresh every time."* Locally it was still reading the **April** PDF fetched **Aug 14**, which is why
  a correct fix first appeared as 8 fabricated quotes. ✅ **CI is unaffected** — `.fidelity-cache/` is
  gitignored, so runners start cold. ⇒ **the failure mode is local-only and it inverts the verdict:
  it reports a correct correction as a fabrication.**

---

## 🚨 SESSION 2b — CI CAUGHT WHAT THE LOCAL RUN DID NOT, AND IT WAS REAL

**The local "841 spans, 0 new" result reported earlier in session 2 was NOT verification.** Two
compounding errors: it was run **before** the last five edits (CACI citations, diabetes, zyban,
pioglitazone, BasicMed), and the cache was stale for the very document at issue. ⚠️ **`Weight_loss_Pharm`
and `diabetesmeds_acceptablecomb` are each cited under TWO different URLs** (short `/ame_guide/...` and
long `/about/office_org/.../ame_guide/...`), which are **two different cache keys**. Clearing one leaves
the other serving 2025 bytes. CI, running cold, was right: **19 new failures.**

⇒ **Never report a gate result that predates your last edit, and clear the cache by CONTENT not by URL.**

### The FAA rewrote two more documents, both dated 08/26/2026

**1. `diabetesmeds_acceptablecomb.pdf` — every group letter changed.** The chart now carries the FAA's
own banner: **`** NOTE: ALL medication Group Letters have been updated **`**. Six records were wrong:

| our text | the chart now |
|---|---|
| metformin **Group A** (Biguanides) | **Group B** |
| liraglutide / semaglutide / dulaglutide **Group C** | **Group D** |
| tirzepatide **Group C** | **Group D** (GLP-1 / GIP sits inside D) |
| `"...from each group (A-F)"` | `"Only ONE Medication allowed from each group (A–G)"` |
| `"3 days"` switching within a class | `"Within Group B-G"` is **48 hours** |

**2. `special_iss/all_classes/asthma` 404s — the AASI protocol moved to `media/AASI_Asthma.pdf` and was
REWRITTEN** (also 08/26/2026). ⚖️ **Asthma is absent from the FAA's 26-condition AASI index and the FAA's
own Item 35 page still links the dead URL**, so their side is inconsistent; the content is alive, at a new
address. **None of our four quoted sentences survived the rewrite.** Substantive changes:
- the note must now come from the **treating pulmonologist**, **annually**, within 90 days
- **the "3 or more medications for stabilization" deferral trigger is GONE.** The defer list is now three
  items: worsening / increased ER visits, `"The FEV1 is less than 70% predicted value"`, and steroids
  `"more than 20 mg of prednisone per day"`
- `"The Examiner must defer to the AMCD or Region"` is now `"The AME must defer recertification if:"`

⇒ **A link probe of all 130 cited sources found exactly ONE dead URL.** That probe is cheap and belongs in
a gate; `check-source-links.py` reports "All 150 reachable cited sources resolve" because it counts
reachable ones.

### ⚖️ A QUOTE THAT ONE EXTRACTOR FINDS AND ANOTHER DOES NOT IS NOT A QUOTE

`"Group D not allowed with Meglitinides"` is a **narrow graphical callout in the margin**. pypdf reads it
contiguously; **pdfplumber, which the checker uses, interleaves it with the drug list beside it.** It was
written as a verbatim quotation on the strength of the pypdf read alone. ⇒ **Before quoting anything from
a PDF, check contiguity with the extractor the GATE uses**, and when they disagree, **make the weaker
claim**: it now reads "The chart also marks Group D as not allowed with Meglitinides", no quotation marks.

### ✅ The obligation-coverage check earned its keep three more times
It found the rewritten diabetes chart's new **`"Initial Certification/Clearance decision is made by the
FAA. The AME must defer."`** missing from `si-dm2-med-list`, and the AASI note's full required contents
missing from both `si-asthma-med-list` and `si-asthma-pft`. **It is still the only check that can see an
omission**, and every time it fires it improves the entry rather than just passing it.

### Final state
`validate` · `check-med-claims` · `check-verification-age` · `check-source-links` · `verify_manifest` all
pass. **`check-content-fidelity`: 860 spans, 0 new, and the baseline SHRANK by 2.** `check-field-claims`
still reports its 5 pre-existing findings (incl. the courier address Ryan closed) and is not a CI gate.
