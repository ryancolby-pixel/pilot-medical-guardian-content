#!/usr/bin/env python3
"""Weekly re-check of the FAA quotes on the free AME request sheet.

WHY (2026-11-12, Ryan: "Yes, build it"). The sheet (secure link server /sheet, data /sheet/sheet-data.json) shows
curated verbatim FAA quotes for the Special Issuance conditions. Its builder, build-sheet-data.py (published in
ryancolby-pixel/pmg-securelink-viewer next to source/sheet-curated.json and sheet/sheet-data.json), re-checks every
quote, sub-item, letter sentence and block heading on its own FAA sourceURL with this repo's matcher
(check-content-fidelity.py: fetch and in_source), but only when someone rebuilds the sheet. An FAA page that changed
after that would leave a stale quote live. This runs the published builder on the published curated file with a new,
empty cache (every FAA document fetched fresh), then compares what it built with the published sheet/sheet-data.json
byte for byte. check-securelink.py checks every day that the live data file is that published copy, so together:
what is live is what was checked.

ONE COMMIT. main is resolved to one commit with git ls-remote and all three files are read from that commit.
raw.githubusercontent.com caches each file on its own for up to 5 minutes (cache-control max-age=300, and a no-cache
request header does not bypass it), so three "main" URLs read just after a publish could come from different commits
and differ for no real reason.

usage:
  check-sheet-quotes.py [--work DIR] [--cache NEW_DIR] [--builder SRC] [--curated SRC] [--published SRC]
      each SRC a path or https URL; by default the three files on pmg-securelink-viewer main. --work is where they
      are downloaded (default: a new temp folder); --cache must be new or empty (default: a new temp folder).
      The builder's --content is this checkout.
  check-sheet-quotes.py --selftest

Exit 0: every quote is on its source and the bytes are equal.
Exit 1: a FINDING, written to sheet-quote-report.md for scripts/file-finding.sh: a quote, letter sentence or heading
        is not on its source (builder exit 2 with its NOT ON ITS SOURCE lines, on a source that is readable prose),
        or the published data is not what the published curated file builds.
Exit 2: the INSTRUMENT could not run: main could not be resolved or a download failed, an FAA source was unreachable
        (builder exit 3), every miss is on a source that fetched but is not readable prose (the vocabulary control
        check-content-fidelity.py applies before it believes a miss), the builder refused (exit 1: malformed curated
        file, cache not new) or exited any other way. Never a finding.

The builder is downloaded code. It runs with python -I from its own folder, and the workflow gives this step no
secrets and no token (see check-sheet-quotes.yml for what that does and does not protect).
"""
import argparse
import hashlib
import importlib.util
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import traceback
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BASE = "https://raw.githubusercontent.com/ryancolby-pixel/pmg-securelink-viewer/main/"
REPO_GIT = "https://github.com/ryancolby-pixel/pmg-securelink-viewer.git"
DEFAULTS = {"builder": BASE + "source/build-sheet-data.py", "curated": BASE + "source/sheet-curated.json",
            "published": BASE + "sheet/sheet-data.json"}
NAMES = {"builder": "build-sheet-data.py", "curated": "sheet-curated.json", "published": "published-sheet-data.json"}
LABELS = {"builder": "the builder", "curated": "the curated file", "published": "the published data"}
REPORT = "sheet-quote-report.md"
MISS = re.compile(r"^(TITLE )?NOT ON ITS SOURCE ")
URL_AT_END = re.compile(r"(https?://\S+)\s*$")
UA = "pmg-ops-check/1.0 (+https://pilotmedicalguardian.com)"


class InstrumentError(Exception):
    """The check itself could not run. Never a finding."""


def readable(src) -> bool:
    """The vocabulary control check-content-fidelity.py applies before it believes any miss: the same expression
    as its `readable = len(src) >= 200 and ...` line in main(), where the measurements behind it are written up.
    fid.fetch runs curl without -f, so a 403 block page, a 5xx page or an image-only PDF comes back as text and every
    quote on it would read as missing. A source that fails this is "not checked": an instrument problem, never a
    finding. Keep the two in step."""
    return bool(src) and len(src) >= 200 and len(set(re.findall(r"[a-z]{3,}", src))) >= 40


def load_fid():
    """This repo's matcher, the module the builder imports (same file, same parser, same cache layout)."""
    spec = importlib.util.spec_from_file_location("fidelity", ROOT / "scripts" / "check-content-fidelity.py")
    fid = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fid)
    return fid


