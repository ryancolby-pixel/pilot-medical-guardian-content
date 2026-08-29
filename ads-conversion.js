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
    if (!cameFromGoogleAd()) return;
    var links = document.querySelectorAll('a[href*="apps.apple.com"]');
    for (var i = 0; i < links.length; i++) {
      var a = links[i];
      try {
        var u = new URL(a.href);
        if (!u.searchParams.get('ct')) continue;   // no token to replace, leave it alone
        u.searchParams.set('ct', AD_CT);
        a.href = u.toString();
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
