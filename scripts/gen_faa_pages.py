#!/usr/bin/env python3
"""Generate the free FAA reference pages on pilotmedicalguardian.com (live 2026-11-15).

Reads this repo's validated v1/ JSON and writes static pages into the repo root
(faa-medications/, faa-conditions/, aviation-medical-examiners/, sitemap block, homepage section), plus /faa-lookup-index.json and /faa-lookup.js.
FAA text is rendered VERBATIM from the JSON (html-escaped only). No verdict
chips: any status stays inside the cited prose, in body color.

Usage:
  python3 gen_faa_pages.py [--src CONTENT_REPO] [--out SITE_DIR]   build everything
  python3 gen_faa_pages.py --check [--src ...] [--out ...]          exit 1 if any built
      medication page's FAA text differs from the JSON (for CI)

Layout of this file: helpers -> page shell -> medications -> conditions ->
examiners -> lookup index -> homepage -> sitemap -> check -> main.
Output is deterministic: stable sort orders, dates taken from the data.
"""
import argparse, collections, datetime, html, json, os, re, shutil, sys, unicodedata

HERE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "faa_pages")  # CSS/JS sources
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ap = argparse.ArgumentParser()
ap.add_argument("--src", default=REPO)
ap.add_argument("--out", default=REPO)
ap.add_argument("--check", action="store_true", help="verify built pages against the JSON, build nothing")
args = ap.parse_args()
SRC, OUT = args.src, args.out
SITE = "https://pilotmedicalguardian.com"
V = "20261127a"   # cache-buster for site-v2.css, faa-lookup.js, index JSON

def own_note(s):
    """informationalNote is OUR wording, not the FAA's; spell out the app name publicly."""
    return (s or "").replace("PMG ", "Pilot Medical Guardian ")

# A page whose last check is older than this shows a plain re-check line (check-verification-age.py uses 120).
STALE_DAYS = 120
TODAY = datetime.date.fromisoformat(os.environ.get("BUILD_DATE") or datetime.date.today().isoformat())

def load(name):
    with open(os.path.join(SRC, "v1", name), encoding="utf-8") as f:
        return json.load(f)

MEDS = load("medications.json")
DISPO = load("disposition_tables.json")
SI = load("si_conditions.json")
AMES = load("ame_directory_full.json")

e = lambda s: html.escape(s or "", quote=True)

def slugify(s):
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    s = s.replace("+", " ").replace("/", " ")
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")

MONTHS = ["January", "February", "March", "April", "May", "June", "July",
          "August", "September", "October", "November", "December"]
def nice_date(y, m, d): return f"{MONTHS[int(m) - 1]} {int(d)}, {int(y)}"
def short_date(y, m, d): return f"{MONTHS[int(m) - 1][:3]} {int(d)}, {int(y)}"
def iso_nice(iso):
    y, m, d = iso[:10].split("-"); return nice_date(y, m, d)
def iso_short(iso):
    y, m, d = iso[:10].split("-"); return short_date(y, m, d)
def checked_stamp(items, what):
    # Index-page stamp, worded by Ryan 11/21 ("FAA sources checked [date range]. Dates on individual
    # entries when the FAA provides one."), shown as its own line under the H1 so it reads at a glance.
    ds = sorted(x["envelope"]["lastVerified"][:10] for x in items)
    lo, hi = ds[0], ds[-1]
    if lo == hi:
        rng = iso_nice(lo)
    elif lo[:4] == hi[:4]:
        y, m, d = lo.split("-"); rng = f"{MONTHS[int(m) - 1]} {int(d)} to {iso_nice(hi)}"
    else:
        rng = f"{iso_nice(lo)} to {iso_nice(hi)}"
    return (f'<p class="stamp"><svg class="stamp-i" viewBox="0 0 16 16" aria-hidden="true"><path d="M3.5 8.5l3 3 6-7"/></svg>'
            f'<span><strong>FAA sources checked {rng}.</strong> Dates on individual entries when the FAA provides one.</span></p>')
def cap1(s): return s[:1].upper() + s[1:]
def sort_key(s):
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    return re.sub(r"^[^a-z0-9]+", "", s)
def letter_of(s):
    k = sort_key(s); return k[0].upper() if k and k[0].isalpha() else "#"

def prose(text):
    """Verbatim prose -> HTML paragraphs. Blank line = new paragraph, newline = <br>."""
    paras = [p for p in re.split(r"\n\s*\n", text.strip()) if p.strip()]
    return "\n".join("<p>" + "<br>".join(e(l) for l in p.split("\n")) + "</p>" for p in paras)

DATE_RE = re.compile(r"(?:updated|Updated)\s+(\d{2})[/-](\d{2})[/-](\d{4})")
def citation_parts(cit):
    """Split a multi-source citation on '; FAA' boundaries -> [(text, (y,m,d)|None)]."""
    out = []
    for p in re.split(r";\s+(?=FAA )", cit):
        m = DATE_RE.search(p)
        out.append((p, (m.group(3), m.group(1), m.group(2)) if m else None))
    return out

# ---------------------------------------------------------------- shell
GTAG = """  <script async src="https://www.googletagmanager.com/gtag/js?id=AW-18408761824"></script>
  <script>
    window.dataLayer = window.dataLayer || [];
    function gtag(){dataLayer.push(arguments);}
    gtag('js', new Date());
    gtag('config', 'AW-18408761824');
  </script>
  <script defer src="/ads-conversion.js"></script>"""
CF = """  <script defer src='https://static.cloudflareinsights.com/beacon.min.js' data-cf-beacon='{"token": "35d3d8be8292443fa9f3a2235ccc7aea"}'></script>"""

def appstore(ct):
    return f"https://apps.apple.com/app/apple-store/id6772534988?pt=128922811&amp;ct={ct}&amp;mt=8"

