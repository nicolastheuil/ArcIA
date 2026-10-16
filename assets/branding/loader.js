/**
 * ArcIA Enterprise Agentic Platform — UI Brand Injector
 * Dynamically enforces the ArcIA brand identity, logos, titles, and styles across Open-WebUI.
 */
(function () {
  'use strict';

  var BRAND_TITLE = 'ArcIA — Enterprise Agentic Platform';
  var BRAND_NAME = 'ArcIA';

  function applyArcIABranding() {
    // 1. Maintain document title
    if (document.title.includes('Open WebUI') || document.title === 'ArcIA (Open WebUI)') {
      document.title = BRAND_TITLE;
    }

    // 2. Enforce official ArcIA Squircle Favicon
    var favicons = document.querySelectorAll("link[rel*='icon']");
    favicons.forEach(function (link) {
      if (!link.href.includes('/static/favicon.svg')) {
        link.href = '/static/favicon.svg';
        link.type = 'image/svg+xml';
      }
    });

    // 3. Replace all default logos / splashes with official ArcIA SVG
    var images = document.querySelectorAll('img');
    images.forEach(function (img) {
      var src = img.getAttribute('src') || '';
      var alt = img.getAttribute('alt') || '';

      if (
        src.includes('splash') ||
        src.includes('logo.png') ||
        alt.toLowerCase().includes('open webui') ||
        img.id === 'logo' ||
        img.id === 'logo-her'
      ) {
        if (img.src !== window.location.origin + '/static/logo.svg') {
          img.src = '/static/logo.svg';
          img.style.maxHeight = '48px';
          img.style.width = 'auto';
        }
      } else if (src.includes('favicon.png') || src.includes('favicon-96x96.png')) {
        if (img.src !== window.location.origin + '/static/favicon.svg') {
          img.src = '/static/favicon.svg';
        }
      }
    });

    // 4. Clean up brand text in DOM nodes
    var targets = document.querySelectorAll('h1, h2, span, a, div.text-2xl, div.font-semibold');
    targets.forEach(function (el) {
      if (el.childNodes.length === 1 && el.childNodes[0].nodeType === 3) {
        var text = el.textContent.trim();
        if (text === 'Open WebUI' || text === 'ArcIA (Open WebUI)') {
          el.textContent = BRAND_NAME;
        }
      }
    });
  }

  // Initial execution
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', applyArcIABranding);
  } else {
    applyArcIABranding();
  }

  // Continuous DOM observation for SPA navigation & dynamic components
  var observer = new MutationObserver(function () {
    applyArcIABranding();
  });

  if (document.documentElement) {
    observer.observe(document.documentElement, {
      childList: true,
      subtree: true
    });
  }
})();