def main_sha() -> str:
    """The commit pmg-securelink-viewer main points at now (see ONE COMMIT above). No token, no API rate limit."""
    try:
        r = subprocess.run(["git", "ls-remote", REPO_GIT, "refs/heads/main"], capture_output=True, text=True, timeout=60)
        m = re.match(r"^([0-9a-f]{40})\s", r.stdout)
    except Exception as e:
        raise InstrumentError(f"could not resolve pmg-securelink-viewer main: {type(e).__name__} {e}") from None
    if not m:
        raise InstrumentError(f"could not resolve pmg-securelink-viewer main: git ls-remote exit {r.returncode} "
                              f"{r.stderr.strip()[:200]}")
    return m.group(1)


def at_commit(srcs: dict, sha: str) -> dict:
    """Every default (main) URL read from that one commit instead; paths and other URLs unchanged."""
    return {k: (s.replace(BASE, BASE[:-len("main/")] + sha + "/") if s.startswith(BASE) else s) for k, s in srcs.items()}


def get(src: str, dest: Path) -> bytes:
    try:
        if src.startswith("https://"):
            req = urllib.request.Request(src, headers={"User-Agent": UA, "Cache-Control": "no-cache"})
            with urllib.request.urlopen(req, timeout=30) as r:
                body = r.read()
        else:
            body = Path(src).read_bytes()
    except Exception as e:  # HTTP 404, network, missing file: all mean we could not check
        raise InstrumentError(f"could not read {src}: {type(e).__name__} {e}") from None
    if not body:
        raise InstrumentError(f"{src} is empty")
    dest.write_bytes(body)
    return body


def changed_conditions(published: bytes, built: bytes) -> str:
    """Which conditions differ, for the report. Best effort: the byte comparison is the verdict."""
    try:
        a = {c["id"]: c for c in json.loads(published)["conditions"]}
        b = {c["id"]: c for c in json.loads(built)["conditions"]}
    except (ValueError, KeyError, TypeError):
        return "The published file is not a sheet data file (not valid JSON, or no conditions list)."
    ids = sorted(i for i in a.keys() | b.keys() if a.get(i) != b.get(i))
    if ids:
        return "Conditions that differ: " + ", ".join(ids)
    return "Every condition is equal; the difference is outside them (the note, the order or the formatting)."


def judge(code: int, output: str, built: bytes | None, published: bytes, unreadable=()) -> tuple[int, str]:
    """(exit code, report for a finding or reason for an instrument problem). Pure, so the selftest can drive it.
    unreadable: the miss URLs whose fetched text failed readable(); their lines are not checked, never a finding."""
    lines = output.splitlines()
    misses, skipped = [], 0
    for i, ln in enumerate(lines):
        if MISS.match(ln):
            m = URL_AT_END.search(ln)
            quote = [lines[i + 1]] if i + 1 < len(lines) and lines[i + 1].startswith("    ") else []
            if m and m.group(1) in unreadable:
                skipped += 1
                continue
            misses += [ln] + quote
    if code == 2 and misses:
        report = ("A line on the free AME request sheet is no longer on the FAA document it cites (weekly re-check, "
                  "every document fetched fresh). The published sheet still shows it.\n\n" + "\n".join(misses) + "\n\n")
        if unreadable:
            # After a "## " heading, so file-finding.sh's fingerprint ignores it.
            report += ("## Not checked (not readable prose)\n\nThese sources fetched but are not readable prose (same "
                       "control as check-content-fidelity.py), so their lines were not judged:\n\n"
                       + "\n".join(sorted(unreadable)) + "\n\n")
        return 1, report + ("## What to do\n\nRead the cited FAA document. If the FAA changed it, correct "
                            "sheet-curated.json in the app repo, rebuild the sheet on a new cache folder and publish it "
                            "again.\n")
    if code == 2 and skipped:
        return 2, ("FAA source fetched but not readable prose, same control as check-content-fidelity.py: "
                   + ", ".join(sorted(unreadable)))
    if code == 3:
        return 2, "an FAA source could not be fetched (builder exit 3)"
    if code == 2:
        return 2, "the builder exited 2 without naming a missing line (for example pdfplumber is not installed)"
    if code != 0:
        return 2, f"the builder refused or crashed (exit {code})"
    if built is None:
        return 2, "the builder exited 0 but wrote nothing"
    if built == published:
        return 0, ""
    first = next((i for i, (x, y) in enumerate(zip(built, published)) if x != y), min(len(built), len(published)))
    return 1, ("The published sheet data (sheet/sheet-data.json in pmg-securelink-viewer) is not what the builder makes "
               "from the published curated file, so the published data is not what this check verified. Every quote was "
               "found on its source.\n\n" + changed_conditions(published, built) + "\n\n## Details\n\n"
               f"published: {len(published)} bytes, sha256 {hashlib.sha256(published).hexdigest()}\n"
               f"rebuilt:   {len(built)} bytes, sha256 {hashlib.sha256(built).hexdigest()}\n"
               f"first difference at byte {first}\n")


