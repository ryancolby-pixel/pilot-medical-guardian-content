#!/usr/bin/env python3
"""What the sheet guard writes to the secure link stacks' attestation record (check-sheet-quotes.yml, attest job).

Moved out of the workflow's bash (2026-11-14) so the decision has a selftest. The rule (SECURE_SEND_SPEC.md):
  - either check FOUND a problem (exit 1): write ok false at once, which takes the FAA quotes down;
  - both clean (exit 0), both read the same commit and data sha256, and the data re-downloaded HERE from the
    commit-pinned URL hashes to that same sha256 (this job runs no downloaded code): write ok true;
  - anything else (a check could not run, the checks disagree, the re-hash differs or fails, the check job died
    before reporting): write nothing, and the server's 36 hour age limit takes over.

Reads CODE_S, CODE_Q, AGREE, COMMIT, DATA_SHA from the environment and appends write=, ok= to $GITHUB_OUTPUT.

usage: sheet-attest-decide.py | sheet-attest-decide.py --selftest
Exit 0 always on a decision (writing nothing is a decision); exit 2 only if this script itself breaks.
"""
import hashlib
import os
import re
import sys
import urllib.request

RAW = "https://raw.githubusercontent.com/ryancolby-pixel/pmg-securelink-viewer/{}/sheet/sheet-data.json"
UA = "pmg-ops-check/1.0 (+https://pilotmedicalguardian.com)"


def rehash(commit: str) -> str | None:
    try:
        req = urllib.request.Request(RAW.format(commit), headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=60) as r:
            return hashlib.sha256(r.read()).hexdigest()
    except Exception as e:
        print(f"re-download failed: {type(e).__name__} {e}")
        return None


def decide(code_s: str, code_q: str, agree: str, commit: str, data_sha: str, rehash=rehash) -> tuple[bool, bool, str]:
    """(write, ok, why). rehash(commit) -> sha256 hex or None; only called when both checks are clean."""
    if code_s == "1" or code_q == "1":
        return True, False, "A check found a problem: revoking (ok false)."
    if code_s == "0" and code_q == "0" and agree == "true" and re.fullmatch(r"[0-9a-f]{40}", commit or "") \
            and re.fullmatch(r"[0-9a-f]{64}", data_sha or ""):
        own = rehash(commit)
        if own == data_sha:
            return True, True, f"Both checks clean on data sha256 {data_sha} (re-hashed here): ok true."
        return False, False, (f"The data at commit {commit} hashed to {own} here, not {data_sha}. Nothing written; "
                              "the age limit takes over.")
    return False, False, ("A check could not run (or the two read different data) and none found a problem. Nothing "
                          "written; the 36 hour age limit takes over.")


def selftest() -> int:
    C, D, E = "c" * 40, "d" * 64, "e" * 64
    calls = []

    def rh(sha):
        calls.append(sha)
        return D
    cases = [
        (("1", "2", "false", "", ""), (True, False)),     # a finding beside an instrument problem still revokes
        (("2", "1", "false", C, D), (True, False)),
        (("1", "1", "true", C, D), (True, False)),
        (("1", "0", "true", C, D), (True, False)),
        (("0", "1", "true", C, D), (True, False)),
        (("2", "0", "true", C, D), (False, False)),       # could not check: nothing written
        (("0", "2", "true", C, D), (False, False)),
        (("", "", "", "", ""), (False, False)),           # the check job died before reporting
        (("0", "0", "false", C, D), (False, False)),      # both clean, but on different data
        (("0", "0", "true", "main", D), (False, False)),  # no pinned commit
        (("0", "0", "true", C, ""), (False, False)),
        (("0", "0", "true", C, E), (False, False)),       # the re-hash here differs
        (("0", "0", "true", C, D), (True, True)),         # the only ok true
    ]
    for args, want in cases:
        got = decide(*args, rehash=rh)[:2]
        assert got == want, f"{args}: {got}, expected {want}"
    assert decide("0", "0", "true", C, D, rehash=lambda c: None)[:2] == (False, False), "a failed re-download"
    assert calls and all(c == C for c in calls), "the re-hash reads the pinned commit"
    n = len(calls)
    decide("1", "0", "true", C, D, rehash=rh)
    decide("2", "0", "true", C, D, rehash=rh)
    assert len(calls) == n, "no download unless both checks are clean"
    print("selftest ok")
    return 0


def main(argv) -> int:
    if "--selftest" in argv:
        return selftest()
    env = os.environ
    args = [env.get(k, "") for k in ("CODE_S", "CODE_Q", "AGREE", "COMMIT", "DATA_SHA")]
    print("sources check exit '{}', quotes check exit '{}', agree '{}', commit '{}', data sha256 '{}'".format(*args))
    write, ok, why = decide(*args)
    print(why if write else f"::warning title=Sheet attestation skipped::{why}")
    out = env.get("GITHUB_OUTPUT")
    lines = f"write={'true' if write else 'false'}\n" + (f"ok={'true' if ok else 'false'}\n" if write else "")
    if out:
        with open(out, "a") as f:
            f.write(lines)
    else:
        print(lines, end="")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except Exception as e:
        print(f"sheet-attest-decide.py broke: {type(e).__name__} {e}")
        sys.exit(2)
