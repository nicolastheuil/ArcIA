/**
 * ArcIA Enterprise Agentic Platform — UI Brand Injector
 * Dynamically enforces the official ArcIA brand identity, logos, titles, and styles across Open-WebUI.
 */
(function () {
  'use strict';

  var BRAND_TITLE = 'ArcIA — Enterprise Agentic Platform';
  var BRAND_NAME = 'ArcIA';

  // 2. Recursive text node cleaner (strips "(Open WebUI)" everywhere)
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
    } catch (e) {}
  }

  // 3. Center Hero Logo (Official aIA Monogram in the middle of empty chat)
  function ensureCenterHeroLogo() {
    var hasMessages = document.querySelector('[data-message-id]') ||
                      document.querySelector('.chat-message') ||
                      document.querySelector('.message-bubble') ||
                      document.querySelector('div:has(> .prose):not(#arcia-center-hero *)');

    var hero = document.getElementById('arcia-center-hero');

    if (hasMessages) {
      if (hero) hero.remove();
      return;
    }

    var centerTarget = null;
    var modelTitle = document.querySelector('.text-2xl, [class*="text-2xl"]');
    if (modelTitle) {
      var row = modelTitle.closest('.flex-row') || modelTitle.closest('div.w-fit');
      if (row) {
        centerTarget = row;
      }
    }

    if (!centerTarget) {
      var emptyCol = document.querySelector('div[class*="translate-y-6"] div.flex-col.items-center');
      if (emptyCol) {
        centerTarget = emptyCol.firstElementChild;
      }
    }

    if (!centerTarget) {
      var textarea = document.querySelector('textarea');
      if (textarea) {
        var form = textarea.closest('form');
        if (form) {
          centerTarget = form;
        }
      }
    }

    if (!centerTarget || !centerTarget.parentElement) return;

    if (!hero) {
      hero = document.createElement('div');
      hero.id = 'arcia-center-hero';
      hero.style.cssText = 'display:flex; flex-direction:column; align-items:center; justify-content:center; margin-bottom:24px; width:100%; text-align:center; user-select:none;';
      hero.innerHTML = `
        <div style="display:flex; flex-direction:column; align-items:center; justify-content:center; pointer-events:auto;">
          <div style="position:relative; width:88px; height:88px; margin-bottom:14px;">
            <img src="/static/favicon.svg" alt="ArcIA" style="width:88px; height:88px; filter: drop-shadow(0 0 28px rgba(107, 231, 221, 0.45)); cursor:pointer; transition: transform 0.25s cubic-bezier(0.16, 1, 0.3, 1);" onmouseover="this.style.transform='scale(1.06)'" onmouseout="this.style.transform='scale(1)'" />
          </div>
          <div style="font-family:'Montserrat', system-ui, sans-serif; font-size:30px; font-weight:800; color:#f8fafc; letter-spacing:-0.5px; margin-bottom:4px; text-shadow:0 2px 14px rgba(0,0,0,0.7);">
            ArcIA
          </div>
          <div style="font-family:'Montserrat', system-ui, sans-serif; font-size:11px; font-weight:700; color:#6be7dd; letter-spacing:2.5px; text-transform:uppercase;">
            Plateforme IA Agentique Souveraine
          </div>
        </div>
      `;

      centerTarget.parentElement.insertBefore(hero, centerTarget);
    } else {
      hero.style.display = 'flex';
      if (!hero.parentElement) {
        centerTarget.parentElement.insertBefore(hero, centerTarget);
      }
    }
  }

  // 6. Global Brand Applicator
  function applyArcIABranding() {
    // A. Enforce Document Title
    if (document.title.includes('Open WebUI') || document.title === 'ArcIA (Open WebUI)') {
      document.title = BRAND_TITLE;
    }

    // B. Enforce Favicon
    var favicons = document.querySelectorAll("link[rel*='icon']");
    favicons.forEach(function (link) {
      if (!link.href.includes('/static/favicon.svg')) {
        link.href = '/static/favicon.svg';
        link.type = 'image/svg+xml';
      }
    });

    // C. Replace default logos/splashes with ArcIA SVG
    document.querySelectorAll('img').forEach(function (img) {
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
      }
    });

    // D. Inject Center Hero Logo (aIA in the middle)
    ensureCenterHeroLogo();


    // F. Sanitize Text in the DOM
    sanitizeTextNodes(document.body || document.documentElement);

    // G. Hide Update Banner
    document.querySelectorAll('a[href*="github.com/open-webui/open-webui/releases"]').forEach(function (el) {
      var container = el.closest('div.fixed, div.toast, div[class*="bottom-"]');
      if (container) container.style.display = 'none';
    });
  }


  // Initial Execution
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', applyArcIABranding);
  } else {
    applyArcIABranding();
  }

  // Continuous Observer for SvelteKit Dynamic Components
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