def run(work: Path | None, cache: Path | None, srcs: dict, read_source=None) -> tuple[int, str]:
    """read_source(url, cache) -> text: fid.fetch by default; the selftest passes a stand-in so it stays offline."""
    # Absolute, because the builder runs with cwd=work and the readable() control reads the same cache from here.
    work = (work or Path(tempfile.mkdtemp(prefix="sheetcheck-"))).resolve()
    cache = (cache or Path(tempfile.mkdtemp(prefix="sheetcache-")) / "cache").resolve()
    work.mkdir(parents=True, exist_ok=True)
    sha = None
    from_commit = [LABELS[k] for k in NAMES if srcs[k].startswith(BASE)]
    try:
        if any(s.startswith(BASE) for s in srcs.values()):
            sha = main_sha()
            print(f"pmg-securelink-viewer main is {sha}")
            srcs = at_commit(srcs, sha)
        files = {k: work / NAMES[k] for k in NAMES}
        for k in NAMES:
            get(srcs[k], files[k])
    except InstrumentError as e:
        return 2, str(e)
    out = work / "rebuilt-sheet-data.json"
    out.unlink(missing_ok=True)
    t0 = time.monotonic()
    r = subprocess.run([sys.executable, "-I", str(files["builder"]), "--content", str(ROOT), "--cache", str(cache),
                        "--curated", str(files["curated"]), "--out", str(out)],
                       cwd=work, capture_output=True, text=True)
    print(r.stdout + r.stderr, end="")
    print(f"builder exit {r.returncode} after {time.monotonic() - t0:.0f} s (cache {cache})")
    built = out.read_bytes() if r.returncode == 0 and out.exists() else None
    output = r.stdout + "\n" + r.stderr
    unreadable = []
    if r.returncode == 2:
        urls = {m.group(1) for ln in output.splitlines() if MISS.match(ln) for m in [URL_AT_END.search(ln)] if m}
        if urls:
            # The builder's own download and parsed text, from the same cache folder: nothing is fetched again.
            read_source = read_source or load_fid().fetch
            unreadable = sorted(u for u in urls if not readable(read_source(u, cache)))
            for u in unreadable:
                print(f"NOT READABLE PROSE, not checked (same control as check-content-fidelity.py): {u}")
    code, text = judge(r.returncode, output, built, files["published"].read_bytes(), unreadable)
    if code == 1 and sha:
        # After a "## " heading, so the commit never changes file-finding.sh's fingerprint.
        text += f"\n## Checked\n\npmg-securelink-viewer commit {sha}, read from it: {', '.join(from_commit)}.\n"
    return code, text


# ---------------------------------------------------------------------------------------------- selftest
FAKE_BUILDER = r'''import sys
a = dict(zip(sys.argv[1::2], sys.argv[2::2]))
body = open(a["--curated"], "rb").read()
if b"MISS" in body:
    sys.stderr.write("NOT ON ITS SOURCE  si-b  [Heading]  https://www.faa.gov/x\n    “the FAA words”\n")
    sys.exit(2)
open(a["--out"], "wb").write(body)
'''


