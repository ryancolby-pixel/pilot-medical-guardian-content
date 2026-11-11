#!/usr/bin/env python3
"""Daily check of the PMG 3.0 secure link server: the page your AME opens, and the hourly cleanup.

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

usage:
  check-securelink.py --published <path or https URL of the published page>   # base URL from $SECURELINK_BASE_URL
  check-securelink.py --selftest

Exit 0: both fine. Exit 1: a finding; each one is written to its own report file (securelink-viewer-report.md,
securelink-cleanup-report.md) for scripts/file-finding.sh. Exit 2: the INSTRUMENT could not run (no URL configured,
server unreachable, published copy unreadable). That is a warning, never an issue: an alarm about our own plumbing
teaches the reader to ignore the real one.

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
CLEANUP_REPORT = "securelink-cleanup-report.md"


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


def read_published(src):
    if src.startswith("https://"):
        status, body = fetch(src)
        if status != 200:
            raise InstrumentError(f"the published copy answered HTTP {status}")
        return body
    try:
        with open(src, "rb") as f:
            return f.read()
    except OSError as e:
        raise InstrumentError(f"could not read the published copy: {type(e).__name__}") from None


def sha(b):
    return hashlib.sha256(b).hexdigest()


# ---------------------------------------------------------------------------------------------- the two judgments
def judge_viewer(live_status, live_body, published_body):
    """None if the live page is the published page, else the finding's first line."""
    if live_status != 200:
        return f"The secure link page did not load (HTTP {live_status}). An AME opening a link right now gets an error."
    if sha(live_body) != sha(published_body):
        return "The page your AME opens does not match the published code."
    return None


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
def run(base, published_src):
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

    found = False
    for p in (VIEWER_REPORT, CLEANUP_REPORT):
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
    return 1 if found else 0


# ---------------------------------------------------------------------------------------------- selftest
def selftest():
    """Negative AND positive controls, so a later edit can't quietly disarm either judgment."""
    H = 3_600_000
    now = 1_800_000_000_000
    page = b"<!doctype html><title>x</title>"
    assert judge_viewer(200, page, page) is None
    assert judge_viewer(200, page + b" ", page) is not None, "one changed byte must be a finding"
    assert judge_viewer(500, b"", page) is not None, "a page that does not load must be a finding"
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
    print("selftest ok")
    return 0


def main(argv):
    if "--selftest" in argv:
        return selftest()
    if "--published" not in argv or argv.index("--published") + 1 >= len(argv):
        print(__doc__)
        return 2
    published_src = argv[argv.index("--published") + 1]
    base = os.environ.get("SECURELINK_BASE_URL", "").strip()
    if not base:
        print("SECURELINK_BASE_URL is not set: nothing to check.")
        return 2
    try:
        return run(base, published_src)
    except InstrumentError as e:
        print(f"could not run the check: {e}")
        return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