def nav(ct, current=None):
    # Site header (reorg 11/25, Ryan's spec): Features, Free Lookups, Guides, Pricing, FAQ, Download.
    # Every lookup page marks "Free Lookups" as current. Keep in step with the static pages' header.
    cur_key = "lookups" if current in ("med", "cond", "ame") else current
    def a(href, label, key):
        cur = ' aria-current="page"' if key == cur_key else ""
        return f'<a class="nav-hide-sm" href="{href}"{cur}>{label}</a>'
    return f"""  <header class="site-nav">
    <div class="container">
      <a class="nav-brand" href="/"><img src="/logo-96.png" alt="Pilot Medical Guardian logo" width="30" height="30"><span>Pilot Medical Guardian</span></a>
      <input type="checkbox" id="navtoggle" class="nav-toggle-cb" hidden>
      <label for="navtoggle" class="nav-toggle"><span class="sr">Menu</span><span aria-hidden="true">&#9776;</span></label>
      <nav class="nav-links" aria-label="Main">
        {a('/features.html', 'Features', 'features')}
        {a('/lookups.html', 'Free Lookups', 'lookups')}
        {a('/guides.html', 'Guides', 'guides')}
        {a('/pricing.html', 'Pricing', 'pricing')}
        {a('/faq.html', 'FAQ', 'faq')}
        <a class="nav-cta" href="{appstore(ct)}" aria-label="Download on the App Store">Download</a>
      </nav>
    </div>
  </header>"""

FOOT_LOOKUPS = '<p>Free lookups: <a href="/faa-medications/">FAA medication lookup</a> · <a href="/faa-conditions/">FAA conditions and disposition tables</a> · <a href="/aviation-medical-examiners/">Find an aviation medical examiner</a></p>'
FOOTER = f"""  <footer>
    <div class="wrap">
      <p>&copy; 2026 YellowArc LLC &middot; Pilot Medical Guardian</p>
      <p>Not affiliated with or endorsed by the FAA.</p>
      {FOOT_LOOKUPS}
      <p><a href="/whats-new.html">What's New</a> · <a href="/faq.html">FAQ</a> · <a href="/privacy.html">Privacy</a> · <a href="/terms.html">Terms</a></p>
      <p>Guides: <a href="/medxpress-guide.html">FAA MedXPress guide</a> · <a href="/medxpress-checklist.html">MedXPress prep checklist</a> · <a href="/basicmed-guide.html">FAA BasicMed guide</a> · <a href="/faa-medical-duration.html">FAA medical certificate duration</a> · <a href="/special-issuance.html">FAA Special Issuance</a></p>
    </div>
  </footer>"""

def page(path, title, desc, body, ld, ct, current=None, lastmod=None):
    canonical = SITE + path.replace("index.html", "")
    doc = f"""<!doctype html>
<html lang="en">
<head>
{GTAG}
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{e(title)}</title>
  <meta name="description" content="{e(desc)}">
  <meta name="theme-color" content="#1c66d9">
  <link rel="canonical" href="{canonical}">
  <meta property="og:type" content="website">
  <meta property="og:site_name" content="Pilot Medical Guardian">
  <meta property="og:title" content="{e(title)}">
  <meta property="og:description" content="{e(desc)}">
  <meta property="og:url" content="{canonical}">
  <meta property="og:image" content="{SITE}/og-card.png">
  <meta name="twitter:card" content="summary_large_image">
  <link rel="icon" type="image/png" sizes="32x32" href="/favicon-32.png">
  <link rel="apple-touch-icon" href="/apple-touch-icon.png">
  <link rel="stylesheet" href="/site.css?v=20261127a">
  <link rel="stylesheet" href="/site-v2.css?v={V}">
  <script defer src="/faa-lookup.js?v={V}"></script>
  <script type="application/ld+json">{json.dumps(ld, ensure_ascii=False, separators=(',', ':'))}</script>
{CF}
  <meta name="apple-itunes-app" content="app-id=6772534988, affiliate-data=pt=128922811&amp;ct={ct}&amp;mt=8">
</head>
<body class="v2">
  <a class="skip" href="#main">Skip to content</a>
{nav(ct, current)}
{body}
{FOOTER}
</body>
</html>
"""
    full = os.path.join(OUT, path.lstrip("/"))
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, "w", encoding="utf-8") as f:
        f.write(doc)
    return canonical, lastmod

def crumbs(items):
    lis, ld = [], []
    for i, (name, p) in enumerate(items, 1):
        if p:
            lis.append(f'<li><a href="{p}">{e(name)}</a></li>')
            ld.append({"@type": "ListItem", "position": i, "name": name, "item": SITE + p})
        else:
            lis.append(f'<li aria-current="page">{e(name)}</li>')
    return (f'<nav class="crumbs" aria-label="Breadcrumb"><ol>{"".join(lis)}</ol></nav>',
            {"@type": "BreadcrumbList", "itemListElement": ld})

I_SEARCH = '<svg class="lk-i" viewBox="0 0 20 20" aria-hidden="true"><circle cx="8.75" cy="8.75" r="5.75"/><path d="M13 13l4.25 4.25"/></svg>'
I_EXT = '<svg class="i-ext" viewBox="0 0 16 16" aria-hidden="true"><path d="M6 3.5H3.5v9h9V10M9 3h4v4M13 3L7.5 8.5"/></svg>'

def lookup_bar(placeholder="Medication, condition, or town"):
    """Global lookup. Popup is an overlay, so loading the index never shifts layout."""
    return f"""<form class="lk" action="/faa-medications/" method="get" role="search" data-lookup="/faa-lookup-index.json?v={V}">
        <label class="sr" for="lk-q">Look up a medication, an FAA condition, or examiners by town</label>
        <div class="lk-field">{I_SEARCH}<input id="lk-q" name="q" type="text" inputmode="search" role="combobox" aria-autocomplete="list" aria-expanded="false" aria-controls="lk-pop" autocomplete="off" autocapitalize="off" spellcheck="false" enterkeyhint="go" placeholder="{e(placeholder)}"><kbd class="lk-kbd" aria-hidden="true">/</kbd></div>
        <div class="lk-pop" id="lk-pop" role="listbox" aria-label="Lookup results" hidden></div>
        <p class="sr lk-status" role="status" aria-live="polite"></p>
      </form>"""

