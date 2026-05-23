#!/usr/bin/env python3
"""
Path B re-classification audit (CONTENT_PIPELINE.md §13.1, 2026-05-23).

Re-classifies the bundled draft content per Path B's narrow tier definitions:
  - Tier A — content reproduced verbatim from a named FAA publication with a
    section citation. The `reviewStatus` envelope field is removed (no badge,
    no "Drafted" date label). No AME medical review needed.
  - Tier B — interpretive content where the curator made a call beyond
    reproduction. Keeps `reviewStatus: "draft"` until AME sign-off.

Classification rules (citation-based, conservative — anything ambiguous stays
Tier B for safety):

  medications.json:
    Tier A if envelope.sourceCitation matches a finite FAA-published list:
      - contains "CACI" (CACI worksheets — FAA publishes the named drug
        classes / acceptable meds in each)
      - contains "Do Not Issue" or "Do Not Fly" (FAA-published DNI/DNF list)
      - contains "SSRI Decision Path" (FAA-published protocol — 4 named SSRIs)
      - contains "Insulin-Treated) protocol" (FAA-published Diabetes protocol)
    Else Tier B.

  si_requirements.json:
    Conservative: ALL stay Tier B. The requirement text is the curator's
    plain-English checklist version, not a verbatim Guide quotation. If we
    later author verbatim-quoted requirements we'll flag those individually.

  si_conditions.json:
    ALL stay Tier B. `summary` + `pathGuidance` are inherently paraphrased.

  thresholds.json:
    Tier A: the 2 BP entries (quote the AME Guide's 155/95 figure verbatim with
    section citation) AND the 7 already-Tier-A entries (no FAA number).
    Net: all thresholds are Tier A under Path B.

Files NOT touched (already Tier A or out of scope):
  cert_durations.json (14 CFR — already Tier A)
  item18.json (Form 8500-8 catalog — already Tier A)
  ame_directory.json (HIMS list — already Tier A; enrichment review pending)
  manifest.json (build artifact)
"""

import json
import sys
from pathlib import Path

CONTENT_DIR = Path(__file__).resolve().parent.parent / "v1"

TIER_A_PATTERNS = ("CACI", "Do Not Issue", "Do Not Fly",
                   "SSRI Decision Path", "Insulin-Treated) protocol")


def classify_medication(citation: str) -> str:
    return "A" if any(p in citation for p in TIER_A_PATTERNS) else "B"


def process_medications(path: Path) -> tuple[int, int]:
    data = json.loads(path.read_text())
    a_count, b_count = 0, 0
    for entry in data:
        citation = entry["envelope"].get("sourceCitation", "")
        tier = classify_medication(citation)
        if tier == "A":
            # Drop reviewStatus so the app renders without the pending badge.
            entry["envelope"].pop("reviewStatus", None)
            a_count += 1
        else:
            # Force-set to "draft" — explicit Tier B until AME sign-off.
            entry["envelope"]["reviewStatus"] = "draft"
            b_count += 1
    # Pretty-print with stable key order so the diff is reviewable.
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    return a_count, b_count


def process_thresholds(path: Path) -> tuple[int, int]:
    """All thresholds → Tier A under Path B (no-number entries are verifiable
    absence; numeric ones quote the AME Guide verbatim with section citation)."""
    data = json.loads(path.read_text())
    a_count = 0
    for entry in data:
        entry["envelope"].pop("reviewStatus", None)
        a_count += 1
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    return a_count, 0


def process_keep_all_b(path: Path) -> tuple[int, int]:
    """SI conditions + SI requirements: conservatively all Tier B (paraphrased)."""
    data = json.loads(path.read_text())
    b_count = 0
    for entry in data:
        entry["envelope"]["reviewStatus"] = "draft"
        b_count += 1
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    return 0, b_count


def main() -> int:
    print(f"Path B re-classification audit — content dir: {CONTENT_DIR}\n")

    total_a, total_b = 0, 0
    results: list[tuple[str, int, int]] = []

    for name, processor in [
        ("medications.json", process_medications),
        ("thresholds.json", process_thresholds),
        ("si_conditions.json", process_keep_all_b),
        ("si_requirements.json", process_keep_all_b),
    ]:
        path = CONTENT_DIR / name
        if not path.exists():
            print(f"  SKIP  {name} — not found")
            continue
        a, b = processor(path)
        results.append((name, a, b))
        total_a += a
        total_b += b
        print(f"  DONE  {name}: {a} Tier A, {b} Tier B")

    print(f"\nTotal: {total_a} Tier A, {total_b} Tier B")
    print(f"AME review scope (Tier B): {total_b} entries\n")
    print("Untouched (already Tier A or out of audit scope):")
    print("  cert_durations.json, item18.json, ame_directory.json, manifest.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
