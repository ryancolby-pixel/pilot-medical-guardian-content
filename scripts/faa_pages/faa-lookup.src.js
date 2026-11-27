/* faa-lookup.js: one small shared script for the free FAA lookups.
   - [data-lookup]  global lookup (medications, FAA conditions, examiner towns);
                    loads /faa-lookup-index.json on first focus only.
   - [data-filter]  the same bar in list mode: filters the list below it.
   - table.ame-t    examiner table: text filter, toggles, sortable columns.
   - [data-copy]    copy-to-clipboard buttons.
   No framework, no storage, no network except the index file. */
(function () {
  'use strict';
  function norm(s) { return (s || '').toLowerCase().normalize('NFKD').replace(/[̀-ͯ]/g, '').replace(/[^a-z0-9]+/g, ' ').trim(); }
  function esc(s) { return String(s).replace(/[&<>"]/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]; }); }
  function cap(s) { return s.charAt(0).toUpperCase() + s.slice(1); }
  var hashQ = location.hash.indexOf('#q=') === 0 ? decodeURIComponent(location.hash.slice(3)) : (new URLSearchParams(location.search).get('q') || '');
  var reduce = window.matchMedia && matchMedia('(prefers-reduced-motion: reduce)').matches;

  /* ---------- global lookup ---------- */
  var IDX = null, P = null;
  function load(src) {
    if (!P) {
      P = fetch(src).then(function (r) { if (!r.ok) throw new Error(r.status); return r.json(); }).then(function (d) {
        ['m', 'c', 't'].forEach(function (g) { d[g].forEach(function (x) { x.k = norm(x[0] + ' ' + x[1]); }); });
        IDX = d; return d;
      });
      P.catch(function () { P = null; });
    }
    return P;
  }
  function rank(k, q, parts) {
    for (var i = 0; i < parts.length; i++) if (k.indexOf(parts[i]) < 0) return -1;
    if (k.indexOf(q) === 0) return 0;
    if ((' ' + k).indexOf(' ' + parts[0]) > -1) return 1;
    return 2;
  }
  function find(arr, q, n) {
    var parts = q.split(' '), out = [];
    for (var i = 0; i < arr.length; i++) { var r = rank(arr[i].k, q, parts); if (r >= 0) out.push([r, arr[i]]); }
    out.sort(function (a, b) { return a[0] - b[0] || a[1][0].length - b[1][0].length || (a[1][0] < b[1][0] ? -1 : 1); });
    return out.slice(0, n).map(function (x) { return x[1]; });
  }
  function opt(id, href, main, sub, ext) {
    return '<a role="option" id="lk-o' + id + '" href="' + esc(href) + '" tabindex="-1"' + (ext ? ' rel="noopener"' : '') + '>' +
      '<span class="lk-m">' + esc(main) + '</span><span class="lk-s">' + esc(sub) + '</span>' +
      (ext ? '<span class="lk-x" aria-label="opens faa.gov">faa.gov</span>' : '') + '</a>';
  }
  function Lookup(root) {
    var inp = root.querySelector('input'), pop = root.querySelector('.lk-pop'), st = root.querySelector('.lk-status');
    var src = root.getAttribute('data-lookup'), opts = [], act = -1, last = null;
    function open(b) { pop.hidden = !b; inp.setAttribute('aria-expanded', b ? 'true' : 'false'); root.classList.toggle('is-open', b); }
    function setAct(i) {
      if (act > -1 && opts[act]) opts[act].classList.remove('is-active');
      act = i;
      if (i > -1 && opts[i]) { opts[i].classList.add('is-active'); inp.setAttribute('aria-activedescendant', opts[i].id); opts[i].scrollIntoView({ block: 'nearest', behavior: reduce ? 'auto' : 'smooth' }); }
      else inp.removeAttribute('aria-activedescendant');
    }
    function render() {
      var q = norm(inp.value);
      if (q === last && IDX) return;
      if (!q) { last = q; open(false); pop.innerHTML = ''; opts = []; act = -1; st.textContent = ''; return; }
      if (!IDX) {
        pop.innerHTML = '<div class="lk-msg is-loading"><span class="lk-spin" aria-hidden="true"></span>Loading the lookup</div>';
        open(true);
        load(src).then(function () { last = null; render(); }, function () {
          pop.innerHTML = '<div class="lk-msg">The lookup did not load. Check your connection and try again.</div>';
        });
        return;
      }
      last = q;
      var G = [
        ['Medications', find(IDX.m, q, 6), function (x, n) { return opt(n, '/faa-medications/' + x[2] + '.html', cap(x[0]), x[1], false); }],
        ['FAA conditions', find(IDX.c, q, 5), function (x, n) { return opt(n, x[2].indexOf('http') === 0 ? x[2] : 'https://www.faa.gov/' + x[2], x[0], x[1], true); }],
        ['Examiners by town', find(IDX.t, q, 5), function (x, n) { return opt(n, '/aviation-medical-examiners/' + x[2] + '.html#q=' + encodeURIComponent(x[0]), x[0] + ', ' + x[1], x[3] + (x[3] === 1 ? ' examiner' : ' examiners'), false); }]
      ];
      var h = '', n = 0;
      G.forEach(function (g, gi) {
        if (!g[1].length) return;
        h += '<div role="group" aria-labelledby="lk-g' + gi + '"><div class="lk-gh" id="lk-g' + gi + '" role="presentation">' + g[0] + '</div>';
        g[1].forEach(function (x) { h += g[2](x, n++); });
        h += '</div>';
      });
      if (!n) h = '<div class="lk-msg"><b>No match for “' + esc(inp.value.trim()) + '”.</b> Try the generic name, one word from a condition, or a nearby town.</div>';
      pop.innerHTML = h;
      opts = [].slice.call(pop.querySelectorAll('[role=option]'));
      act = -1; open(true);
      st.textContent = n ? n + (n === 1 ? ' result' : ' results') : 'No results';
    }
    inp.addEventListener('focus', function () { load(src).catch(function () {}); if (inp.value) render(); }, { passive: true });
    inp.addEventListener('input', render);
    inp.addEventListener('keydown', function (e) {
      if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
        if (pop.hidden) render();
        if (!opts.length) return;
        e.preventDefault();
        var d = e.key === 'ArrowDown' ? 1 : -1;
        setAct(act < 0 ? (d > 0 ? 0 : opts.length - 1) : (act + d + opts.length) % opts.length);
      } else if (e.key === 'Enter') {
        var t = opts[act > -1 ? act : 0];
        if (t && !pop.hidden) { e.preventDefault(); location.href = t.href; }
        else if (!IDX) e.preventDefault();   /* index still loading: wait, don't submit */
      } else if (e.key === 'Escape') {
        if (!pop.hidden) { open(false); setAct(-1); } else { inp.value = ''; render(); }
      }
    });
    pop.addEventListener('mousedown', function (e) { e.preventDefault(); });
    inp.addEventListener('blur', function () { setTimeout(function () { open(false); setAct(-1); }, 120); });
  }
  /* "/" focuses the first search field on the page, unless typing in a field already. */
  document.addEventListener('keydown', function (e) {
    if (e.key !== '/' || e.metaKey || e.ctrlKey || e.altKey) return;
    var t = e.target, tag = t && t.tagName;
    if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT' || (t && t.isContentEditable)) return;
    var f = document.querySelector('.lk input, #aq');
    if (f) { e.preventDefault(); f.focus(); }
  });

  /* ---------- list filter (same bar, list mode) ---------- */
  function Filter(root) {
    var inp = root.querySelector('input'), box = document.getElementById(root.getAttribute('data-filter'));
    var rows = [].slice.call(box.querySelectorAll('[data-k]')), groups = [].slice.call(box.querySelectorAll('[data-group]'));
    var cnt = root.querySelector('.lk-count'), none = document.getElementById(root.getAttribute('data-empty'));
    var az = document.querySelector('.az'), total = rows.length, unit = cnt.getAttribute('data-unit');
    rows.forEach(function (r) { r._k = norm(r.getAttribute('data-k')); });
    function first() { return box.querySelector('[data-k]:not([hidden]) a'); }
    function run() {
      var q = norm(inp.value), parts = q ? q.split(' ') : [], n = 0;
      rows.forEach(function (r) { var ok = parts.every(function (p) { return r._k.indexOf(p) > -1; }); r.hidden = !ok; if (ok) n++; });
      groups.forEach(function (g) { g.hidden = !g.querySelector('[data-k]:not([hidden])'); });
      cnt.textContent = q ? n + ' of ' + total.toLocaleString() + ' ' + unit : total.toLocaleString() + ' ' + unit;
      if (none) { none.hidden = n > 0; var w = none.querySelector('[data-q]'); if (w) w.textContent = inp.value.trim(); }
      if (az) az.hidden = !!q;
    }
    inp.addEventListener('input', run);
    inp.addEventListener('keydown', function (e) {
      var f = first();
      if (e.key === 'Enter' && f && inp.value) { e.preventDefault(); location.href = f.href; }
      else if (e.key === 'ArrowDown' && f) { e.preventDefault(); f.focus(); }
      else if (e.key === 'Escape') { inp.value = ''; run(); }
    });
    box.addEventListener('keydown', function (e) {
      if (e.key !== 'ArrowDown' && e.key !== 'ArrowUp') return;
      var links = [].slice.call(box.querySelectorAll('[data-k]:not([hidden]) a')), i = links.indexOf(document.activeElement);
      if (i < 0) return;
      e.preventDefault();
      if (e.key === 'ArrowUp' && i === 0) { inp.focus(); return; }
      var t = links[i + (e.key === 'ArrowDown' ? 1 : -1)]; if (t) t.focus();
    });
    if (hashQ) { inp.value = hashQ; run(); }
  }

  /* ---------- examiner table ---------- */
  function Table(t) {
    var q = document.getElementById('aq'), boxes = [].slice.call(document.querySelectorAll('.ame-tools input[type=checkbox]'));
    var rows = [].slice.call(t.tBodies[0].rows), cnt = document.getElementById('acount'), none = document.getElementById('anone'), total = rows.length;
    rows.forEach(function (r) { r._k = norm(r.getAttribute('data-k')); });
    function run() {
      var v = norm(q.value), parts = v ? v.split(' ') : [], need = boxes.filter(function (b) { return b.checked; }).map(function (b) { return b.value; }), n = 0;
      rows.forEach(function (r) {
        var ok = parts.every(function (p) { return r._k.indexOf(p) > -1; }) && need.every(function (f) { return r.hasAttribute('data-' + f); });
        r.hidden = !ok; if (ok) n++;
      });
      cnt.textContent = (n === total ? '' : n + ' of ') + total + (total === 1 ? ' examiner' : ' examiners');
      none.hidden = n > 0; t.hidden = n === 0;
    }
    q.addEventListener('input', run);
    q.addEventListener('keydown', function (e) { if (e.key === 'Escape') { q.value = ''; run(); } });
    boxes.forEach(function (b) { b.addEventListener('change', run); });
    var ths = [].slice.call(t.tHead.rows[0].cells);
    ths.forEach(function (th) {
      var b = th.querySelector('button'); if (!b) return;
      b.addEventListener('click', function () {
        var key = b.getAttribute('data-sort'), dir = th.getAttribute('aria-sort') === 'ascending' ? -1 : 1;
        ths.forEach(function (o) { if (o.querySelector('button')) o.setAttribute('aria-sort', 'none'); });
        th.setAttribute('aria-sort', dir > 0 ? 'ascending' : 'descending');
        rows.sort(function (a, c) {
          var x = a.getAttribute('data-' + key), y = c.getAttribute('data-' + key);
          return (x < y ? -1 : x > y ? 1 : (a.getAttribute('data-n') < c.getAttribute('data-n') ? -1 : 1)) * dir;
        });
        rows.forEach(function (r) { t.tBodies[0].appendChild(r); });
      });
    });
    if (hashQ) { q.value = hashQ; run(); }
  }

  /* ---------- copy buttons ---------- */
  function Copy(b) {
    b.addEventListener('click', function () {
      var txt = b.getAttribute('data-copy'), lab = b.querySelector('.cp-l');
      function done() { b.classList.add('is-done'); lab.textContent = 'Copied'; setTimeout(function () { b.classList.remove('is-done'); lab.textContent = 'Copy'; }, 1600); }
      if (navigator.clipboard && window.isSecureContext) navigator.clipboard.writeText(txt).then(done, function () {});
      else { var r = document.createRange(), s = getSelection(), el = b.parentNode.querySelector('.mx-name'); r.selectNodeContents(el); s.removeAllRanges(); s.addRange(r); try { document.execCommand('copy'); done(); } catch (e) {} }
    });
  }

  [].forEach.call(document.querySelectorAll('[data-lookup]'), Lookup);
  [].forEach.call(document.querySelectorAll('[data-filter]'), Filter);
  [].forEach.call(document.querySelectorAll('table.ame-t'), Table);
  [].forEach.call(document.querySelectorAll('[data-copy]'), Copy);
})();

/* Sticky A to Z bar on phones: sit exactly under the sticky lookup band, whatever its real height.
   The same value clears the band when the skip link jumps to <main>. */
(function () {
  var band = document.querySelector(".tool-band");
  if (!band) return;
  function place() {
    var top = (parseFloat(getComputedStyle(band).top) || 0) + band.offsetHeight;
    document.documentElement.style.setProperty("--v-az-top", top + "px");
  }
  place();
  window.addEventListener("resize", place);
})();