def filter_bar(target, empty_id, label, placeholder, total, unit):
    return f"""<div class="lk lk-filter" data-filter="{target}" data-empty="{empty_id}">
        <label class="sr" for="lk-f">{e(label)}</label>
        <div class="lk-field">{I_SEARCH}<input id="lk-f" name="q" type="search" autocomplete="off" autocapitalize="off" spellcheck="false" enterkeyhint="go" placeholder="{e(placeholder)}" aria-describedby="lk-count"></div>
        <p class="lk-count" id="lk-count" aria-live="polite" data-unit="{e(unit)}">{total:,} {e(unit)}</p>
      </div>"""

def tool_band(inner):
    return f'  <div class="tool-band"><div class="wrap wide">{inner}</div></div>'

def head_block(crumb_html, h1, sub=None, extra=""):
    s = f'<p class="v2-sub">{sub}</p>' if sub else ""
    return f"""  <header class="v2-head">
    <div class="wrap wide">
      {crumb_html}
      <h1>{h1}</h1>
      {extra if 'class="stamp"' in extra else ""}{s}{"" if 'class="stamp"' in extra else extra}
    </div>
  </header>"""

APP_LINES = {
    "med": "Pilot Medical Guardian keeps this same FAA medication reference in the app, next to your own medication list.",
    "cond": "Pilot Medical Guardian keeps your records, your medical certificate dates, and your Special Issuance paperwork organized, so you walk into every exam ready.",
    "ame": "Pilot Medical Guardian keeps your records, your medications, and your Item 18 answers organized before you sit down with your AME.",
}
def app_line(kind, ct):
    return (f'<p class="app-line"><img src="/logo-96.png" alt="" width="24" height="24" loading="lazy">'
            f'<span>{APP_LINES[kind]} Your health data stays on your device and your own iCloud. '
            f'<a href="{appstore(ct)}">Free to download on the App Store</a></span></p>')

NEUTRAL = "This is what the FAA publishes, not a determination about you. Your AME decides."

# ---------------------------------------------------------------- medications
slugs, seen = {}, collections.Counter()
for m in MEDS:
    s = slugify(m["genericName"]); seen[s] += 1
    slugs[m["genericName"]] = s if seen[s] == 1 else f"{s}-{seen[s]}"
by_cat = collections.defaultdict(list)
for m in MEDS:
    by_cat[m["category"]].append(m)

def brand_str(brands, limit=3):
    if not brands: return ""
    return ", ".join(brands) if len(brands) <= limit else ", ".join(brands[:limit]) + f" and {len(brands) - limit} more"

def med_page(m):
    g, slug, env = m["genericName"], slugs[m["genericName"]], m["envelope"]
    G = cap1(g)
    brands = m.get("brandNames") or []
    bshort = brand_str(brands)
    head = f"{G} ({bshort})" if bshort else G
    title = f"{head} and the FAA medical"
    desc = (f"{head} and the FAA medical for pilots: the FAA reference text, the FAA source document and its date, "
            f"and when I last checked it. Information, not advice.")
    crumb_html, crumb_ld = crumbs([("Home", "/"), ("FAA medications", "/faa-medications/"), (G, None)])
    text = prose(m["faaStatusDescription"])
    neutral = "Your AME decides." if "not a determination about you" in (m["faaStatusDescription"] + (m.get("informationalNote") or "")) else NEUTRAL
    if m.get("informationalNote"):
        text += "\n" + prose(own_note(m["informationalNote"]))
    parts = citation_parts(env["sourceCitation"])
    dates = []
    for _, d in parts:
        if d and (d, short_date(*d)) not in dates:
            dates.append((d, short_date(*d)))
    checked_short, checked_long = iso_short(env["lastVerified"]), iso_nice(env["lastVerified"])
    age = (TODAY - datetime.date.fromisoformat(env["lastVerified"][:10])).days
    stale = (f'\n          <p class="src-meta"><strong>Re-check pending.</strong> It has been more than {STALE_DAYS} days since my last check. Rely on the FAA source linked above.</p>') if age > STALE_DAYS else ""
    # Trust strip: visible above the fold on a phone.
    tr = []
    if dates:
        lab = "FAA document updated" if len(dates) == 1 else "FAA documents updated"
        tr.append(f'<span><span class="t-k">{lab}</span> ' + "; ".join(f'<time datetime="{y}-{mo}-{da}">{t}</time>' for (y, mo, da), t in dates) + '</span>')
    tr.append(f'<span><span class="t-k">Checked</span> <time datetime="{env["lastVerified"][:10]}">{checked_short}</time></span>')
    tr.append(f'<a href="{e(env["sourceURL"])}" rel="noopener">FAA source{I_EXT}</a>')
    trust = '<p class="trust">' + "".join(tr) + "</p>"
    meta = " · ".join(x for x in (", ".join(brands), m["category"]) if x)
    mx = ""
    if m.get("medxpressName"):
        n = m["medxpressName"]
        mx = (f'<div class="mx"><p>In MedXPress, this is listed as: <b class="mx-name">{e(n)}</b></p>'
              f'<button type="button" class="cp" data-copy="{e(n)}" aria-label="Copy {e(n)}">'
              f'<svg viewBox="0 0 16 16" aria-hidden="true"><rect x="5.5" y="5.5" width="8" height="8" rx="1.5"/><path d="M10.5 3.5v-.5a1 1 0 0 0-1-1h-6a1 1 0 0 0-1 1v6a1 1 0 0 0 1 1h.5"/></svg>'
              f'<span class="cp-l">Copy</span></button></div>')
    cites = "".join(f'<li>{e(t)}</li>' for t, _ in parts)
    links = ""
    if m.get("links"):
        links = ('<h2 class="h-s">Related FAA documents</h2><ul class="doc-links">' + "".join(
            f'<li><a href="{e(l["url"])}" rel="noopener">{e(l["title"])}{I_EXT}</a></li>' for l in m["links"]) + "</ul>")
    rel = [x for x in by_cat[m["category"]] if x is not m][:8]
    related = ""
    if rel:
        related = ('<p class="related"><span class="t-k">Same category</span> ' + ", ".join(
            f'<a href="/faa-medications/{slugs[x["genericName"]]}.html">{e(cap1(x["genericName"]))}</a>' for x in rel) + "</p>")
    body = tool_band(lookup_bar()) + "\n" + head_block(crumb_html, e(title), extra=f'<p class="meta-line">{e(meta)}</p>{trust}{mx}')
    body += f"""
  <main class="v2-main" id="main">
    <div class="wrap wide">
      <div class="answer">
        <section class="faa-text" aria-label="FAA reference text">
{text}
        </section>
        <div class="src">
          <p class="src-h">Source</p>
          <ul class="src-list">{cites}</ul>
          <p class="src-meta"><a href="{e(env['sourceURL'])}" rel="noopener">Open the FAA source{I_EXT}</a><span class="src-url">{e(env['sourceURL'].replace('https://', ''))}</span></p>
          <p class="src-meta">I last checked this against the FAA source on {checked_long}.</p>{stale}
        </div>
        <p class="neutral">{neutral}</p>
        {links}
        {related}
        {app_line('med', 'seo-med')}
      </div>
    </div>
  </main>"""
    ld = {"@context": "https://schema.org", "@graph": [crumb_ld, {
        "@type": "MedicalWebPage", "name": title, "description": desc,
        "url": f"{SITE}/faa-medications/{slug}.html", "lastReviewed": env["lastVerified"][:10],
        # Substance, not Drug: schema.org Drug is a Product subtype, so Google read every page as a
        # Product snippet missing offers/review/aggregateRating (Rich Results Test 2026-11-16). We sell nothing here.
        "about": {"@type": "Substance", "name": g, **({"alternateName": brands} if brands else {})},
        "citation": [{"@type": "CreativeWork", "name": t, "url": env["sourceURL"]} for t, _ in parts],
        "publisher": {"@type": "Organization", "name": "Pilot Medical Guardian", "url": SITE + "/"},
    }]}
    return page(f"/faa-medications/{slug}.html", title, desc, body, ld, "seo-med", "med", env["lastVerified"][:10])

