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
