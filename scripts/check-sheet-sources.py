#!/usr/bin/env python3
"""Twice daily FAA change watcher for every document the free AME request sheet quotes.

WHY (2026-11-14). The secure link server now serves the sheet's FAA quotes only while a fresh attestation says they
were checked (SECURE_SEND_SPEC.md in the docs repo). check-sheet-quotes.py proves every quote is still ON its source.
It cannot see an FAA edit that leaves our quoted sentences in place but changes what surrounds them (a new required
document, a changed interval in the next line). This watches the whole readable text of every cited document and
reports ANY change, so a person reads the FAA page before the sheet keeps standing on it.

WHAT IS COMPARED. For each distinct source URL of the published sheet/sheet-data.json (each condition page, the
letter sourceURL, each block sourceURL, first-seen order) a text fingerprint:
  HTML: the GOTCHAS_VERIFY.md section 30 normalization (the instrument that worked on 136 FAA sources): drop
        <script|style|head|nav|header|footer> with their contents, write each remaining link's target in as
        "[link URL]" (absolute, no query string or fragment), drop tags, HTML-unescape, collapse whitespace, sha256.
        A raw-page hash is worthless here: Drupal rotates asset cache-busters and reorders meta tags on every FAA
        deploy. The link targets count because the FAA posts a revised form at a NEW URL and repoints the page's link
        while the old PDF stays online: the visible text does not move, the cited form is superseded.
  PDF:  pdfplumber page text plus table cells (as check-content-fidelity.py reads them), whitespace collapsed, sha256.
        That is an EXACT hash of pdfplumber's output, so the extractor is part of the instrument: the baseline records
        the pdfplumber and pdfminer.six versions (and the fingerprint method) it was taken with, the workflow pins
        them, and a run on other versions is exit 2, never a finding. Upgrading either means a deliberate re-baseline.
Downloads use check-content-fidelity.py's own downloader (_blob: curl, its browser User-Agent, its eCFR renderer
rewrite) into a new, empty cache, one folder per source (so two long URLs can never share a cached file), so every
document is fetched fresh. A #fragment is dropped before the fetch (the eCFR rewrite only matches a bare section URL).
Fetches are paced (PACE_S apart); a source that comes back unreachable or not readable is tried once more after
RETRY_WAIT_S; past DEADLINE_S the rest are not fetched (exit 2), so a slow FAA never hangs the job.

ONE COMMIT, same as check-sheet-quotes.py: the published data file is read from one pmg-securelink-viewer commit
(main resolved with git ls-remote, or --commit). The commit and the data file's sha256 are written to
<work>/checked.json so the attestation step writes the SAME values the checks used.

BASELINE: .sheet-source-fingerprints.json at the repo root,
  {"dataSha": "<sha256 of the published sheet-data.json>", "taken": "YYYY-MM-DD", "sources": {"<url>": "<sha>"},
   "instrument": {"method": "<fingerprint method>", "pdfplumber": "<version>", "pdfminer.six": "<version>"}}
Only hashes are stored. Re-take it with --rebaseline after a person has read every changed document (and after
every sheet publish, since the data sha is part of the baseline).

usage:
  check-sheet-sources.py [--work DIR] [--cache NEW_DIR] [--published SRC] [--commit SHA]
  check-sheet-sources.py --rebaseline [same options]   # refuses if any source is unreadable or unreachable
  check-sheet-sources.py --selftest                     # offline

Exit 0: every source reads the same as the baseline and the baseline was taken on the published data.
Exit 1: a FINDING, written to sheet-source-report.md for scripts/file-finding.sh: a source's text changed, a source
        has no baseline, or the published data is not the data the baseline was taken on.
Exit 2: the INSTRUMENT could not run: the commit or the data file could not be read, a source was unreachable or
        fetched as something that is not readable prose (same control as check-content-fidelity.py) after its retry,
        the time limit was reached, or the baseline was taken with another fingerprint method or other pdfplumber /
        pdfminer.six versions than the ones installed. Never a finding.
        A finding on another source still wins (exit 1).
"""
import argparse
import hashlib
import html
import importlib.util
import json
import re
import shutil
import sys
import tempfile
import time
import traceback
import urllib.parse
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BASELINE = ROOT / ".sheet-source-fingerprints.json"
REPORT = "sheet-source-report.md"
CHECKED = "checked.json"


