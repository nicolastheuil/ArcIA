/**
 * ArcIA Enterprise Agentic Platform — UI Brand Injector
 * Dynamically enforces the ArcIA brand identity, logos, titles, and styles across Open-WebUI.
 */
(function () {
  'use strict';

  var BRAND_TITLE = 'ArcIA — Enterprise Agentic Platform';
  var BRAND_NAME = 'ArcIA';

  function sanitizeTextNodes(root) {
    if (!root) return;
    try {
      var walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, null, false);
      var node;
      while ((node = walker.nextNode())) {
        var val = node.nodeValue;
        if (val && (val.includes('Open WebUI') || val.includes('(Open WebUI)'))) {
          node.nodeValue = val
            .replace(/ArcIA\s*\(Open WebUI\)/gi, BRAND_NAME)
            .replace(/\(Open WebUI\)/gi, '')
            .replace(/Open WebUI/gi, BRAND_NAME)
            .trim();
        }
      }
    } catch (e) {
      // Ignore walker errors
    }
  }

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
          img.style.maxHeight = '42px';
          img.style.width = 'auto';
        }
      } else if (src.includes('favicon.png') || src.includes('favicon-96x96.png')) {
        if (img.src !== window.location.origin + '/static/favicon.svg') {
          img.src = '/static/favicon.svg';
        }
      }
    });

    // 4. Sanitize text across all text nodes (removes "(Open WebUI)" in sidebar, titles, buttons)
    sanitizeTextNodes(document.body || document.documentElement);

    // 5. Hide any update banner notification
    document.querySelectorAll('a[href*="github.com/open-webui/open-webui/releases"]').forEach(function (el) {
      var container = el.closest('div.fixed, div.toast, div[class*="bottom-"]');
      if (container) {
        container.style.display = 'none';
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