def az_nav(letters):
    return '<nav class="az" aria-label="Jump to letter">' + "".join(
        f'<a href="#l-{"num" if L == "#" else L}">{L}</a>' for L in letters) + "</nav>"

def no_match(id_, tail):
    return f'<p id="{id_}" class="empty" hidden><b>No match for “<span data-q></span>”.</b> {tail}</p>'

def med_index():
    groups = collections.defaultdict(list)
    for m in sorted(MEDS, key=lambda x: sort_key(x["genericName"])):
        groups[letter_of(m["genericName"])].append(m)
    letters = sorted(groups, key=lambda L: (L == "#", L))
    secs = []
    for L in letters:
        rows = []
        for m in groups[L]:
            b = ", ".join(m.get("brandNames") or [])
            rows.append(f'<li data-k="{e(m["genericName"] + " " + b)}"><a href="/faa-medications/{slugs[m["genericName"]]}.html">'
                        f'<span class="d-m">{e(cap1(m["genericName"]))}</span><span class="d-s">{e(b)}</span>'
                        f'<span class="d-r">{e(m["category"])}</span></a></li>')
        secs.append(f'<section class="dg" data-group id="l-{"num" if L == "#" else L}"><h2 class="dg-h">{L}</h2><ul class="dense">{"".join(rows)}</ul></section>')
    crumb_html, crumb_ld = crumbs([("Home", "/"), ("FAA medications", None)])
    title = f"Medication List for FAA Medicals: {len(MEDS)} Medications, A to Z"
    desc = ("Look up a medication by brand or generic name and see the FAA reference text, the FAA source document, "
            "and its date. Free, no account. Information, not advice.")
    body = tool_band(filter_bar("dl", "dl-none", "Filter medications by brand or generic name", "Filter by brand or generic name", len(MEDS), "medications"))
    body += "\n" + head_block(crumb_html, "Medication list for FAA medicals",
                              "Every entry shows the FAA reference text the app uses, the FAA document it cites, and its date when the FAA gives one. Information, not advice: your AME decides.", checked_stamp(MEDS, "entry"))
    body += f"""
  <main class="v2-main" id="main">
    <div class="wrap wide">
      {az_nav(letters)}
      <div id="dl">
      {no_match('dl-none', 'Try the generic name, or check the spelling. If a medication is not here, ask your AME.')}
      {"".join(secs)}
      </div>
      <p class="neutral">{NEUTRAL}</p>
      {app_line('med', 'seo-med-index')}
    </div>
  </main>"""
    ld = {"@context": "https://schema.org", "@graph": [crumb_ld, {
        "@type": "CollectionPage", "name": title, "description": desc, "url": SITE + "/faa-medications/", "numberOfItems": len(MEDS)}]}
    return page("/faa-medications/index.html", title, desc, body, ld, "seo-med", "med", max(x["envelope"]["lastVerified"] for x in MEDS)[:10])

# ---------------------------------------------------------------- conditions
def dispo_meta(d):
    items = d.get("examItems") or []
    item_s = (f'Item{"s" if len(items) > 1 else ""} {", ".join(items)}') if items else ""
    date_s = ""
    if d.get("updated"):
        y, mo, da = d["updated"].split("-")
        date_s = f'{d.get("dateWord") or "Updated"} {short_date(y, mo, da)}'
    return item_s, date_s

