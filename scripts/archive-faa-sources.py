#!/usr/bin/env python3
"""Daily dated archive of every FAA document the app and the AME request sheet quote.

WHY (2026-11-14). The checks tell us WHEN an FAA page changed. They keep only hashes, so after a change nobody can
show what the page said on the day we quoted it. This keeps a dated copy of the raw bytes in S3, one object per
distinct version, so "what did the FAA say on date X" has an answer from the FAA's own file.

SOURCES (same discovery as the checks, so the lists cannot drift apart):
  1. The sheet: every distinct source URL of the published sheet/sheet-data.json, read from ONE pmg-securelink-viewer
     commit (main resolved with git ls-remote, or --commit), via check-sheet-sources.py's source_urls().
  2. The content: every cited URL check-content-fidelity.py reads (cited_source_urls(): envelope.sourceURL and each
     entry's own links[] across every v1 file).
  Only https://www.faa.gov, https://www.ecfr.gov and https://medxpress.faa.gov URLs are kept. A #fragment is dropped.

DOWNLOAD. check-content-fidelity.py's own downloader (_blob: curl, its browser User-Agent, its eCFR renderer
rewrite) into a new temp folder, one folder per source, paced. A response is SKIPPED, never archived, when:
  - it could not be fetched;
  - the URL names a PDF and the bytes do not start with %PDF;
  - it is HTML and fails the readable() vocabulary control check-sheet-quotes.py and check-content-fidelity.py
    apply (curl runs without -f, so an Akamai 403 page or a 5xx page arrives as a body), or its <title> says it is a
    block or error page. An HTML block page must never be archived as the FAA's document.
  A skipped source is a warning, not a failure: the next day's run tries again.

KEY. faa/<host>/<path, "/" kept, query dropped, unsafe characters replaced with "_">/<YYYY-MM-DD>_<sha256[:16]>.<ext>
with ext pdf (bytes start %PDF), json (bytes parse as JSON) or html. The date is the UTC fetch date.

DEDUP. Before an upload, the URL's prefix is listed (s3api list-objects-v2) and the object is uploaded only when no
existing key there carries the same sha prefix. Unchanged documents cost one list call and nothing else.

TWO PHASES, so no AWS credential exists while fetch code runs (the workflow configures credentials between them):
  --fetch DIR    discover + download + plan into DIR (plan.json plus the files). No AWS call.
  --upload DIR   read DIR/plan.json, list + upload with the aws cli (--bucket or FAA_ARCHIVE_BUCKET). Writes the
                 summary (archived new N, unchanged M, skipped K with reasons) to stdout and $GITHUB_STEP_SUMMARY.
  --dry-run      --fetch into a temp folder and print the plan. No AWS call, nothing uploaded.
  --selftest     offline: key building, dedup decision, block page rejected, PDF header check.

Exit 0: done (skipped sources are warnings). Exit 1: an upload or listing failed. Exit 2: discovery failed (the sheet
data or the v1 files could not be read), so nothing was planned.
"""
import argparse
import hashlib
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import traceback
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HOSTS = ("https://www.faa.gov/", "https://www.ecfr.gov/", "https://medxpress.faa.gov/")
PLAN = "plan.json"
PACE_S, RETRY_WAIT_S, DEADLINE_S = 1.0, 10.0, 30 * 60
# A <title> that says the response is not the document. Lowercased substring match.
# Kept narrow: a false match only skips a day (a warning), but a generic word like "error" would skip real pages.
BLOCK_TITLES = ("access denied", "page not found", "404", "403 forbidden", "service unavailable",
                "request rejected", "just a moment", "attention required")
TITLE = re.compile(r"<title[^>]*>(.*?)</title\s*>", re.S | re.I)


def _load(name, file):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / file)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------------------------------------- keys and checks
def path_part(url: str) -> str:
    """faa/<host>/<path>: "/" kept, query and fragment dropped, anything outside [A-Za-z0-9._-] replaced with "_"."""
    u = urllib.parse.urlsplit(url)
    segs = []
    for seg in urllib.parse.unquote(u.path).split("/"):
        if not seg:
            continue
        seg = re.sub(r"[^A-Za-z0-9._-]", "_", seg)
        if set(seg) <= {"."}:  # "." and ".." must never become path steps in a key
            seg = seg.replace(".", "_")
        segs.append(seg)
    host = re.sub(r"[^A-Za-z0-9.-]", "_", u.netloc.lower())
    return "/".join(["faa", host] + (segs or ["_root"]))


