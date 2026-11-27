"""Strip analytics from a PREVIEW COPY of the site (never the repo itself) before a QA deploy (11/27).
Every page carries the Google Ads tag and the Cloudflare Web Analytics beacon, so QA page loads on a
preview count as real visits. Usage: copy the site to a scratch dir (rsync, excluding .git and scripts/),
then: python3 -I scripts/strip-preview-analytics.py <copy-dir>; rm <copy-dir>/ads-conversion.js;
grep -rlE "googletagmanager|gtag[(]|cloudflareinsights|ads-conversion" <copy-dir> must print nothing."""
import re, sys, pathlib
root = pathlib.Path(sys.argv[1])
pat = re.compile(r'[ \t]*<script\b([^>]*)>(.*?)</script>[ \t]*\n?', re.S | re.I)
bad_src = re.compile(r'googletagmanager|ads-conversion|cloudflareinsights', re.I)
bad_body = re.compile(r'gtag\(|dataLayer')
comment = re.compile(r'[ \t]*<!-- Cloudflare Web Analytics[^>]*-->[ \t]*\n?')
n_files = n_rm = 0
for p in root.rglob('*.html'):
    s = p.read_text(encoding='utf-8')
    def repl(m):
        global n_rm
        attrs, body = m.group(1), m.group(2)
        if bad_src.search(attrs) or bad_body.search(body):
            n_rm += 1
            return ''
        return m.group(0)
    t = pat.sub(repl, s)
    t = comment.sub('', t)
    if t != s:
        p.write_text(t, encoding='utf-8'); n_files += 1
print(n_files, 'files changed,', n_rm, 'script blocks removed')