def cond_index():
    groups = collections.defaultdict(list)
    for d in sorted(DISPO, key=lambda x: sort_key(x["title"])):
        groups[letter_of(d["title"])].append(d)
    letters = sorted(groups, key=lambda L: (L == "#", L))
    secs = []
    for L in letters:
        rows = []
        for d in groups[L]:
            url = d["envelope"]["sourceURL"]
            item_s, date_s = dispo_meta(d)
            kind = "PDF" if url.lower().endswith(".pdf") else "Page"
            rows.append(f'<li data-k="{e(d["title"] + " " + item_s)}"><a href="{e(url)}" rel="noopener">'
                        f'<span class="d-m">{e(d["title"])}</span><span class="d-s">{e(item_s)}</span>'
                        f'<span class="d-r num">{e(date_s)}</span><span class="d-x">{kind}{I_EXT}</span></a></li>')
        secs.append(f'<section class="dg" data-group id="l-{"num" if L == "#" else L}"><h2 class="dg-h">{L}</h2><ul class="dense dense-c">{"".join(rows)}</ul></section>')
    si_rows = "".join(
        f'<li data-k="{e(s["displayName"] + " special issuance")}"><a href="{e(s["envelope"]["sourceURL"])}" rel="noopener">'
        f'<span class="d-m">{e(s["displayName"])}</span><span class="d-s">Special Issuance</span><span class="d-r"></span>'
        f'<span class="d-x">{"PDF" if s["envelope"]["sourceURL"].lower().endswith(".pdf") else "Page"}{I_EXT}</span></a></li>'
        for s in sorted(SI, key=lambda x: sort_key(x["displayName"])))
    crumb_html, crumb_ld = crumbs([("Home", "/"), ("FAA conditions", None)])
    title = "FAA Disposition Tables and Special Issuance Conditions, A to Z"
    desc = (f"All {len(DISPO)} FAA AME Guide disposition tables and {len(SI)} Special Issuance conditions, each linked straight "
            "to the FAA document, with its exam item number and the FAA's date where the FAA gives one. Free, no account.")
    body = tool_band(filter_bar("cl", "cl-none", "Filter FAA conditions by name or exam item", "Filter by condition or exam item", len(DISPO) + len(SI), "entries"))
    body += "\n" + head_block(crumb_html, "FAA conditions, A to Z",
                              "The FAA's own disposition tables from the Guide for Aviation Medical Examiners, plus the Special Issuance conditions the app tracks. Every row opens the FAA document itself. I link, I don't paraphrase.", checked_stamp(DISPO + SI, "row"))
    body += f"""
  <main class="v2-main" id="main">
    <div class="wrap wide">
      <div id="cl">
      {no_match('cl-none', 'Try another word from the condition’s name, or an exam item number.')}
      <section class="dg" data-group id="si"><h2 class="dg-h dg-h-l">Special Issuance conditions <span class="num">{len(SI)}</span></h2><p class="dg-note">Each opens the FAA’s page for it. More in my <a href="/special-issuance.html">FAA Special Issuance guide</a>.</p><ul class="dense dense-c">{si_rows}</ul></section>
      <h2 class="dg-h dg-h-l" id="tables">FAA disposition tables <span class="num">{len(DISPO)}</span></h2>
      {az_nav(letters)}
      {"".join(secs)}
      </div>
      <p class="fine">Titles, item numbers and dates are as the FAA publishes them. Links open faa.gov.</p>
      <p class="neutral">{NEUTRAL}</p>
      {app_line('cond', 'seo-conditions')}
    </div>
  </main>"""
    ld = {"@context": "https://schema.org", "@graph": [crumb_ld, {
        "@type": "CollectionPage", "name": title, "description": desc, "url": SITE + "/faa-conditions/",
        "numberOfItems": len(DISPO) + len(SI)}]}
    return page("/faa-conditions/index.html", title, desc, body, ld, "seo-conditions", "cond", max(x["envelope"]["lastVerified"] for x in DISPO + SI)[:10])

# ---------------------------------------------------------------- AMEs
STATES = {"AK": "Alaska", "AL": "Alabama", "AR": "Arkansas", "AZ": "Arizona", "CA": "California", "CO": "Colorado",
          "CT": "Connecticut", "DC": "District of Columbia", "DE": "Delaware", "FL": "Florida", "GA": "Georgia",
          "GU": "Guam", "HI": "Hawaii", "IA": "Iowa", "ID": "Idaho", "IL": "Illinois", "IN": "Indiana", "KS": "Kansas",
          "KY": "Kentucky", "LA": "Louisiana", "MA": "Massachusetts", "MD": "Maryland", "ME": "Maine",
          "MH": "Marshall Islands", "MI": "Michigan", "MN": "Minnesota", "MO": "Missouri",
          "MP": "Northern Mariana Islands", "MS": "Mississippi", "MT": "Montana", "NC": "North Carolina",
          "ND": "North Dakota", "NE": "Nebraska", "NH": "New Hampshire", "NJ": "New Jersey", "NM": "New Mexico",
          "NV": "Nevada", "NY": "New York", "OH": "Ohio", "OK": "Oklahoma", "OR": "Oregon", "PA": "Pennsylvania",
          "PR": "Puerto Rico", "RI": "Rhode Island", "SC": "South Carolina", "SD": "South Dakota", "TN": "Tennessee",
          "TX": "Texas", "UT": "Utah", "VA": "Virginia", "VI": "U.S. Virgin Islands", "VT": "Vermont",
          "WA": "Washington", "WI": "Wisconsin", "WV": "West Virginia", "WY": "Wyoming"}