def ext_of(raw: bytes) -> str:
    if raw[:4] == b"%PDF":
        return "pdf"
    s = raw.lstrip()[:1]
    if s in (b"{", b"["):
        try:
            json.loads(raw.decode("utf-8"))
            return "json"
        except (ValueError, UnicodeDecodeError):
            pass
    return "html"


def key_for(url: str, raw: bytes, day: str) -> str:
    return f"{path_part(url)}/{day}_{hashlib.sha256(raw).hexdigest()[:16]}.{ext_of(raw)}"


def is_new(key: str, existing: list[str]) -> bool:
    """Upload only when no existing key under the URL's prefix carries the same sha prefix."""
    sha = key.rsplit("/", 1)[1].split("_", 1)[1].split(".", 1)[0]
    return not any(k.rsplit("/", 1)[-1].split(".", 1)[0].endswith("_" + sha) for k in existing)


def why_unarchivable(url: str, raw: bytes, readable, html_text) -> str:
    """'' when the bytes may be archived as this URL's document, else the reason it is skipped."""
    if not raw:
        return "empty response"
    is_pdf = raw[:4] == b"%PDF"
    if urllib.parse.urlsplit(url).path.lower().endswith(".pdf") and not is_pdf:
        return "the URL names a PDF but the response has no %PDF header (block or error page)"
    if is_pdf:
        return ""
    if ext_of(raw) == "json":
        return ""
    page = raw.decode("utf-8", errors="ignore")
    m = TITLE.search(page)
    title = re.sub(r"\s+", " ", m.group(1)).strip().lower() if m else ""
    if any(b in title for b in BLOCK_TITLES):
        return f"block or error page (title {title[:60]!r})"
    if not readable(html_text(page, url).lower()):
        return "not readable prose (block page, error page or empty shell)"
    return ""


# ---------------------------------------------------------------------------------------------- discovery
def discover(commit: str | None) -> tuple[list[str], dict]:
    """(urls in first-seen order, info). Sheet sources first, then content sources."""
    S = _load("sheet_sources", "check-sheet-sources.py")
    Q = S.Q
    fid = Q.load_fid()
    commit = commit or Q.main_sha()
    srcs = Q.at_commit({"published": Q.DEFAULTS["published"]}, commit)
    with tempfile.TemporaryDirectory(prefix="faaarch-sheet-") as d:
        body = Q.get(srcs["published"], Path(d) / Q.NAMES["published"])
    try:
        sheet = list(S.source_urls(json.loads(body)))
    except (ValueError, KeyError, TypeError):
        raise Q.InstrumentError("the published file is not a sheet data file") from None
    content = fid.cited_source_urls()
    out, seen = [], set()
    for u in sheet + content:
        u = (u or "").strip().split("#", 1)[0]
        if u.startswith(HOSTS) and u not in seen:
            seen.add(u)
            out.append(u)
    info = {"commit": commit, "sheetSources": len(sheet), "contentSources": len(content), "kept": len(out)}
    return out, info


# ---------------------------------------------------------------------------------------------- phase 1: fetch
def fetch_all(urls: list[str], out: Path, blob=None, readable=None, html_text=None, now=None) -> dict:
    if blob is None or readable is None or html_text is None:
        S = _load("sheet_sources", "check-sheet-sources.py")
        blob = blob or S.Q.load_fid()._blob
        readable = readable or S.Q.readable
        html_text = html_text or S.html_text
    files, cache = out / "files", Path(tempfile.mkdtemp(prefix="faaarch-cache-"))
    files.mkdir(parents=True, exist_ok=True)
    items, skipped, t0 = [], [], time.monotonic()
    try:
        for i, u in enumerate(urls):
            if time.monotonic() - t0 > DEADLINE_S:
                skipped.append({"url": u, "reason": f"not fetched, the {DEADLINE_S // 60} minute limit was reached"})
                continue
            reason, raw = "", b""
            for attempt in (0, 1):
                if i or attempt:
                    time.sleep(RETRY_WAIT_S if attempt else PACE_S)
                where = cache / f"{i:03d}"
                shutil.rmtree(where, ignore_errors=True)  # a retry fetches again, never reuses a bad download
                p = blob(u, where)
                raw = p.read_bytes() if p else b""
                reason = "unreachable" if p is None else why_unarchivable(u, raw, readable, html_text)
                if not reason:
                    break
            if reason:
                skipped.append({"url": u, "reason": reason})
                print(f"  SKIP   {u}  ({reason})")
                continue
            at = now or datetime.now(timezone.utc)
            key = key_for(u, raw, at.strftime("%Y-%m-%d"))
            name = f"{i:03d}.{ext_of(raw)}"
            (files / name).write_bytes(raw)
            items.append({"url": u, "key": key, "file": name, "bytes": len(raw),
                          "fetchedAt": at.strftime("%Y-%m-%dT%H:%M:%SZ")})
            print(f"  OK     {len(raw):8d}  {key}")
    finally:
        shutil.rmtree(cache, ignore_errors=True)
    return {"items": items, "skipped": skipped}