def _load(name, file):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / file)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# The quotes check's commit pinning, downloader and readable() control, so the two checks cannot drift apart.
Q = _load("sheet_quotes", "check-sheet-quotes.py")
InstrumentError = Q.InstrumentError


# ---------------------------------------------------------------------------------------------- the fingerprint
DROP = re.compile(r"<(script|style|head|nav|header|footer)\b[^>]*>.*?</\1\s*>", re.S | re.I)
A_HREF = re.compile(r"""<a\b[^>]*?\shref\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s>]+))[^>]*>""", re.I)
# Change this when the normalization changes: a baseline taken another way is refused (exit 2), not a mass finding.
METHOD = "html text + link targets, pdf text + tables (2026-11-14)"
PACE_S, RETRY_WAIT_S, DEADLINE_S = 1.0, 20.0, 20 * 60


def _link(m, base: str) -> str:
    href = html.unescape(next(g for g in m.groups() if g is not None)).strip()
    if not href or href.startswith(("#", "javascript:")):
        return " "
    u = urllib.parse.urlsplit(urllib.parse.urljoin(base, href))
    return f" [link {urllib.parse.urlunsplit((u.scheme, u.netloc, u.path, '', ''))}] "


def html_text(s: str, base: str = "") -> str:
    """GOTCHAS_VERIFY.md section 30: what a reader sees, without Drupal's per-deploy noise, plus where its links go."""
    s = re.sub(r"<!--.*?-->", " ", s, flags=re.S)
    s = DROP.sub(" ", s)
    s = A_HREF.sub(lambda m: _link(m, base), s)
    s = re.sub(r"<[^>]+>", " ", s)
    s = html.unescape(s)
    return re.sub(r"\s+", " ", s).strip()


def pdf_text(path: Path) -> str:
    """Page text plus table cells, as check-content-fidelity.py's _fetch reads a PDF."""
    try:
        import pdfplumber
    except ImportError:
        raise InstrumentError("pdfplumber is required to read PDF sources: pip install pdfplumber") from None
    parts = []
    try:
        with pdfplumber.open(path) as pdf:
            for page in pdf.pages:
                parts.append(page.extract_text() or "")
                for table in (page.extract_tables() or []):
                    for row in table:
                        parts.extend(c for c in row if c)
    except Exception as e:  # a truncated or non-PDF download: not readable, so not checked
        return f"(pdf could not be parsed: {type(e).__name__})"
    return re.sub(r"\s+", " ", " ".join(parts)).strip()


def text_of(path: Path, url: str = "") -> str:
    raw = path.read_bytes()
    if raw[:4] == b"%PDF":
        return pdf_text(path)
    return html_text(raw.decode("utf-8", errors="ignore"), url)


def instrument() -> dict:
    """What the fingerprints depend on besides the FAA's words. Recorded in the baseline, compared every run."""
    try:
        import pdfplumber
        import pdfminer
    except ImportError:
        raise InstrumentError("pdfplumber is required to read PDF sources: pip install pdfplumber") from None
    return {"method": METHOD, "pdfplumber": pdfplumber.__version__, "pdfminer.six": pdfminer.__version__}