LOC_RE = re.compile(r"^(.*?),\s*([A-Z]{2})(?:\s+\d{5}(?:-\d{4})?)?\s*$")
ame_by_state = collections.defaultdict(list)
ame_oddities = []
for a in AMES:
    mm = LOC_RE.match(a.get("location") or "")
    if not mm or mm.group(2) not in STATES:
        ame_oddities.append(a.get("location")); continue
    if not re.search(r"\d{5}", a["location"]):
        ame_oddities.append(a["location"])
    city = mm.group(1).strip()
    ame_by_state[mm.group(2)].append((city.title() if city.isupper() else city, a))
RETRIEVED = iso_nice(AMES[0]["envelope"]["lastVerified"])
LOCATOR = AMES[0]["envelope"]["sourceURL"]
def tel(p):
    d = re.sub(r"\D", "", p or "")
    return ("+1" + d) if len(d) == 10 else ("+" + d if d else "")
def state_slug(st): return slugify(STATES[st])

def ame_row(city, a):
    tags = [t for t in (a.get("examStyleIndicators") or []) if t != "HIMS-trained"]
    cls = " · ".join(tags)
    hims = bool(a.get("isHIMSTrained"))
    flags = ""
    if any(t.startswith("Class I,") for t in tags): flags += " data-c1"
    if "Senior AME" in tags: flags += " data-sr"
    if hims: flags += " data-h"
    k = f'{a["name"]} {a.get("clinicName") or ""} {city}' + (" hims" if hims else "")
    clinic = f'<span class="a-c">{e(a["clinicName"])}</span>' if a.get("clinicName") else ""
    ph = f'<a href="tel:{tel(a["phone"])}">{e(a["phone"])}</a>' if a.get("phone") else ""
    return (f'<tr data-k="{e(k)}" data-n="{e(sort_key(a["name"]))}" data-t="{e(sort_key(city))}"{flags}>'
            f'<th scope="row" class="a-n"><span class="a-nm">{e(a["name"])}</span>{clinic}</th>'
            f'<td class="a-t">{e(city)}</td><td class="a-p num">{ph}</td><td class="a-k">{e(cls)}</td>'
            f'<td class="a-h">{"HIMS" if hims else ""}</td></tr>')

def ame_state(st):
    rows = ame_by_state[st]; name = STATES[st]
    rows = sorted(rows, key=lambda r: (sort_key(r[0]), sort_key(r[1]["name"])))
    n = len(rows); towns = len({c.lower() for c, _ in rows})
    exam = "examiner" if n == 1 else "examiners"; town_w = "town" if towns == 1 else "towns"
    crumb_html, crumb_ld = crumbs([("Home", "/"), ("Find an AME", "/aviation-medical-examiners/"), (name, None)])
    title = f"Aviation Medical Examiners in {name} ({n} FAA AMEs)"
    desc = (f"{n} aviation medical examiner listings in {name} from the FAA Designee Locator, by town, with phone numbers, "
            f"classes examined, Senior AME and HIMS training. Free, no account.")
    body = tool_band(lookup_bar()) + "\n" + head_block(
        crumb_html, f"Aviation medical examiners in {e(name)}",
        f'{n} {exam} in {towns} {town_w}, from the <a href="{e(LOCATOR)}" rel="noopener">FAA Designee Locator</a>, retrieved {RETRIEVED}. Call the office to confirm details before you book.')
    body += f"""
  <main class="v2-main" id="main">
    <div class="wrap wide">
      <div class="ame-tools" role="search" aria-label="Filter examiners in {e(name)}">
        <div class="lk-field sm">{I_SEARCH}<label class="sr" for="aq">Filter examiners in {e(name)} by name, clinic, or town</label><input id="aq" type="search" autocomplete="off" spellcheck="false" placeholder="Name, clinic, or town"></div>
        <fieldset class="tg"><legend class="sr">Show only</legend>
          <label><input type="checkbox" value="c1"><span>Class I</span></label>
          <label><input type="checkbox" value="sr"><span>Senior AME</span></label>
          <label><input type="checkbox" value="h"><span>HIMS</span></label>
        </fieldset>
        <p class="lk-count" id="acount" aria-live="polite">{n} {exam}</p>
      </div>
      <p id="anone" class="empty" hidden><b>No examiner matches.</b> Clear a filter, try a nearby town, or <a href="/aviation-medical-examiners/">pick another state</a>.</p>
      <table class="ame-t">
        <caption class="sr">Aviation medical examiners in {e(name)}, from the FAA Designee Locator</caption>
        <thead><tr><th scope="col" aria-sort="none"><button type="button" data-sort="n">Name</button></th><th scope="col" aria-sort="ascending"><button type="button" data-sort="t">Town</button></th><th scope="col">Phone</th><th scope="col">Classes</th><th scope="col">HIMS</th></tr></thead>
        <tbody>{"".join(ame_row(c, a) for c, a in rows)}</tbody>
      </table>
      <p class="fine">Names, clinics, towns, phone numbers, classes and HIMS training are as the FAA Designee Locator lists them. I leave out street and email addresses.</p>
      {app_line('ame', 'seo-ame')}
      <p class="fine"><a href="/aviation-medical-examiners/">All states and territories</a></p>
    </div>
  </main>"""
    ld = {"@context": "https://schema.org", "@graph": [crumb_ld, {
        "@type": "CollectionPage", "name": title, "description": desc,
        "url": f"{SITE}/aviation-medical-examiners/{state_slug(st)}.html",
        "isBasedOn": {"@type": "WebPage", "name": "FAA Designee Locator", "url": LOCATOR}, "numberOfItems": n}]}
    return page(f"/aviation-medical-examiners/{state_slug(st)}.html", title, desc, body, ld, "seo-ame", "ame", AMES[0]["envelope"]["lastVerified"][:10])

