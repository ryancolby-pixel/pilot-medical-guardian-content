/* Google Ads conversion: outbound click on an App Store link.
 *
 * WHY THIS EXISTS
 * A website tag cannot see App Store installs. Apple passes nothing back to Google. The only
 * thing this site can measure is the moment a visitor leaves for the App Store, so that click
 * is the conversion. Treat it as "reached the store", never as "installed".
 *
 * THE ONLY THING TO EDIT IS SEND_TO, one line below.
 * Google Ads -> Goals -> Conversions -> Summary -> New conversion action -> Website,
 * then open the action -> Tag setup -> Use Google tag -> "Event snippet". The value you want
 * is the send_to string, which looks like 'AW-18408761824/AbC-D_efGhIjKlMnOp'. Keep the AW- part.
 *
 * Until SEND_TO is filled in, this file does nothing at all: links behave exactly as if it
 * were not here, and a click logs one console warning so a test click tells you it is unset.
 *
 * SAFETY: navigation must never depend on Google. Every path either navigates immediately or
 * is covered by the timeout below, and a throw anywhere sends the visitor on their way.
 */
(function () {
  'use strict';

  var SEND_TO = 'AW-18408761824/jdRECKrRhuocEODT_clE';

  // How long to wait for Google before giving up and navigating anyway.
  var MAX_WAIT_MS = 900;

  /* ------------------------------------------------------------------ *
   * Tell App Store Connect that this visitor came from a Google ad.
   *
   * Every App Store link on the site carries a per-page ct token, like
   * ct=web-home or ct=seo-duration, which is how ASC Campaigns groups
   * downloads. A visitor arriving from a Google ad lands on one of those
   * same pages, so without this their download is filed under the page
   * token and is indistinguishable from organic website traffic.
   *
   * Google appends gclid to an ad click (gbraid/wbraid on some iOS
   * traffic). If one is present, or was present earlier this session,
   * rewrite the ct on outbound App Store links so ASC files the download
   * separately. pt is never touched: without it ASC collects nothing.
   * ------------------------------------------------------------------ */
  var AD_CT = 'google-ads';
  var AD_FLAG = 'pmg_from_google_ad';
  var SRC_FLAG = 'pmg_src_ct';

  // Organic search referrers. A visitor arriving from one of these typed a query and chose us.
  var SEARCH_HOST = /(^|\.)(google|bing|duckduckgo|yahoo|ecosia|brave|startpage|qwant|yandex|baidu)\./i;

  function qparam(name) {
    try {
      return new URL(window.location.href).searchParams.get(name);
    } catch (e) { return null; }
  }

  // ASC campaign tokens are short and plain. Keep to lowercase alphanumerics and hyphens.
  function slug(v) {
    return String(v).toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 24);
  }

  function arrivedFromSearch() {
    try {
      if (!document.referrer) return false;
      var r = new URL(document.referrer);
      if (r.hostname === window.location.hostname) return false;   // internal navigation
      return SEARCH_HOST.test(r.hostname);
    } catch (e) { return false; }
  }

  function remember(v) { try { sessionStorage.setItem(SRC_FLAG, v); } catch (e) {} }
  function recall() { try { return sessionStorage.getItem(SRC_FLAG); } catch (e) { return null; } }

  /* Decide what this visitor's ct should be, given the token the page author wrote.
   *
   * Precedence, highest first:
   *   1. Google ad (gclid/gbraid/wbraid)  -> 'google-ads'
   *   2. utm_source on the landing URL    -> 'web-<source>'   e.g. web-linkedin
   *   3. Arrived from an organic search   -> flip 'web-' to 'seo-'
   *   4. Anything else                    -> the authored token, untouched
   *
   * Case 3 is the point of this: pages the SEO cluster targets are already authored 'seo-*',
   * so they are correct either way. The homepage is authored 'web-home', and a search visitor
   * landing there was previously indistinguishable from a bookmark or a direct visit.
   *
   * The decision is remembered for the session, because a visitor may land on one page, browse
   * to another, and click there - at which point document.referrer is our own host.
   */
  function retagToken(authored) {
    if (cameFromGoogleAd()) return AD_CT;

    var remembered = recall();
    var utm = qparam('utm_source');

    if (utm) {
      var t = 'web-' + slug(utm);
      remember(t);
      return t;
    }
    if (arrivedFromSearch()) {
      remember('search');
      return authored.replace(/^web-/, 'seo-');
    }
    if (remembered === 'search') return authored.replace(/^web-/, 'seo-');
    if (remembered) return remembered;
    return authored;
  }

  function cameFromGoogleAd() {
    try {
      var q = window.location.search;
      if (/[?&](gclid|gbraid|wbraid)=/.test(q)) {
        try { sessionStorage.setItem(AD_FLAG, '1'); } catch (e) {}
        return true;
      }
      return sessionStorage.getItem(AD_FLAG) === '1';
    } catch (e) {
      // Private mode can throw on sessionStorage. Fall back to this page only.
      return /[?&](gclid|gbraid|wbraid)=/.test(window.location.search);
    }
  }

  function retagAppStoreLinks() {
    var links = document.querySelectorAll('a[href*="apps.apple.com"]');
    for (var i = 0; i < links.length; i++) {
      var a = links[i];
      try {
        var u = new URL(a.href);
        var authored = u.searchParams.get('ct');
        if (!authored) continue;                   // no token to replace, leave it alone
        var next = retagToken(authored);
        if (!next || next === authored) continue;  // nothing to change
        u.searchParams.set('ct', next);
        a.href = u.toString();                     // pt is never touched
      } catch (e) { /* leave the link exactly as authored */ }
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', retagAppStoreLinks);
  } else {
    retagAppStoreLinks();
  }

  function appStoreLink(node) {
    var a = node && node.closest ? node.closest('a') : null;
    if (!a || !a.href) return null;
    return a.hostname === 'apps.apple.com' ? a : null;
  }

  document.addEventListener('click', function (e) {
    var a = appStoreLink(e.target);
    if (!a) return;
    if (e.defaultPrevented) return;
    if (typeof window.gtag !== 'function') return;   // tag blocked or still loading: leave the link alone

    // Modifier click or middle click opens a new tab. This page is not going away, so record it
    // and do not touch navigation.
    var newTab = e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey;

    if (!SEND_TO) {
      if (window.console && console.warn) {
        console.warn('[pmg] App Store click not counted: SEND_TO is empty in /ads-conversion.js');
      }
      return;
    }

    if (newTab) {
      try { window.gtag('event', 'conversion', { send_to: SEND_TO }); } catch (err) {}
      return;
    }

    var url = a.href;
    var navigated = false;
    function go() {
      if (navigated) return;
      navigated = true;
      window.location.href = url;
    }

    try {
      e.preventDefault();
      window.gtag('event', 'conversion', { send_to: SEND_TO, event_callback: go });
      window.setTimeout(go, MAX_WAIT_MS);
    } catch (err) {
      go();
    }
  }, true);
})();