def fp(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------------------------- the sources
def source_urls(data: dict) -> dict:
    """{url: [condition ids]} in first-seen order: each condition's page, its letter, then its blocks."""
    out = {}
    for c in data["conditions"]:
        urls = [c.get("page")] + [(c.get("letter") or {}).get("sourceURL")] + \
               [b.get("sourceURL") for b in c.get("blocks") or []]
        for u in urls:
            if u:
                ids = out.setdefault(u, [])
                if c["id"] not in ids:
                    ids.append(c["id"])
    return out


def read_one(u: str, where: Path, blob) -> tuple:
    shutil.rmtree(where, ignore_errors=True)  # a retry must fetch again, not reuse the bad download
    p = blob(u, where)
    if p is None:
        return None, 0, "unreachable"
    text = text_of(p, u)
    if not Q.readable(text.lower()):
        return None, len(text), "not readable prose"
    return fp(text), len(text), ""


def read_all(urls, cache: Path, blob=None) -> dict:
    """{url: (sha or None, text length, reason when None)}. blob(url, cache) -> Path or None (unreachable).
    One cache folder per source; paced; one retry after RETRY_WAIT_S; nothing fetched after DEADLINE_S."""
    blob = blob or Q.load_fid()._blob
    out, t0 = {}, time.monotonic()
    for i, u in enumerate(urls):
        if time.monotonic() - t0 > DEADLINE_S:
            out[u] = (None, 0, f"not fetched, the {DEADLINE_S / 60:.0f} minute time limit was reached")
            continue
        fetch, where = u.split("#", 1)[0], cache / f"{i:03d}"
        if i:
            time.sleep(PACE_S)
        out[u] = read_one(fetch, where, blob)
        if not out[u][0]:
            print(f"  retrying in {RETRY_WAIT_S:.0f} s ({out[u][2]}): {u}")
            time.sleep(RETRY_WAIT_S)
            out[u] = read_one(fetch, where, blob)
    return out


# ---------------------------------------------------------------------------------------------- the judgment
def judge(baseline: dict | None, data_sha: str, uses: dict, results: dict) -> tuple[int, str]:
    """(exit code, report for a finding or reason for an instrument problem). Pure, so the selftest drives it."""
    base = (baseline or {}).get("sources", {})
    changed = [u for u in uses if results[u][0] and u in base and base[u] != results[u][0]]
    missing = [u for u in uses if results[u][0] and u not in base]
    unchecked = [u for u in uses if not results[u][0]]
    data_moved = baseline is None or baseline.get("dataSha") != data_sha
    if not (changed or missing or data_moved):
        if unchecked:
            return 2, "could not read " + ", ".join(f"{u} ({results[u][2]})" for u in unchecked)
        return 0, ""
    lines = []
    if changed:
        lines.append("An FAA document the free AME request sheet quotes has changed since the sheet's sources were last "
                     "read. The server stops showing the FAA quotes until this is cleared.\n")
        lines += [f"- {u} (used by: {', '.join(uses[u])})" for u in changed]
        lines.append("")
    if missing:
        lines.append("These sources of the published sheet have no baseline, so nothing says they were read:\n")
        lines += [f"- {u} (used by: {', '.join(uses[u])})" for u in missing]
        lines.append("")
    if data_moved:
        lines.append("The published sheet data is not the data the source baseline was taken on (the sheet was "
                     "republished without re-baselining its sources).\n")
    report = "\n".join(lines) + (
        "\n## What to do\n\n"
        "Read each changed FAA document. If the FAA changed what the sheet relies on, correct sheet-curated.json in "
        "the app repo, rebuild and republish the sheet. Then, from the content repo, run "
        "`python3 scripts/check-sheet-sources.py --rebaseline` and commit .sheet-source-fingerprints.json.\n")
    if unchecked:
        report += ("\n## Not checked\n\n" + "\n".join(f"- {u} ({results[u][2]})" for u in unchecked) + "\n")
    # Below a "## " heading: file-finding.sh's fingerprint ignores everything from the first one.
    report += "\n## Checked\n\n" + "".join(
        f"- {u}: baseline {base.get(u, 'none')}, now {results[u][0]} ({results[u][1]} characters of text)\n"
        for u in changed + missing)
    report += (f"- published data sha256 {data_sha}, baseline taken on "
               f"{(baseline or {}).get('dataSha', 'none')} ({(baseline or {}).get('taken', 'never')})\n")
    return 1, report


def write_baseline(path: Path, data_sha: str, results: dict, inst: dict):
    doc = {"dataSha": data_sha, "taken": date.today().isoformat(), "instrument": inst,
           "sources": {u: r[0] for u, r in results.items()}}
    path.write_text(json.dumps(doc, indent=1, sort_keys=True) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------------------------- run
def run(work: Path | None, cache: Path | None, published: str, commit: str | None, rebaseline=False,
        baseline_path: Path = BASELINE, blob=None) -> tuple[int, str]:
    work = (work or Path(tempfile.mkdtemp(prefix="sheetsrc-"))).resolve()
    cache = (cache or Path(tempfile.mkdtemp(prefix="sheetsrccache-")) / "cache").resolve()
    work.mkdir(parents=True, exist_ok=True)
    (work / CHECKED).unlink(missing_ok=True)
    if cache.exists() and any(cache.iterdir()):
        return 2, f"the cache folder {cache} is not new: every source must be fetched fresh"
    try:
        srcs = {"published": published}
        if published.startswith(Q.BASE):
            commit = commit or Q.main_sha()
            print(f"pmg-securelink-viewer commit {commit}")
            srcs = Q.at_commit(srcs, commit)
        body = Q.get(srcs["published"], work / Q.NAMES["published"])
        data_sha = hashlib.sha256(body).hexdigest()
        try:
            uses = source_urls(json.loads(body))
        except (ValueError, KeyError, TypeError):
            raise InstrumentError("the published file is not a sheet data file") from None
        inst = instrument()
    except InstrumentError as e:
        return 2, str(e)
    baseline = None
    if not rebaseline:
        # Before any FAA fetch: a baseline this run cannot compare with is an instrument problem, not a finding.
        try:
            baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            baseline = None
        except ValueError:
            return 2, f"{baseline_path.name} is not valid JSON"
        if baseline is not None and baseline.get("instrument") != inst:
            return 2, (f"the baseline was taken with {baseline.get('instrument')}, this run has {inst}. Install the "
                       "pinned versions, or (after reading every source) re-baseline on purpose with --rebaseline")
    t0 = time.monotonic()
    try:
        results = read_all(uses, cache, blob)
    except InstrumentError as e:
        return 2, str(e)
    print(f"read {len(uses)} sources in {time.monotonic() - t0:.0f} s (cache {cache})")
    for u, (s, n, why) in results.items():
        print(f"  {s[:16] if s else 'NOT CHECKED':16}  {n:7d}  {u}" + (f"  ({why})" if why else ""))
    if rebaseline:
        bad = [u for u, r in results.items() if not r[0]]
        if bad:
            return 2, "refusing to re-baseline, not readable: " + ", ".join(f"{u} ({results[u][2]})" for u in bad)
        write_baseline(baseline_path, data_sha, results, inst)
        return 0, (f"baseline written to {baseline_path.name}: {len(results)} sources, data sha256 {data_sha}, "
                   f"instrument {inst}")
    code, text = judge(baseline, data_sha, uses, results)
    (work / CHECKED).write_text(json.dumps({"commit": commit, "dataSha": data_sha, "code": code}) + "\n")
    if code == 1 and commit:
        text += f"- pmg-securelink-viewer commit {commit}\n"
    return code, text


# ---------------------------------------------------------------------------------------------- selftest
def tiny_pdf(text: str, table=None) -> bytes:
    """A one-page PDF with `text` in Helvetica, offsets computed, so pdfplumber really parses it. table: rows of cell
    strings, drawn as ruled cells so pdfplumber's extract_tables() finds them."""
    ops = [f"BT /F1 10 Tf 40 760 Td ({text}) Tj ET"]
    for r, row in enumerate(table or []):
        for c, cell in enumerate(row):
            x, y = 40 + 200 * c, 700 - 30 * r
            ops += [f"{x} {y} 200 30 re S", f"BT /F1 10 Tf {x + 6} {y + 10} Td ({cell}) Tj ET"]
    stream = "\n".join(ops).encode()
    objs = [b"<< /Type /Catalog /Pages 2 0 R >>",
            b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 5 0 R >> >> "
            b"/Contents 4 0 R >>",
            b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    out, offs = bytearray(b"%PDF-1.4\n"), []
    for i, o in enumerate(objs, 1):
        offs.append(len(out))
        out += f"{i} 0 obj\n".encode() + o + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode()
    out += b"".join(f"{o:010d} 00000 n \n".encode() for o in offs)
    out += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return bytes(out)


def selftest() -> int:
    """Negative AND positive controls (GOTCHAS_VERIFY.md section 30: a zero is not believable without both)."""
    global PACE_S, RETRY_WAIT_S
    PACE_S, RETRY_WAIT_S = 0, 0
    PROSE = " ".join("w" + chr(97 + i // 26) + chr(97 + i % 26) for i in range(60))
    page = ('<html><head><meta name="a" content="1"><meta name="twitter:site" content="@faa">'
            '<script src="/collapsiblock.js?tjxmlb"></script><title>T</title></head><body>'
            '<header>FAA header</header><nav><a href="/x">Menu one</a></nav>'
            f'<main><h1>Asthma</h1><p>The AME must review &amp; {PROSE}. Submit the <abbr>FAA</abbr> form within 6 months '
            'if FEV1 is LESS than 60%. Use the <a class="x" href="/ame_guide/media/status.pdf?v=tjxmlb">Status '
            'Summary</a> and <a href="#top">back to top</a>.</p></main>'
            '<footer>Page last updated footer</footer><script>var x=1;</script></body></html>')
    h = lambda s: fp(html_text(s))
    same = [("identical text", page),
            ("a Drupal cache-buster changed", page.replace("?tjxmlb", "?tkg5s1")),
            ("meta tags reordered in <head>", page.replace('<meta name="a" content="1"><meta name="twitter:site" '
                                                           'content="@faa">', '<meta name="twitter:site" content="@faa">'
                                                           '<meta name="a" content="1">')),
            ("nav changed", page.replace("Menu one", "Menu two and three")),
            ("footer changed", page.replace("footer</footer>", "footer changed</footer>")),
            ("inline script changed", page.replace("var x=1;", "var x=2;")),
            ("a cache-buster on a link changed", page.replace("status.pdf?v=tjxmlb", "status.pdf?v=zz9")),
            ("an in-page anchor changed", page.replace('href="#top"', 'href="#main"'))]
    diff = [("one visible word changed", page.replace("must review", "may review")),
            ("a sentence inserted", page.replace("Submit the", "Also send a new report. Submit the")),
            ("a number changed", page.replace("6 months", "12 months")),
            ("a percentage changed", page.replace("60%", "50%")),
            ("a link repointed, its text unchanged", page.replace("status.pdf?", "status_2026.pdf?"))]
    for name, p in same:
        assert h(p) == h(page), f"{name}: should be SAME"
    for name, p in diff:
        assert h(p) != h(page), f"{name}: should be DIFF"
    assert "Menu" not in html_text(page) and "collapsiblock" not in html_text(page) and "&amp;" not in html_text(page)
    assert "/x]" not in html_text(page, "https://www.faa.gov/p"), "a nav link is dropped with the nav"
    assert "[link https://www.faa.gov/ame_guide/media/status.pdf]" in html_text(page, "https://www.faa.gov/p"), \
        "a link target is absolute, without its query string"
    assert Q.readable(html_text(page).lower()), "the stand-in page is readable prose"

    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        T = [["Interval", "Every 6 months"], ["FEV1", "Less than 60%"]]
        files = {"a.pdf": tiny_pdf("The AME must review the report within 6 months.", T),
                 "b.pdf": tiny_pdf("The AME must review the report within 6 months.", T),
                 "c.pdf": tiny_pdf("The AME may review the report within 6 months.", T),
                 "d.pdf": tiny_pdf("The AME must review the report within 12 months.", T),
                 "e.pdf": tiny_pdf("The AME must review the report within 6 months.",
                                   [T[0], ["FEV1", "Less than 50%"]])}
        for n, b in files.items():
            (d / n).write_bytes(b)
        ta, tb, tc, td, te = (text_of(d / n) for n in files)
        assert "must review" in ta, f"pdfplumber reads the stand-in PDF ({ta!r})"
        assert ta.count("Less than 60%") == 2, f"table cells are read on top of the page text ({ta!r})"
        assert fp(ta) == fp(tb), "identical PDF text SAME"
        assert fp(ta) != fp(tc), "PDF text change DIFF"
        assert fp(ta) != fp(td), "PDF number change DIFF"
        assert fp(ta) != fp(te), "PDF table cell number change DIFF"

    # The judgment, both ways.
    uses = {"https://www.faa.gov/p": ["si-a"], "https://www.faa.gov/q.pdf": ["si-a", "si-b"]}
    base = {"dataSha": "d" * 64, "taken": "2026-11-14", "sources": {"https://www.faa.gov/p": "1" * 64,
                                                                     "https://www.faa.gov/q.pdf": "2" * 64}}
    ok = {"https://www.faa.gov/p": ("1" * 64, 900, ""), "https://www.faa.gov/q.pdf": ("2" * 64, 900, "")}
    assert judge(base, "d" * 64, uses, ok)[0] == 0, "clean"
    c, t = judge(base, "d" * 64, uses, dict(ok, **{"https://www.faa.gov/q.pdf": ("3" * 64, 901, "")}))
    assert c == 1 and "q.pdf (used by: si-a, si-b)" in t.split("\n## ")[0], "a changed source is a finding naming it"
    c2, t2 = judge(base, "d" * 64, uses, dict(ok, **{"https://www.faa.gov/q.pdf": ("4" * 64, 950, "")}))
    head = lambda s: re.sub(r"\d", "", s.split("\n## ")[0])
    assert head(t) == head(t2), "the findings section is stable while the same source keeps changing"
    unread = dict(ok, **{"https://www.faa.gov/p": (None, 40, "not readable prose")})
    assert judge(base, "d" * 64, uses, unread)[0] == 2, "unreadable is could-not-check, not a finding"
    assert judge(base, "d" * 64, uses, dict(ok, **{"https://www.faa.gov/p": (None, 0, "unreachable")}))[0] == 2
    c, t = judge(base, "e" * 64, uses, ok)
    assert c == 1 and "not the data the source baseline" in t, "a data sha mismatch is a finding"
    c, t = judge(dict(base, sources={"https://www.faa.gov/p": "1" * 64}), "d" * 64, uses, ok)
    assert c == 1 and "no baseline" in t, "a source missing from the baseline is a finding"
    assert judge(None, "d" * 64, uses, ok)[0] == 1, "no baseline at all is a finding"
    c, t = judge(base, "d" * 64, uses, dict(unread, **{"https://www.faa.gov/q.pdf": ("3" * 64, 1, "")}))
    assert c == 1 and "## Not checked" in t, "a finding still wins over an unreadable source"
    assert source_urls({"conditions": [
        {"id": "a", "page": "P", "letter": {"sourceURL": "L"}, "blocks": [{"sourceURL": "B"}, {"sourceURL": "P"}]},
        {"id": "b", "page": "B", "letter": None, "blocks": []}]}) == {"P": ["a"], "L": ["a"], "B": ["a", "b"]}

    # The whole path offline: a local published file, a stand-in downloader, a temp baseline.
    import contextlib, io
    LONG = "https://www.faa.gov/ame_guide/" + "x" * 120
    data = json.dumps({"note": "n", "conditions": [{"id": "si-a", "name": "A", "page": "https://www.faa.gov/p",
                                                    "letter": None, "blocks": [{"sourceURL": "https://www.faa.gov/q"},
                                                                               {"sourceURL": LONG + "/one#p-1"},
                                                                               {"sourceURL": LONG + "/two"}]}]})
    with tempfile.TemporaryDirectory() as d, contextlib.redirect_stdout(io.StringIO()):
        d = Path(d)
        (d / "pub.json").write_text(data)
        pages = {"https://www.faa.gov/p": page, "https://www.faa.gov/q": page.replace("Asthma", "COPD"),
                 LONG + "/one": page.replace("Asthma", "One"), LONG + "/two": page.replace("Asthma", "Two")}
        fetched, flaky = [], {}

        def blob(u, cache):  # the real _blob's cache key: the first 120 characters of the URL
            fetched.append(u)
            if flaky.get(u):
                flaky[u] -= 1
                body = "403 Forbidden"
            elif pages[u] is None:
                return None
            else:
                body = pages[u]
            cache.mkdir(parents=True, exist_ok=True)
            f = cache / re.sub(r"\W+", "_", u)[:120]
            if not f.exists():
                f.write_text(body)
            return f
        bl = d / "baseline.json"
        go = lambda n, **k: run(d / f"w{n}", d / f"c{n}", str(d / "pub.json"), None, baseline_path=bl, blob=blob, **k)
        pages["https://www.faa.gov/q"] = "403 Forbidden"
        assert go(0, rebaseline=True)[0] == 2 and not bl.exists(), "re-baseline refuses an unreadable source"
        pages["https://www.faa.gov/q"] = page.replace("Asthma", "COPD")
        assert go(1, rebaseline=True)[0] == 0 and bl.exists(), "re-baseline writes the file"
        doc = json.loads(bl.read_text())
        assert bl.read_text().endswith("}\n") and list(doc) == sorted(doc) and len(doc["sources"]) == 4
        assert doc["instrument"] == instrument() and doc["instrument"]["method"] == METHOD, "the instrument is recorded"
        assert doc["sources"][LONG + "/one#p-1"] != doc["sources"][LONG + "/two"], \
            "two URLs sharing a 120 character prefix are fetched into their own folders"
        assert all("#" not in u for u in fetched), "a fragment is dropped before the fetch"
        assert go(2)[0] == 0, "clean against its own baseline"
        flaky["https://www.faa.gov/q"] = 1
        assert go(21)[0] == 0, "a source blocked once is fetched again and read"
        flaky["https://www.faa.gov/q"] = 2
        assert go(22)[0] == 2, "a source blocked twice is could-not-check"
        good = bl.read_text()
        bl.write_text(json.dumps(dict(doc, instrument=dict(doc["instrument"], pdfplumber="0.0.1"))))
        n = len(fetched)
        c, t = go(23)
        assert c == 2 and "pinned versions" in t and len(fetched) == n, "another pdfplumber: exit 2, nothing fetched"
        bl.write_text(json.dumps({k: v for k, v in doc.items() if k != "instrument"}))
        assert go(24)[0] == 2, "a baseline with no instrument record (older method) is exit 2, not a mass finding"
        bl.write_text(good)
        assert json.loads((d / "w2" / CHECKED).read_text())["dataSha"] == hashlib.sha256(data.encode()).hexdigest()
        pages["https://www.faa.gov/p"] = page.replace("?tjxmlb", "?zzz")
        assert go(3)[0] == 0, "a cache-buster is not a change"
        pages["https://www.faa.gov/p"] = page.replace("must review", "may review")
        assert go(4)[0] == 1, "a changed word is a finding"
        pages["https://www.faa.gov/p"] = None
        assert go(5)[0] == 2, "unreachable is could-not-check"
        pages["https://www.faa.gov/p"] = page
        (d / "pub.json").write_text(data + " ")
        code, text = go(6)
        assert code == 1 and "not the data" in text, "the published data moved: a finding"
        (d / "c7").mkdir()
        (d / "c7" / "x").write_text("old")
        assert go(7)[0] == 2, "a used cache is refused"
    print("selftest ok")
    return 0


def main(argv: list[str]) -> int:
    if "--selftest" in argv:
        return selftest()
    ap = argparse.ArgumentParser()
    ap.add_argument("--work", type=Path)
    ap.add_argument("--cache", type=Path)
    ap.add_argument("--published", default=Q.DEFAULTS["published"])
    ap.add_argument("--commit")
    ap.add_argument("--rebaseline", action="store_true")
    a = ap.parse_args(argv)
    if a.commit and not re.fullmatch(r"[0-9a-f]{40}", a.commit):
        print("--commit must be a full 40 character commit sha")
        return 2
    Path(REPORT).unlink(missing_ok=True)
    t0 = time.monotonic()
    code, text = run(a.work, a.cache, a.published, a.commit, rebaseline=a.rebaseline)
    took = f"{time.monotonic() - t0:.0f} s"
    if a.rebaseline:
        print(f"\n{'RE-BASELINED' if code == 0 else 'COULD NOT RE-BASELINE'} ({took}): {text}")
    elif code == 1:
        Path(REPORT).write_text(text, encoding="utf-8")
        print(f"\nFINDING ({took}), written to {REPORT}:\n\n{text}")
    elif code == 2:
        print(f"\nCOULD NOT CHECK ({took}): {text}. Not a finding.")
    else:
        print(f"\nCLEAN ({took}): every FAA source of the sheet reads as it did at the baseline.")
    return code


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except Exception:
        traceback.print_exc()
        sys.exit(2)
