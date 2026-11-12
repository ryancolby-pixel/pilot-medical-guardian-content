#!/usr/bin/env python3
"""Daily check of the PMG 3.0 secure link server: the page your AME opens, the request sheet, and the hourly cleanup.

WHY (2026-11-11). Two promises in the 3.0 privacy wording (docs repo SECURE_SEND_SPEC.md 7.3) are only as good as
someone looking:
  1. "Its code is published, and I check every day that the live page matches it." We serve the page that decrypts
     the pilot's file in the AME's browser. If that page ever changed without a matching publish, nothing would say so.
     This fetches the live page and compares its SHA-256 with the published copy. It DETECTS a changed page; it cannot
     prevent one (spec, "The honest limits").
  2. "An expired copy is deleted within the hour." The hourly cleanup used to swallow every error and report success,
     so a failing cleanup would have gone unnoticed while expired files waited on the 15-day storage rule. The server
     now stamps a heartbeat each run and answers GET /v1/health with three times (no pilot data):
       cleanupOkAt   when a run last finished
       cleanupLateAt when a run last deleted a link more than 2 hours after it was due (earlier runs were missed)
       cleanupFailAt when a run last failed
  3. The free AME request sheet (2026-11-12, Ryan: "Yes, publish it"): GET /sheet and GET /sheet/sheet-data.json are
     published next to the page (sheet/index.html, sheet/sheet-data.json) and judged the same way: each live file's
     SHA-256 against its published copy. A live file whose published copy is missing (HTTP 404) is a finding too
     ("not published"), not a broken instrument.

usage:
  check-securelink.py --published <page> [--published-sheet <sheet page> --published-sheet-data <sheet data>]
      each a path or https URL of the published copy; base URL from $SECURELINK_BASE_URL. Without the two sheet
      options the sheet is not checked.
  check-securelink.py --selftest

Exit 0: all fine. Exit 1: a finding; each one is written to its own report file (securelink-viewer-report.md,
securelink-sheet-report.md, securelink-cleanup-report.md) for scripts/file-finding.sh. Exit 2: the INSTRUMENT could
not run (no URL configured, server unreachable, published copy unreadable). That is a warning, never an issue: an
alarm about our own plumbing teaches the reader to ignore the real one.

The base URL is a secret on purpose: until 3.0 ships it is the AWS TEST stack, and this repo is public.
"""
import hashlib
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

STALE_HOURS = 3        # hourly job: one missed run is noise, three is a broken cleanup
LATE_WINDOW_HOURS = 26  # a daily check plus slack: report any late run since the last check
TIMEOUT = 20
UA = "pmg-ops-check/1.0 (+https://pilotmedicalguardian.com)"

VIEWER_REPORT = "securelink-viewer-report.md"
SHEET_REPORT = "securelink-sheet-report.md"
SHEET_UNCHECKED = "securelink-sheet-unchecked"
CLEANUP_REPORT = "securelink-cleanup-report.md"
SHEET_PATHS = ("/sheet", "/sheet/sheet-data.json")


class InstrumentError(Exception):
    """The check itself could not run. Never a finding."""


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Cache-Control": "no-cache"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        # Never print the URL: the base is a secret until 3.0 ships (Actions masks it, but say only the path).
        why = str(getattr(e, "reason", "") or "")[:80]
        raise InstrumentError(f"could not reach {urllib.parse.urlsplit(url).path or '/'}: {type(e).__name__} {why}".rstrip()) from None


def read_published(src, missing_ok=False):
    """The published bytes. With missing_ok, None when the copy does not exist (never published) instead of an error."""
    if src.startswith("https://"):
        status, body = fetch(src)
        if status == 404 and missing_ok:
            return None
        if status != 200:
            raise InstrumentError(f"the published copy answered HTTP {status}")
        return body
    try:
        with open(src, "rb") as f:
            return f.read()
    except FileNotFoundError:
        if missing_ok:
            return None
        raise InstrumentError("could not read the published copy: FileNotFoundError") from None
    except OSError as e:
        raise InstrumentError(f"could not read the published copy: {type(e).__name__}") from None


def sha(b):
    return hashlib.sha256(b).hexdigest()