def ame_index():
    total = sum(len(v) for v in ame_by_state.values())
    hims = sum(1 for v in ame_by_state.values() for _, a in v if a.get("isHIMSTrained"))
    rows = "".join(
        f'<li data-k="{e(STATES[st] + " " + st)}"><a href="/aviation-medical-examiners/{state_slug(st)}.html">'
        f'<span class="d-m">{e(STATES[st])}</span><span class="d-r num">{len(ame_by_state[st])}</span></a></li>'
        for st in sorted(ame_by_state, key=lambda s: STATES[s]))
    crumb_html, crumb_ld = crumbs([("Home", "/"), ("Find an AME", None)])
    title = f"Find an Aviation Medical Examiner (AME) by State: {total:,} FAA Listings"
    desc = (f"{total:,} aviation medical examiner listings from the FAA Designee Locator, by state and town, with phone numbers, "
            "classes examined, Senior AME and HIMS training. Free, no account.")
    body = tool_band(lookup_bar("Town, medication, or condition")) + "\n" + head_block(
        crumb_html, "Find an aviation medical examiner",
        f'{total:,} examiner listings, {hims} of them HIMS-trained, from the <a href="{e(LOCATOR)}" rel="noopener">FAA Designee Locator</a>, retrieved {RETRIEVED}. Type a town above, or pick a state.')
    body += f"""
  <main class="v2-main" id="main">
    <div class="wrap wide">
      <h2 class="dg-h dg-h-l">States and territories <span class="num">{len(ame_by_state)}</span></h2>
      <ul class="dense dense-cols">{rows}</ul>
      <p class="fine">I leave out street and email addresses.</p>
      {app_line('ame', 'seo-ame-index')}
    </div>
  </main>"""
    ld = {"@context": "https://schema.org", "@graph": [crumb_ld, {
        "@type": "CollectionPage", "name": title, "description": desc, "url": SITE + "/aviation-medical-examiners/",
        "isBasedOn": {"@type": "WebPage", "name": "FAA Designee Locator", "url": LOCATOR}, "numberOfItems": total}]}
    return page("/aviation-medical-examiners/index.html", title, desc, body, ld, "seo-ame", "ame", AMES[0]["envelope"]["lastVerified"][:10]), total, hims

# ---------------------------------------------------------------- lookup index + JS
def write_index():
    m = [[x["genericName"], ", ".join(x.get("brandNames") or []), slugs[x["genericName"]]]
         for x in sorted(MEDS, key=lambda x: sort_key(x["genericName"]))]
    c = []
    for d in sorted(DISPO, key=lambda x: sort_key(x["title"])):
        item_s, _ = dispo_meta(d)
        c.append([d["title"], item_s or "FAA disposition table", d["envelope"]["sourceURL"].replace("https://www.faa.gov/", "")])
    for s in sorted(SI, key=lambda x: sort_key(x["displayName"])):
        c.append([s["displayName"], "Special Issuance", s["envelope"]["sourceURL"].replace("https://www.faa.gov/", "")])
    cnt = collections.Counter()
    for st, v in ame_by_state.items():
        for city, _ in v:
            cnt[(city, st)] += 1
    t = [[cty, st, state_slug(st), n] for (cty, st), n in sorted(cnt.items())]
    p = os.path.join(OUT, "faa-lookup-index.json")
    with open(p, "w", encoding="utf-8") as f:
        json.dump({"v": V, "m": m, "c": c, "t": t}, f, ensure_ascii=False, separators=(",", ":"))


def minify(src, dst, css=False):
    """Tiny, safe minifier for our own two files: drop /* */ comments and indentation."""
    t = open(os.path.join(HERE, src), encoding="utf-8").read()
    t = re.sub(r"/\*[\s\S]*?\*/", "", t)
    t = "\n".join(l.strip() for l in t.splitlines() if l.strip())
    if css:
        t = re.sub(r"\s*([{};,>])\s*", r"\1", t).replace(";}", "}")
    open(os.path.join(OUT, dst), "w", encoding="utf-8").write(t + "\n")

def write_assets():
    minify("faa-lookup.src.js", "faa-lookup.js")
    minify("site-v2.src.css", "site-v2.css", css=True)

# ---------------------------------------------------------------- homepage
def home_section(ame_total):
    return f"""
  <!-- FREE FAA LOOKUPS (preview 2026-11-14): generated by sitegen/gen_faa_pages.py -->
  <section class="lookup-home" id="lookups" aria-labelledby="lookups-h">
    <div class="wrap">
      <h2 id="lookups-h">Free FAA lookups. No account.</h2>
      {lookup_bar()}
      <p class="lk-links"><a href="/faa-medications/"><span class="num">{len(MEDS)}</span> medications</a><span aria-hidden="true">·</span><a href="/faa-conditions/#tables"><span class="num">{len(DISPO)}</span> FAA tables</a><span aria-hidden="true">·</span><a href="/faa-conditions/#si"><span class="num">{len(SI)}</span> Special Issuance conditions</a><span aria-hidden="true">·</span><a href="/aviation-medical-examiners/"><span class="num">{ame_total:,}</span> examiners</a></p>
      <p class="lk-links lk-plain"><a href="/faa-medications/">Medications</a><span aria-hidden="true">|</span><a href="/faa-conditions/">Conditions</a><span aria-hidden="true">|</span><a href="/aviation-medical-examiners/">Find an AME</a><span aria-hidden="true">|</span><a href="/lookups.html">All free lookups &rarr;</a></p>
    </div>
  </section>
"""