# ---------------------------------------------------------------------------------------------- phase 2: upload
CONTENT_TYPES = {"pdf": "application/pdf", "html": "text/html; charset=utf-8", "json": "application/json"}


def aws(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(["aws"] + args, capture_output=True, text=True, timeout=120)


def list_keys(bucket: str, prefix: str) -> list[str]:
    r = aws(["s3api", "list-objects-v2", "--bucket", bucket, "--prefix", prefix,
             "--query", "Contents[].Key", "--output", "json"])
    if r.returncode != 0:
        raise RuntimeError(f"list {prefix}: {r.stderr.strip()[:300]}")
    return json.loads(r.stdout or "null") or []


def put(bucket: str, key: str, body: Path, url: str, fetched_at: str) -> None:
    ext = key.rsplit(".", 1)[1]
    r = aws(["s3api", "put-object", "--bucket", bucket, "--key", key, "--body", str(body),
             "--content-type", CONTENT_TYPES[ext],
             "--metadata", json.dumps({"source-url": url, "fetched-at": fetched_at})])
    if r.returncode != 0:
        raise RuntimeError(f"put {key}: {r.stderr.strip()[:300]}")


def upload(plan_dir: Path, bucket: str, lister=list_keys, putter=put) -> tuple[int, dict]:
    plan = json.loads((plan_dir / PLAN).read_text(encoding="utf-8"))
    new, same, failed = [], [], []
    for it in plan["items"]:
        prefix = it["key"].rsplit("/", 1)[0] + "/"
        try:
            if not is_new(it["key"], lister(bucket, prefix)):
                same.append(it["key"])
                continue
            putter(bucket, it["key"], plan_dir / "files" / it["file"], it["url"], it["fetchedAt"])
            new.append(it["key"])
            print(f"  NEW    {it['key']}")
        except Exception as e:
            failed.append({"key": it["key"], "error": f"{type(e).__name__}: {e}"})
            print(f"  FAILED {it['key']}: {e}")
    return (1 if failed else 0), {"new": new, "unchanged": same, "failed": failed, "skipped": plan["skipped"],
                                  "info": plan.get("info", {})}


def summary(res: dict) -> str:
    sk = res["skipped"]
    lines = ["## FAA source archive", "",
             f"archived new {len(res['new'])}, unchanged {len(res['unchanged'])}, skipped {len(sk)}"
             + (f", FAILED {len(res['failed'])}" if res["failed"] else ""), ""]
    info = res.get("info") or {}
    if info:
        lines += [f"Sources: {info.get('kept')} FAA URLs ({info.get('sheetSources')} sheet, "
                  f"{info.get('contentSources')} content, before host filter and dedup); "
                  f"sheet data from pmg-securelink-viewer {info.get('commit')}", ""]
    for title, rows in (("Failed uploads", [f"{f['key']}: {f['error']}" for f in res["failed"]]),
                        ("Skipped (tried again tomorrow)", [f"{s['url']}: {s['reason']}" for s in sk]),
                        ("Archived new", res["new"])):
        if rows:
            lines += [f"### {title}", ""] + [f"- {r}" for r in rows] + [""]
    return "\n".join(lines)


def warn_skipped(skipped: list[dict]) -> None:
    if skipped and os.environ.get("GITHUB_ACTIONS"):
        for s in skipped:
            print(f"::warning title=FAA source not archived today::{s['url']}: {s['reason']}")


# ---------------------------------------------------------------------------------------------- selftest
def selftest() -> int:
    ok = True

    def check(name, cond):
        nonlocal ok
        print(f"  {'pass' if cond else 'FAIL'}  {name}")
        ok = ok and cond

    pdf, page = b"%PDF-1.7\n...", b"<html><head><title>Asthma | Federal Aviation Administration</title></head><body>x</body></html>"
    sha = hashlib.sha256(pdf).hexdigest()[:16]
    check("key: pdf path kept, date and sha16",
          key_for("https://www.faa.gov/ame_guide/media/Asthma.pdf?x=1#p2", pdf, "2026-11-14")
          == f"faa/www.faa.gov/ame_guide/media/Asthma.pdf/2026-11-14_{sha}.pdf")
    check("key: query dropped, unsafe chars replaced, dot segments neutralised",
          path_part("https://www.faa.gov/a%20b/../c d/(x)/?q=1") == "faa/www.faa.gov/a_b/__/c_d/_x_")
    check("key: eCFR section path kept", path_part(
        "https://www.ecfr.gov/current/title-14/chapter-I/subchapter-D/part-67/subpart-B/section-67.107")
        == "faa/www.ecfr.gov/current/title-14/chapter-I/subchapter-D/part-67/subpart-B/section-67.107")
    check("key: bare host", path_part("https://medxpress.faa.gov") == "faa/medxpress.faa.gov/_root")
    check("ext: json", ext_of(b' {"a": 1}') == "json" and ext_of(b"{not json") == "html" and ext_of(page) == "html")
    k = f"faa/www.faa.gov/x.pdf/2026-11-14_{sha}.pdf"
    check("dedup: same sha on another day is unchanged",
          not is_new(k, [f"faa/www.faa.gov/x.pdf/2026-01-02_{sha}.pdf"]))
    check("dedup: different sha is new", is_new(k, [f"faa/www.faa.gov/x.pdf/2026-01-02_{'0' * 16}.pdf"]))
    check("dedup: empty prefix is new", is_new(k, []))
    check("dedup: sha must be the whole suffix, not a substring",
          is_new(k, [f"faa/www.faa.gov/x.pdf/2026-01-02_{sha[1:]}.pdf"]))

    readable = lambda s: bool(s) and len(s) >= 200 and len(set(re.findall(r"[a-z]{3,}", s))) >= 40
    html_text = lambda s, base="": re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", s)).strip()
    words = " ".join(f"word{chr(97 + i // 26)}{chr(97 + i % 26)}" for i in range(60))
    good = f"<html><head><title>Asthma</title></head><body><p>{words}</p></body></html>".encode()
    akamai = b"<HTML><HEAD><TITLE>Access Denied</TITLE></HEAD><BODY>You don't have permission to access this.</BODY></HTML>"
    akamai_long = f"<html><head><title>Access Denied</title></head><body>{words}</body></html>".encode()
    shell = b"<html><head><title>eCFR</title></head><body><div id=app></div><script>x</script></body></html>"
    check("readable FAA page accepted", why_unarchivable("https://www.faa.gov/x", good, readable, html_text) == "")
    check("Akamai block page rejected", why_unarchivable("https://www.faa.gov/x", akamai, readable, html_text) != "")
    check("block page with enough words still rejected by its title",
          why_unarchivable("https://www.faa.gov/x", akamai_long, readable, html_text) != "")
    check("empty shell rejected", why_unarchivable("https://www.ecfr.gov/x", shell, readable, html_text) != "")
    check("PDF URL answered with HTML rejected",
          why_unarchivable("https://www.faa.gov/m/A.pdf", good, readable, html_text) != "")
    check("PDF URL with %PDF header accepted", why_unarchivable("https://www.faa.gov/m/A.pdf", pdf, readable, html_text) == "")
    check("empty body rejected", why_unarchivable("https://www.faa.gov/x", b"", readable, html_text) != "")

    # Fetch + upload end to end, offline: a fake downloader and a fake bucket.
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        bodies = {"https://www.faa.gov/a": good, "https://www.faa.gov/b.pdf": akamai, "https://www.faa.gov/c.pdf": pdf}

        def blob(u, where):
            if u not in bodies:
                return None
            where.mkdir(parents=True, exist_ok=True)
            (where / "f").write_bytes(bodies[u])
            return where / "f"

        global PACE_S, RETRY_WAIT_S
        saved = PACE_S, RETRY_WAIT_S
        PACE_S = RETRY_WAIT_S = 0
        import contextlib, io
        with contextlib.redirect_stdout(io.StringIO()):
            plan = fetch_all(list(bodies) + ["https://www.faa.gov/gone"], d, blob, readable, html_text,
                             now=datetime(2026, 11, 14, 16, 20, tzinfo=timezone.utc))
        PACE_S, RETRY_WAIT_S = saved
        (d / PLAN).write_text(json.dumps(plan))
        check("fetch: 2 planned, 2 skipped", len(plan["items"]) == 2 and len(plan["skipped"]) == 2)
        bucket = {f"faa/www.faa.gov/c.pdf/2026-10-01_{sha}.pdf"}
        puts = []

        def lister(b, prefix):
            return [k for k in bucket if k.startswith(prefix)]

        def putter(b, key, body, url, at):
            puts.append((key, body.read_bytes(), url, at))

        with contextlib.redirect_stdout(io.StringIO()):
            code, res = upload(d, "bkt", lister, putter)
        check("upload: one new, one unchanged, exit 0", code == 0 and len(res["new"]) == 1 and len(res["unchanged"]) == 1)
        check("upload: bytes and metadata are the fetched ones",
              puts and puts[0][1] == good and puts[0][2] == "https://www.faa.gov/a" and puts[0][3] == "2026-11-14T16:20:00Z")

        def bad_put(*a):
            raise RuntimeError("AccessDenied")

        with contextlib.redirect_stdout(io.StringIO()):
            code, res = upload(d, "bkt", lister, bad_put)
        check("upload: a failed put is exit 1", code == 1 and len(res["failed"]) == 1)
        check("summary counts", "archived new 0, unchanged 1, skipped 2, FAILED 1" in summary(res))
    print("archive selftest " + ("passed" if ok else "FAILED"))
    return 0 if ok else 1


# ---------------------------------------------------------------------------------------------- main
def do_fetch(out: Path, commit: str | None) -> int:
    out.mkdir(parents=True, exist_ok=True)
    try:
        urls, info = discover(commit)
    except Exception as e:
        print(f"COULD NOT DISCOVER SOURCES: {type(e).__name__}: {e}")
        return 2
    print(f"{info['kept']} FAA URLs ({info['sheetSources']} sheet, {info['contentSources']} content), "
          f"pmg-securelink-viewer {info['commit']}")
    plan = fetch_all(urls, out)
    plan["info"] = info
    (out / PLAN).write_text(json.dumps(plan, indent=1) + "\n", encoding="utf-8")
    print(f"planned {len(plan['items'])}, skipped {len(plan['skipped'])}")
    warn_skipped(plan["skipped"])
    return 0


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--fetch", type=Path, metavar="DIR")
    g.add_argument("--upload", type=Path, metavar="DIR")
    g.add_argument("--dry-run", action="store_true")
    g.add_argument("--selftest", action="store_true")
    ap.add_argument("--commit")
    ap.add_argument("--bucket", default=os.environ.get("FAA_ARCHIVE_BUCKET", ""))
    a = ap.parse_args(argv)
    if a.selftest:
        return selftest()
    if a.commit and not re.fullmatch(r"[0-9a-f]{40}", a.commit):
        print("--commit must be a full 40 character commit sha")
        return 2
    if a.dry_run:
        d = Path(tempfile.mkdtemp(prefix="faaarch-dry-"))
        code = do_fetch(d, a.commit)
        print(f"DRY RUN: nothing uploaded. Plan: {d / PLAN}")
        return code
    if a.fetch:
        return do_fetch(a.fetch, a.commit)
    if not a.bucket:
        print("no bucket: pass --bucket or set FAA_ARCHIVE_BUCKET")
        return 1
    code, res = upload(a.upload, a.bucket)
    text = summary(res)
    print("\n" + text)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as f:
            f.write(text + "\n")
    return code


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except Exception:
        traceback.print_exc()
        sys.exit(1)
