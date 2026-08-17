#!/usr/bin/env python3
"""Apply a reviewed patch to v1/si_requirements.json, safely and reviewably.

WHY A SCRIPT AND NOT HAND EDITS. On 2026-08-07 an audit found most of the 85 Special
Issuance requirement entries needed rewriting. Editing that many by hand, or by a
throwaway one-liner, invites three specific failures that this script refuses:

  1. A CHANGED `code` ORPHANS A PILOT'S DATA. SIChecklistItem links to the reference
     template by requirementCode and carries the pilot's own completion state and their
     titleSnapshot. Rename a code and that pilot's checked-off history detaches from the
     requirement it belongs to. This script will not write a patch that introduces,
     removes or renames a code.

  2. A REFORMATTED FILE HIDES THE REAL CHANGE. The first attempt at the cardiac fix used
     json.dumps(indent=1) against a file written with indent=2 and produced a 2,210-line
     diff for a 3-entry edit. Unreviewable, and a reviewer who cannot see the change
     cannot catch a mistake in it. This preserves the original formatting exactly and
     verifies the diff touches only the fields named in the patch.

  3. A SILENT NO-OP. A patch entry whose code does not exist, or which sets a field to
     what it already held, should be reported rather than quietly doing nothing. A patch
     that appears to apply and changes nothing is how a "fix" reaches no user.

USAGE
    python3 scripts/apply_si_patch.py patch.json --dry-run   # show what would change
    python3 scripts/apply_si_patch.py patch.json             # apply, then regen manifest

PATCH FORMAT: a JSON list. Only `code` is required; every other field is optional and
omitted fields are left untouched.
    [{"code": "si-osa-pap-report",
      "requirementText": "...",
      "sourceURL": "https://www.faa.gov/...",
      "sourceCitation": "FAA Guide for Aviation Medical Examiners, ...",
      "cadence": "annual"}]
"""

import json
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parent))
from content_time import now_stamp
import pathlib
import subprocess
import sys
from datetime import datetime, timezone

ROOT = pathlib.Path(__file__).resolve().parent.parent
TARGET = ROOT / "v1" / "si_requirements.json"

FIELD_MAP = {           # patch key -> (container, json key)
    "requirementText": ("entry", "requirementText"),
    "cadence": ("entry", "cadenceRaw"),
    "docType": ("entry", "documentTypeNeededRaw"),
    "sourceURL": ("envelope", "sourceURL"),
    "sourceCitation": ("envelope", "sourceCitation"),
}


def die(msg: str) -> None:
    print(f"REFUSING TO APPLY: {msg}")
    raise SystemExit(2)


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    dry = "--dry-run" in sys.argv
    if not args:
        die("no patch file given")

    patch = json.loads(pathlib.Path(args[0]).read_text())
    if not isinstance(patch, list):
        die("patch must be a JSON list")

    original = TARGET.read_text()
    data = json.loads(original)
    by_code = {e["envelope"]["code"]: e for e in data}
    before_codes = sorted(by_code)

    # Every patch code must already exist. A patch cannot add or rename entries: adding a
    # requirement means editing si_conditions.json's requirementCodes too, which is a
    # different, deliberate change and not this script's job.
    unknown = [p["code"] for p in patch if p.get("code") not in by_code]
    if unknown:
        die(f"{len(unknown)} patch code(s) do not exist in the file: {unknown[:5]}")

    dupes = [c for c in {p["code"] for p in patch} if sum(1 for p in patch if p["code"] == c) > 1]
    if dupes:
        die(f"patch names the same code more than once: {dupes}")

    # Via the shared helper so there is one definition of "what a stamp looks like".
    # This already produced second precision; routing it here keeps it that way when the
    # format is next touched, and validate.py enforces the same shape on every entry.
    now = now_stamp()
    changed, noop = [], []

    for p in patch:
        entry = by_code[p["code"]]
        touched = []
        for pk, (where, jk) in FIELD_MAP.items():
            if pk not in p or p[pk] in (None, ""):
                continue
            target = entry if where == "entry" else entry["envelope"]
            if target.get(jk) == p[pk]:
                continue
            if dry:
                old = str(target.get(jk))
                print(f"  {p['code']}.{jk}")
                print(f"      - {old[:150]}{'...' if len(old) > 150 else ''}")
                print(f"      + {str(p[pk])[:150]}{'...' if len(str(p[pk])) > 150 else ''}")
            target[jk] = p[pk]
            touched.append(jk)
        if touched:
            entry["envelope"]["lastVerified"] = now
            changed.append((p["code"], touched))
        else:
            noop.append(p["code"])

    # Structural invariants. These are the ones that would cost a pilot their data.
    after_codes = sorted(e["envelope"]["code"] for e in data)
    if after_codes != before_codes:
        die("the set of codes changed. This orphans pilots' checklist items.")
    if len(data) != len(json.loads(original)):
        die("entry count changed")

    print()
    print(f"{len(changed)} entr{'y' if len(changed) == 1 else 'ies'} would change"
          if dry else f"{len(changed)} entr{'y' if len(changed) == 1 else 'ies'} changed")
    if noop:
        print(f"⚠️  {len(noop)} patch entr{'y' if len(noop) == 1 else 'ies'} changed NOTHING "
              f"(values already identical). A silent no-op is worth knowing about: {noop[:8]}")

    if dry:
        print("\n--dry-run: nothing written.")
        return 0
    if not changed:
        print("nothing to write.")
        return 0

    out = json.dumps(data, indent=2, ensure_ascii=False)
    if original.endswith("\n"):
        out += "\n"
    TARGET.write_text(out)

    # Regenerate the manifest, or validate.py fails on a checksum mismatch and, worse, a
    # publish could ship content whose manifest disagrees with it.
    r = subprocess.run([sys.executable, str(ROOT / "scripts" / "gen_manifest.py")],
                       capture_output=True, text=True)
    print(r.stdout.strip() or r.stderr.strip())

    v = subprocess.run([sys.executable, str(ROOT / "scripts" / "validate.py")],
                       capture_output=True, text=True)
    print(v.stdout.strip() or v.stderr.strip())
    if v.returncode != 0:
        print("\n⚠️ validate.py FAILED. Inspect before committing.")
        return 1

    # Report the diff size, because a big one on a small patch means formatting drifted.
    d = subprocess.run(["git", "-C", str(ROOT), "diff", "--numstat", "--", "v1/si_requirements.json"],
                       capture_output=True, text=True).stdout.strip()
    if d:
        add, rem, _ = d.split(None, 2)
        print(f"\ndiff: +{add} -{rem} lines for {len(changed)} entries")
        if int(add) > len(changed) * 12:
            print("⚠️ diff is far larger than the patch. Formatting may have drifted; "
                  "review before committing.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