def patch_home(section):
    p = os.path.join(OUT, "index.html")
    s = open(p, encoding="utf-8").read()
    s = re.sub(r"\n  <!-- FREE FAA LOOKUPS[\s\S]*?</section>\n", "\n", s)  # idempotent
    s = re.sub(r'<link rel="stylesheet" href="/site-v2\.css\?v=[^"]*">\n', "", s)
    s = re.sub(r'<script defer src="/faa-lookup\.js\?v=[^"]*"></script>\n', "", s)
    s = s.replace("</head>", f'<link rel="stylesheet" href="/site-v2.css?v={V}">\n<script defer src="/faa-lookup.js?v={V}"></script>\n</head>', 1)
    if '<body class="v2 v2-home">' not in s:
        s = s.replace("<body>", '<body class="v2 v2-home">', 1)
    anchor = "  <!-- PRIVACY -->"  # reorg 11/25: the strip sits between Three jobs and Privacy
    assert anchor in s, "homepage anchor missing"
    s = s.replace(anchor, section.lstrip("\n") + "\n" + anchor, 1)
    s = re.sub(r"\n{3,}(  <!-- (?:FREE FAA LOOKUPS|PRIVACY))", r"\n\n\1", s)  # idempotent: no blank lines pile up between runs
    if "/faa-medications/" not in s.split("<footer>")[1]:
        s = s.replace("<p>Not affiliated with or endorsed by the FAA.</p>",
                      "<p>Not affiliated with or endorsed by the FAA.</p>\n      " + FOOT_LOOKUPS, 1)
    open(p, "w", encoding="utf-8").write(s)

def patch_lookups():
    """/lookups.html: the search bar plus one card per lookup index, each card's text taken from that
    index page's own h1 and meta description (so counts and wording stay in step with the pages)."""
    p = os.path.join(OUT, "lookups.html")
    if not os.path.exists(p):
        return
    s = open(p, encoding="utf-8").read()
    cards = []
    ame_total = sum(len(v) for v in ame_by_state.values())
    # Ryan 11/27: short titles and a count on each card; the description is the index page's own meta description.
    for href, f, title, count in (("/faa-medications/", "faa-medications/index.html", "Medications", f'<span class="num">{len(MEDS)}</span> medications'),
                                  ("/faa-conditions/", "faa-conditions/index.html", "Conditions and disposition tables",
                                   f'<span class="num">{len(DISPO)}</span> FAA tables · <span class="num">{len(SI)}</span> Special Issuance conditions'),
                                  ("/aviation-medical-examiners/", "aviation-medical-examiners/index.html", "Find an AME", f'<span class="num">{ame_total:,}</span> examiner listings')):
        doc = open(os.path.join(OUT, f), encoding="utf-8").read()
        desc = re.search(r'<meta name="description" content="([^"]*)"', doc).group(1)
        cards.append(f'        <a class="gcard" href="{href}"><h3>{title}</h3><p class="gcard-count">{count}</p><p>{desc}</p><span class="gcard-go">Open &rarr;</span></a>')
    block = ("  <!-- LOOKUP CARDS: generated by scripts/gen_faa_pages.py -->\n      " + lookup_bar() +
             '\n      <div class="gcards lk-cards">\n' + "\n".join(cards) + "\n      </div>\n  <!-- /LOOKUP CARDS -->")
    s = re.sub(r"  <!-- LOOKUP CARDS[\s\S]*?<!-- /LOOKUP CARDS -->", lambda m: block, s, count=1)
    s = re.sub(r'<link rel="stylesheet" href="/site-v2\.css\?v=[^"]*">\n', "", s)
    s = re.sub(r'<script defer src="/faa-lookup\.js\?v=[^"]*"></script>\n', "", s)
    s = s.replace("</head>", f'<link rel="stylesheet" href="/site-v2.css?v={V}">\n<script defer src="/faa-lookup.js?v={V}"></script>\n</head>', 1)
    open(p, "w", encoding="utf-8").write(s)

def sitemap(urls):
    p = os.path.join(OUT, "sitemap.xml")
    s = open(p, encoding="utf-8").read()
    s = re.sub(r"\s*<!-- FAA lookups -->[\s\S]*?<!-- /FAA lookups -->", "", s)
    block = "\n  <!-- FAA lookups -->\n" + "".join(
        f"  <url>\n    <loc>{u}</loc>\n    <lastmod>{lm}</lastmod>\n    <changefreq>monthly</changefreq>\n    <priority>{pr}</priority>\n  </url>\n"
        for (u, lm), pr in urls) + "  <!-- /FAA lookups -->\n"
    open(p, "w", encoding="utf-8").write(s.replace("</urlset>", block + "</urlset>"))

# ---------------------------------------------------------------- check (CI)
def check():
    """Every medication page's FAA text block must equal the JSON prose, verbatim."""
    bad = 0
    for m in MEDS:
        p = os.path.join(OUT, "faa-medications", slugs[m["genericName"]] + ".html")
        try:
            doc = open(p, encoding="utf-8").read()
        except FileNotFoundError:
            print("MISSING", p); bad += 1; continue
        blk = re.search(r'<section class="faa-text"[^>]*>\n([\s\S]*?)\n        </section>', doc)
        want = prose(m["faaStatusDescription"]) + ("\n" + prose(own_note(m["informationalNote"])) if m.get("informationalNote") else "")
        if not blk or blk.group(1) != want:
            print("DIFFERS", m["genericName"]); bad += 1
    print(f"check: {len(MEDS) - bad} of {len(MEDS)} medication pages match the JSON exactly")
    return 1 if bad else 0

def main():
    if args.check:
        sys.exit(check())
    for d in ("faa-medications", "faa-conditions", "aviation-medical-examiners"):
        shutil.rmtree(os.path.join(OUT, d), ignore_errors=True)
    urls = [(med_index(), "0.8")]
    urls += [(med_page(m), "0.6") for m in MEDS]
    urls.append((cond_index(), "0.8"))
    url, total, hims = ame_index()
    urls.append((url, "0.8"))
    urls += [(ame_state(st), "0.6") for st in sorted(ame_by_state)]
    write_index()
    write_assets()
    patch_home(home_section(total))
    patch_lookups()
    sitemap(urls)
    print(f"meds {len(MEDS)}, conditions 1 ({len(DISPO)} tables, {len(SI)} SI), AME index + {len(ame_by_state)} states "
          f"({total} listings), sitemap +{len(urls)} urls")
    if ame_oddities:
        print("AME location oddities:", ame_oddities)

if __name__ == "__main__":
    main()