# ---------------------------------------------------------------------------------------------- the three judgments
def judge_viewer(live_status, live_body, published_body):
    """None if the live page is the published page, else the finding's first line."""
    if live_status != 200:
        return f"The secure link page did not load (HTTP {live_status}). An AME opening a link right now gets an error."
    if sha(live_body) != sha(published_body):
        return "The page your AME opens does not match the published code."
    return None


def judge_sheet(files):
    """A list of finding lines (empty = fine). files: (path, live status, live body, published body or None)."""
    out = []
    for path, live_status, live_body, published_body in files:
        if live_status != 200:
            out.append(f"The request sheet's {path} did not load (HTTP {live_status}).")
        elif published_body is None:
            out.append(f"The request sheet's {path} is live but not published.")
        elif sha(live_body) != sha(published_body):
            out.append(f"The request sheet's {path} does not match the published copy.")
    return out


def judge_cleanup(health, now_ms):
    """A list of finding lines (empty = fine)."""
    out = []
    ok, late, fail = health.get("cleanupOkAt"), health.get("cleanupLateAt"), health.get("cleanupFailAt")
    hours = lambda ms: (now_ms - ms) / 3_600_000
    if ok is None:
        out.append("The hourly cleanup has never finished a run on this server.")
    elif hours(ok) > STALE_HOURS:
        out.append(f"The hourly cleanup has not finished a run in {hours(ok):.0f} hours.")
    if fail is not None and (ok is None or fail > ok):
        out.append("The newest cleanup run failed.")
    if late is not None and hours(late) <= LATE_WINDOW_HOURS:
        out.append("In the last day a cleanup run deleted an expired link more than 2 hours late, so earlier runs were missed.")
    return out


def stamp(ms):
    return "never" if ms is None else time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime(ms / 1000))


