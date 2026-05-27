#!/usr/bin/env python3
"""
Apply the medication-scope reduction (Build 14, 2026-05-26 + 27).

Background: LAUNCH_BUDGET.md §10 + CONTENT_PIPELINE.md §12.6.

For medications PMG ships where the FAA doesn't name the drug in a published
list (CACI Worksheets / Do Not Issue / Do Not Fly / SSRI Decision Path /
Insulin-Treated protocol), PMG no longer renders an interpretive faaStatus.
Even AMAS calls their own medication DB "unofficial" — no third party can
authoritatively classify these. PMG's value for these meds remains intact on
the personal-record-keeping side (dose, frequency, condition, dates,
MedXPress Item 17 prep); what's removed is PMG rendering an opinion.

Concretely, for each Tier-B medication (citation does NOT match a named
FAA-published list):
  - faaStatus → removed (decodes to nil on the iOS side — switch flips
    from "show a status badge" to "show informational-only note")
  - isCACI → removed
  - preFlightWaitHours → removed
  - informationalOnly → added, set to true (new flag the iOS side reads)
  - informationalNote → added, plain-language note explaining the
    AME-determines posture and pointing at the broader AME Guide

  KEPT (still useful):
    - faaStatusDescription (cited prose remains the substantive content)
    - envelope.sourceCitation + sourceURL (broader AME Guide reference)
    - treatedConditionNote (when present)
    - reviewStatus: "draft" (the path_b_audit.py state — until AME signs off
      on the new informational note copy too; for now stays draft)

Idempotent: rerunning is a no-op once entries have informationalOnly: true.

Run:
    python3 scripts/apply_informational_only.py
"""

import json
import sys
from pathlib import Path

CONTENT_DIR = Path(__file__).resolve().parent.parent / "v1"
MEDS = CONTENT_DIR / "medications.json"

# Same Tier-A pattern set as path_b_audit.py — entries whose envelope
# sourceCitation contains any of these are Tier A (FAA names the drug).
# Everything else is Tier B (PMG was interpreting; under Build 14 scope
# reduction, we no longer interpret these — we surface informational only).
TIER_A_PATTERNS = (
    "CACI",
    "Do Not Issue",
    "Do Not Fly",
    "SSRI Decision Path",
    "Insulin-Treated) protocol",
)


def is_tier_a(entry: dict) -> bool:
    citation = entry.get("envelope", {}).get("sourceCitation", "")
    return any(p in citation for p in TIER_A_PATTERNS)


def build_informational_note(entry: dict) -> str:
    """Plain-language copy explaining the AME-determines posture for this
    medication. Names the drug + condition class so the note is specific."""
    generic = entry.get("genericName", "this medication")
    category = entry.get("category") or ""
    cond_note = entry.get("treatedConditionNote") or ""

    # Use the cited condition context when present; else fall back to category.
    context = ""
    if cond_note:
        context = " " + cond_note.rstrip(".") + "."
    elif category:
        context = f" The underlying condition class is: {category}."

    return (
        f"The FAA does not name {generic} in CACI, Do Not Issue / Do Not Fly, "
        f"or the SSRI Decision Path. Your AME determines acceptability based "
        f"on your underlying condition and the cited AME Guide section."
        f"{context} See the broader AME Guide reference cited below; PMG does "
        f"not render a status verdict for medications the FAA doesn't name."
    )


def apply_scope_reduction(path: Path) -> tuple[int, int, int]:
    """Returns (tier_a_count, tier_b_count, already_done_count)."""
    data = json.loads(path.read_text())
    a, b, noop = 0, 0, 0
    for entry in data:
        if is_tier_a(entry):
            # Leave alone — FAA names this drug. PMG renders the status.
            a += 1
            continue

        # Tier B — apply informational-only treatment.
        if entry.get("informationalOnly") is True:
            # Idempotent rerun — already done.
            noop += 1
            continue

        entry.pop("faaStatus", None)
        entry.pop("isCACI", None)
        entry.pop("preFlightWaitHours", None)
        entry["informationalOnly"] = True
        entry["informationalNote"] = build_informational_note(entry)
        b += 1

    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    return a, b, noop


def main() -> int:
    print(f"Medication scope reduction (Build 14) — content dir: {CONTENT_DIR}\n")
    if not MEDS.exists():
        print(f"  ERROR: {MEDS} not found")
        return 1
    a, b, noop = apply_scope_reduction(MEDS)
    print(f"  Tier A (FAA names the drug — unchanged): {a}")
    print(f"  Tier B (newly informational-only this run): {b}")
    print(f"  Already informational-only (idempotent no-op): {noop}")
    print(f"\n  Total entries processed: {a + b + noop}")
    print(f"\nNext steps:")
    print(f"  1. python3 scripts/validate.py")
    print(f"  2. CONTENT_VERSION=2026-05-27.6 python3 scripts/gen_manifest.py")
    print(f"  3. Sync bundled snapshot to app repo")
    return 0


if __name__ == "__main__":
    sys.exit(main())