def selftest() -> int:
    """Negative AND positive controls, so a later edit can't quietly disarm either judgment."""
    A = json.dumps({"note": "n", "conditions": [{"id": "si-a", "x": 1}, {"id": "si-b", "x": 2}]}).encode()
    B = A.replace(b'"x": 2', b'"x": 3')
    miss = "NOT ON ITS SOURCE  si-b  [Heading]  https://www.faa.gov/x\n    “the FAA words”\n1 of 9 missing"
    title = "TITLE NOT ON ITS SOURCE  si-a  https://www.faa.gov/y\n    Some Heading"
    # One miss on a readable source (x) and one on a source that fetched as a block page (u).
    two = ("NOT ON ITS SOURCE  si-b  [Heading]  https://www.faa.gov/x\n    \u201cthe FAA words\u201d\n"
           "NOT ON ITS SOURCE  si-u  [Other]  https://www.faa.gov/u\n    \u201cwords on a block page\u201d\n2 of 9 missing")
    for name, args, want, words in [
        ("clean", (0, "", A, A), 0, []),
        ("one changed byte", (0, "", A + b" ", A), 1, ["Every condition is equal"]),
        ("a changed condition", (0, "", B, A), 1, ["si-b"]),
        ("published is not JSON", (0, "", A, b"<html>"), 1, ["not a sheet data file"]),
        ("a quote missing", (2, miss, None, A), 1, ["si-b", "the FAA words"]),
        ("a heading missing", (2, title, None, A), 1, ["si-a", "Some Heading"]),
        ("exit 2 with no miss line", (2, "pdfplumber is required", None, A), 2, []),
        ("FAA unreachable", (3, "UNREACHABLE https://www.faa.gov/z (used by si-a)", None, A), 2, []),
        ("malformed or cache not new", (1, "MALFORMED: x", None, A), 2, []),
        ("killed", (-9, "", None, A), 2, []),
        ("exit 0 but nothing written", (0, "", None, A), 2, []),
        ("a miss only on an unreadable source", (2, miss, None, A, ["https://www.faa.gov/x"]), 2,
         ["not readable prose", "https://www.faa.gov/x"]),
        ("a readable miss and an unreadable one", (2, two, None, A, ["https://www.faa.gov/u"]), 1,
         ["si-b", "the FAA words", "## Not checked (not readable prose)", "https://www.faa.gov/u"]),
    ]:
        code, text = judge(*args)
        assert code == want, f"{name}: exit {code}, expected {want}"
        assert all(w in text for w in words), f"{name}: report lacks {words}"
    findings = judge(2, two, None, A, ["https://www.faa.gov/u"])[1].split("\n## ")[0]
    assert "si-u" not in findings and "block page" not in findings and "faa.gov/u" not in findings, \
        "an unreadable source's miss is not named as a finding"
    # The readable() control itself, both ways. PROSE: 60 distinct three-letter words, 240 chars.
    PROSE = " ".join("w" + chr(97 + i // 26) + chr(97 + i % 26) for i in range(60))
    assert readable(PROSE), "real text is readable"
    for junk in (None, "", "403 forbidden access denied " * 20, "x" * 5000):
        assert not readable(junk), f"not readable: {str(junk)[:30]!r}"
    # One commit for all three downloads; local paths untouched.
    pinned = at_commit(DEFAULTS, "f" * 40)
    assert all(("/" + "f" * 40 + "/") in v and "/main/" not in v for v in pinned.values()), "every default is pinned"
    assert at_commit({"builder": "/x/b.py"}, "f" * 40) == {"builder": "/x/b.py"}, "a path is not rewritten"
    assert callable(load_fid().fetch), "the matcher loads and has fetch"
    # The whole path with a stand-in builder: download from a path, run it with -I, compare the bytes.
    import contextlib, io
    with tempfile.TemporaryDirectory() as d, contextlib.redirect_stdout(io.StringIO()):
        d = Path(d)
        (d / "b.py").write_text(FAKE_BUILDER)
        (d / "pub.json").write_bytes(A)
        (d / "cur.json").write_bytes(A)
        srcs = {"builder": str(d / "b.py"), "curated": str(d / "cur.json"), "published": str(d / "pub.json")}
        assert run(d / "w1", d / "c1", srcs)[0] == 0, "equal bytes are clean"
        (d / "pub.json").write_bytes(B)
        assert run(d / "w2", d / "c2", srcs)[0] == 1, "a changed published byte is a finding"
        (d / "cur.json").write_bytes(A + b"MISS")
        code, text = run(d / "w3", d / "c3", srcs, read_source=lambda u, c: PROSE)
        assert code == 1 and "si-b" in text, "a missing quote is a finding that names it"
        code, text = run(d / "w5", d / "c5", srcs, read_source=lambda u, c: "403 Forbidden")
        assert code == 2 and "not readable prose" in text, "a miss on a block page is instrument"
        assert run(d / "w4", d / "c4", dict(srcs, builder=str(d / "nope.py")))[0] == 2, "a failed download is instrument"
    print("selftest ok")
    return 0


def main(argv: list[str]) -> int:
    if "--selftest" in argv:
        return selftest()
    ap = argparse.ArgumentParser()
    ap.add_argument("--work", type=Path)
    ap.add_argument("--cache", type=Path)
    for k in DEFAULTS:
        ap.add_argument(f"--{k}", default=DEFAULTS[k])
    a = ap.parse_args(argv)
    Path(REPORT).unlink(missing_ok=True)
    t0 = time.monotonic()
    code, text = run(a.work, a.cache, {k: getattr(a, k) for k in DEFAULTS})
    if code == 1:
        Path(REPORT).write_text(text, encoding="utf-8")
        print(f"\nFINDING ({time.monotonic() - t0:.0f} s), written to {REPORT}:\n\n{text}")
    elif code == 2:
        print(f"\nCOULD NOT CHECK ({time.monotonic() - t0:.0f} s): {text}. Not a finding.")
    else:
        print(f"\nCLEAN ({time.monotonic() - t0:.0f} s): every sheet quote is on its FAA source and the published data "
              "is byte for byte what the builder makes.")
    return code


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except Exception:
        # A crash here is our instrument, never a finding: exit 1 would read as one.
        traceback.print_exc()
        sys.exit(2)