# ---------------------------------------------------------------------------------------------- run
def run(base, published_src, sheet_srcs=None):
    base = base.rstrip("/")
    now_ms = int(time.time() * 1000)
    published = read_published(published_src)
    live_status, live_body = fetch(base + "/r")
    h_status, h_body = fetch(base + "/v1/health")
    if h_status != 200:
        raise InstrumentError(f"/v1/health answered HTTP {h_status} (server not updated yet, or down)")
    try:
        health = json.loads(h_body)
    except json.JSONDecodeError:
        raise InstrumentError("/v1/health did not answer JSON") from None

    # Checked apart: a failure fetching the sheet must never hide the page or cleanup verdicts.
    sheet_files, sheet_error = None, None
    if sheet_srcs:
        try:
            sheet_published = [read_published(src, missing_ok=True) for src in sheet_srcs]
            sheet_files = [(path, *fetch(base + path), pub) for path, pub in zip(SHEET_PATHS, sheet_published)]
        except InstrumentError as e:
            sheet_error = str(e)

    found = False
    for p in (VIEWER_REPORT, SHEET_REPORT, SHEET_UNCHECKED, CLEANUP_REPORT):
        if os.path.exists(p):
            os.remove(p)

    v = judge_viewer(live_status, live_body, published)
    print(f"viewer: live {sha(live_body)[:16]} ({len(live_body)} bytes), published {sha(published)[:16]} "
          f"({len(published)} bytes): {'MISMATCH' if v else 'match'}")
    if v:
        found = True
        with open(VIEWER_REPORT, "w") as f:
            f.write(f"{v}\n\n"
                    "Until this is explained, assume the page that decrypts pilots' files is not the code we published.\n\n"
                    "## Details\n\n"
                    f"- Live page: HTTP {live_status}, {len(live_body)} bytes, SHA-256 `{sha(live_body)}`\n"
                    f"- Published copy: {len(published)} bytes, SHA-256 `{sha(published)}`\n"
                    "- If the change was ours (a viewer update deployed before it was published), publish the new build. "
                    "If it was not ours, treat it as a security incident: stop new links and find out who changed the page.\n")

    if sheet_error:
        print(f"sheet: could not check: {sheet_error}")
        open(SHEET_UNCHECKED, "w").close()
    elif sheet_files is None:
        print("sheet: not checked (no --published-sheet given)")
    else:
        s = judge_sheet(sheet_files)
        details = []
        for path, st, body, pub in sheet_files:
            pub_txt = "not published" if pub is None else f"published {sha(pub)[:16]} ({len(pub)} bytes)"
            ok = st == 200 and pub is not None and sha(body) == sha(pub)
            print(f"sheet {path}: live HTTP {st} {sha(body)[:16]} ({len(body)} bytes), {pub_txt}: "
                  f"{'match' if ok else ('NOT PUBLISHED' if st == 200 and pub is None else 'MISMATCH')}")
            pub_line = "not published (no copy at the published address)" if pub is None else \
                f"{len(pub)} bytes, SHA-256 `{sha(pub)}`"
            details.append(f"- `{path}`: live HTTP {st}, {len(body)} bytes, SHA-256 `{sha(body)}`; published: {pub_line}\n")
        if s:
            found = True
            with open(SHEET_REPORT, "w") as f:
                f.write("\n".join(s) + "\n\n"
                        "Until this is explained, assume the request sheet AMEs and pilots see is not the code and FAA list "
                        "we published.\n\n"
                        "## Details\n\n" + "".join(details) +
                        "- If the change was ours (a sheet or data update deployed before it was published), publish the new "
                        "build with SecureLink/server/tools/export-viewer.mjs. If it was not ours, treat it as a security "
                        "incident and find out who changed the sheet.\n")

    c = judge_cleanup(health, now_ms)
    print(f"cleanup: last ok {stamp(health.get('cleanupOkAt'))}, last late {stamp(health.get('cleanupLateAt'))}, "
          f"last failed {stamp(health.get('cleanupFailAt'))}: {'PROBLEM' if c else 'fine'}")
    if c:
        found = True
        with open(CLEANUP_REPORT, "w") as f:
            f.write("\n".join(c) + "\n\n"
                    "Expired secure link files may be sitting on the server past the time the privacy policy promises "
                    "(deleted within the hour). The 15-day storage rule is the only backstop.\n\n"
                    "## Details\n\n"
                    f"- Last finished run: {stamp(health.get('cleanupOkAt'))}\n"
                    f"- Last late run: {stamp(health.get('cleanupLateAt'))}\n"
                    f"- Last failed run: {stamp(health.get('cleanupFailAt'))}\n"
                    "- Look at the cleanup function's log in AWS (kept 1 day) and its Errors metric. A failure logs only "
                    "\"cleanup failed (<error type>)\".\n")
    return 1 if found else (2 if sheet_error else 0)


# ---------------------------------------------------------------------------------------------- selftest
def selftest():
    """Negative AND positive controls, so a later edit can't quietly disarm either judgment."""
    H = 3_600_000
    now = 1_800_000_000_000
    page = b"<!doctype html><title>x</title>"
    assert judge_viewer(200, page, page) is None
    assert judge_viewer(200, page + b" ", page) is not None, "one changed byte must be a finding"
    assert judge_viewer(500, b"", page) is not None, "a page that does not load must be a finding"
    data = b'{"conditions":[]}'
    good = [("/sheet", 200, page, page), ("/sheet/sheet-data.json", 200, data, data)]
    assert judge_sheet(good) == []
    assert len(judge_sheet([("/sheet", 200, page + b" ", page), good[1]])) == 1, "one changed byte in the sheet page"
    assert len(judge_sheet([good[0], ("/sheet/sheet-data.json", 200, data + b" ", data)])) == 1, "one changed byte in the data"
    assert len(judge_sheet([("/sheet", 404, b"", page), good[1]])) == 1, "a sheet that does not load must be a finding"
    assert len(judge_sheet([good[0], ("/sheet/sheet-data.json", 200, data, None)])) == 1, "live but not published is a finding"
    missing = os.path.join(os.path.dirname(os.path.abspath(__file__)), "no-such-published-copy")
    assert read_published(missing, missing_ok=True) is None, "a sheet copy never published is judged, not an error"
    try:
        read_published(missing)
        raise AssertionError("a missing published copy of the AME page must stay an instrument error")
    except InstrumentError:
        pass
    assert judge_cleanup({"cleanupOkAt": now - H, "cleanupLateAt": None, "cleanupFailAt": None}, now) == []
    assert judge_cleanup({"cleanupOkAt": now - 2 * H, "cleanupLateAt": now - 30 * H, "cleanupFailAt": now - 5 * H}, now) == [], \
        "an old late run and a failure older than the last good run are history, not findings"
    assert len(judge_cleanup({"cleanupOkAt": now - 4 * H, "cleanupLateAt": None, "cleanupFailAt": None}, now)) == 1, "stale"
    assert len(judge_cleanup({"cleanupOkAt": None, "cleanupLateAt": None, "cleanupFailAt": None}, now)) == 1, "never ran"
    assert len(judge_cleanup({"cleanupOkAt": now - H, "cleanupLateAt": None, "cleanupFailAt": now - 1000}, now)) == 1, "newest run failed"
    assert len(judge_cleanup({"cleanupOkAt": now - H, "cleanupLateAt": now - 2 * H, "cleanupFailAt": None}, now)) == 1, "late"
    # The stale line's digits change every day; file-finding.sh strips digits from its fingerprint, so this stays one finding.
    a = judge_cleanup({"cleanupOkAt": now - 4 * H, "cleanupLateAt": None, "cleanupFailAt": None}, now)[0]
    b = judge_cleanup({"cleanupOkAt": now - 40 * H, "cleanupLateAt": None, "cleanupFailAt": None}, now)[0]
    assert "".join(ch for ch in a if not ch.isdigit()) == "".join(ch for ch in b if not ch.isdigit())
    # A sheet fetch that fails must not hide the page verdict: stub the network, tamper /r, break the sheet data.
    import contextlib, io, tempfile
    real_fetch, cwd = globals()["fetch"], os.getcwd()
    health = json.dumps({"cleanupOkAt": int(time.time() * 1000) - 600_000}).encode()
    def stub(tampered):
        def f(url):
            if url.endswith("/sheet/sheet-data.json"):
                raise InstrumentError("could not reach /sheet/sheet-data.json: TimeoutError")
            return 200, {"/r": page + b" " if tampered else page, "/v1/health": health, "/sheet": page}[urllib.parse.urlsplit(url).path]
        return f
    try:
        # Silent: a stubbed "MISMATCH" line in the Actions log must never read as a real finding.
        with tempfile.TemporaryDirectory() as d, contextlib.redirect_stdout(io.StringIO()):
            os.chdir(d)
            for n in ("viewer.html", "index.html", "sheet-data.json"):
                with open(n, "wb") as fh:
                    fh.write(page)
            globals()["fetch"] = stub(True)
            assert run("https://x.test", "viewer.html", ("index.html", "sheet-data.json")) == 1, "the page finding still counts"
            assert os.path.exists(VIEWER_REPORT) and os.path.exists(SHEET_UNCHECKED), "page report written, sheet marked unchecked"
            globals()["fetch"] = stub(False)
            assert run("https://x.test", "viewer.html", ("index.html", "sheet-data.json")) == 2, "no finding plus an unchecked sheet is exit 2"
            assert not os.path.exists(VIEWER_REPORT), "a stale report from the run before is removed"
    finally:
        globals()["fetch"] = real_fetch
        os.chdir(cwd)
    print("selftest ok")
    return 0


def main(argv):
    if "--selftest" in argv:
        return selftest()
    if "--published" not in argv or argv.index("--published") + 1 >= len(argv):
        print(__doc__)
        return 2
    published_src = argv[argv.index("--published") + 1]
    opt = lambda name: argv[argv.index(name) + 1] if name in argv and argv.index(name) + 1 < len(argv) else None
    sheet_srcs = (opt("--published-sheet"), opt("--published-sheet-data"))
    if any(sheet_srcs) and not all(sheet_srcs):
        print("give both --published-sheet and --published-sheet-data, or neither")
        return 2
    base = os.environ.get("SECURELINK_BASE_URL", "").strip()
    if not base:
        print("SECURELINK_BASE_URL is not set: nothing to check.")
        return 2
    try:
        return run(base, published_src, sheet_srcs if all(sheet_srcs) else None)
    except InstrumentError as e:
        print(f"could not run the check: {e}")
        return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
