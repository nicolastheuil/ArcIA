/**
 * ArcIA Enterprise Agentic Platform — UI Brand Injector
 * Dynamically enforces the official ArcIA brand identity, logos, titles, and styles across Open-WebUI.
 */
(function () {
  'use strict';

  var BRAND_TITLE = 'ArcIA — Enterprise Agentic Platform';
  var BRAND_NAME = 'ArcIA';

  var DEFAULT_MODEL_ICON = '/static/icon-model-default.svg';
  var LOCAL_MODEL_ICON = '/static/icon-model-local.svg';
  var ZDR_MODEL_ICON = '/static/icon-model-zdr.svg';

  // Dynamic model-to-icon mapping pushed by the Wizard
  var modelBrandingMap = {
    'simple/auto': ZDR_MODEL_ICON,
    'simple/free': ZDR_MODEL_ICON,
    'agentic/auto': ZDR_MODEL_ICON,
    'agentic/free': ZDR_MODEL_ICON,
    'agentic/expert': ZDR_MODEL_ICON
  };

  // 0. Load dynamic models branding config pushed by the Wizard
  function loadModelsBrandingConfig() {
    try {
      fetch('/static/models-branding.json')
        .then(function (res) {
          if (res.ok) return res.json();
          return null;
        })
        .then(function (data) {
          if (!data) return;
          if (data.models && typeof data.models === 'object') {
            for (var key in data.models) {
              if (data.models[key] && data.models[key].icon) {
                modelBrandingMap[key.toLowerCase()] = data.models[key].icon;
              }
            }
          }
          if (data.default_icon) DEFAULT_MODEL_ICON = data.default_icon;
          if (data.local_icon) LOCAL_MODEL_ICON = data.local_icon;
          if (data.zdr_icon) ZDR_MODEL_ICON = data.zdr_icon;
          replaceModelAvatars();
        })
        .catch(function () {});
    } catch (e) {}
  }

  function resolveModelIcon(modelId) {
    if (!modelId) return DEFAULT_MODEL_ICON;
    var id = String(modelId).trim().toLowerCase();
    if (modelBrandingMap[id]) return modelBrandingMap[id];
    // Check if local sovereign model (Ollama, vLLM, local endpoint)
    if (id.includes('ollama') || id.includes('vllm') || id.includes('local')) {
      return LOCAL_MODEL_ICON;
    }
    // Check if cloud model with ZDR (Zero Data Retention)
    if (id.startsWith('simple/') || id.startsWith('agentic/') || id.includes('openrouter') || id.includes(':free')) {
      return ZDR_MODEL_ICON;
    }
    return DEFAULT_MODEL_ICON;
  }

  // 1. Intercept window.fetch to natively enrich Open-WebUI model objects with official ArcIA icons
  try {
    var _nativeFetch = window.fetch;
    window.fetch = async function () {
      var res = await _nativeFetch.apply(this, arguments);
      try {
        var reqUrl = (typeof arguments[0] === 'string') ? arguments[0] : (arguments[0] && arguments[0].url) || '';
        if (reqUrl.includes('/api/models') || reqUrl.includes('/api/v1/models')) {
          var clone = res.clone();
          var data = await clone.json();
          var modified = false;

          var enrichModel = function (item) {
            if (!item) return;
            var mid = item.id || item.name;
            var targetIcon = resolveModelIcon(mid);
            if (!item.info) item.info = {};
            if (!item.info.meta) item.info.meta = {};
            item.info.meta.profile_image_url = targetIcon;
            item.profile_image_url = targetIcon;
            modified = true;
          };

          if (Array.isArray(data)) {
            data.forEach(enrichModel);
          } else if (data && Array.isArray(data.data)) {
            data.data.forEach(enrichModel);
          } else if (data && Array.isArray(data.models)) {
            data.models.forEach(enrichModel);
          }

          if (modified) {
            return new Response(JSON.stringify(data), {
              status: res.status,
              statusText: res.statusText,
              headers: res.headers
            });
          }
        }
      } catch (err) {}
      return res;
    };
  } catch (e) {}

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

  // 4. Helper to determine currently active model in the chat
  function getCurrentChatModel() {
    try {
      var sel = document.querySelector('button[aria-label*="model" i], button[id*="model" i]');
      if (sel && sel.textContent) {
        var t = sel.textContent.trim();
        if (t) return t;
      }
      var modelEl = document.querySelector('.text-2xl, [class*="text-2xl"]');
      if (modelEl && modelEl.textContent) {
        var name = modelEl.textContent.trim();
        if (name.includes('/') || name.includes('auto') || name.includes('free')) return name;
      }
    } catch (e) {}
    return 'simple/auto';
  }

  // 5. Replace model avatars (replaces Open-WebUI fallback "OI" and "01" badges with ArcIA SVG icons)
  function replaceModelAvatars() {
    var activeModel = getCurrentChatModel();
    var defaultActiveIcon = resolveModelIcon(activeModel);

    // A. Replace initials avatars with text "OI", "01", "O I", "OpenAI"
    document.querySelectorAll('div, button, span').forEach(function (el) {
      if (el.childNodes.length === 1 && el.childNodes[0].nodeType === 3) {
        var text = el.textContent.trim();
        if (/^(OI|01|O\s*I)$/i.test(text) && el.offsetWidth < 56 && el.offsetHeight < 56) {
          var row = el.closest('button, [role="menuitem"], div.flex');
          var modelIcon = defaultActiveIcon;
          if (row) {
            var rowText = (row.textContent || '').toLowerCase();
            for (var mKey in modelBrandingMap) {
              if (rowText.includes(mKey)) {
                modelIcon = modelBrandingMap[mKey];
                break;
              }
            }
          }
          el.style.backgroundImage = 'url("' + modelIcon + '")';
          el.style.backgroundRepeat = 'no-repeat';
          el.style.backgroundPosition = 'center';
          el.style.backgroundSize = 'contain';
          el.style.color = 'transparent';
          el.style.backgroundColor = 'transparent';
          el.style.border = 'none';
          el.setAttribute('data-arcia-model-icon', 'true');
        }
      }
    });

    // B. Replace image avatars in assistant messages or dropdowns that lack the proper icon
    document.querySelectorAll('img').forEach(function (img) {
      var src = img.getAttribute('src') || '';
      var alt = img.getAttribute('alt') || '';
      if (
        (src.includes('openai') || alt.toLowerCase().includes('openai') || src.includes('favicon.png')) &&
        !img.closest('#arcia-center-hero')
      ) {
        var row = img.closest('button, [role="menuitem"], div.flex');
        var targetIcon = defaultActiveIcon;
        if (row) {
          var rowText = (row.textContent || '').toLowerCase();
          for (var mKey in modelBrandingMap) {
            if (rowText.includes(mKey)) {
              targetIcon = modelBrandingMap[mKey];
              break;
            }
          }
        }
        if (img.src !== window.location.origin + targetIcon) {
          img.src = targetIcon;
        }
      }
    });
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
      } else if (src.includes('favicon.png') || src.includes('favicon-96x96.png')) {
        if (img.src !== window.location.origin + '/static/favicon.svg') {
          img.src = '/static/favicon.svg';
        }
      }

      if (!img.dataset.arciaBound) {
        img.dataset.arciaBound = 'true';
        img.addEventListener('error', function () {
          this.src = '/static/favicon.svg';
        });
      }
    });

    // D. Inject Center Hero Logo (aIA in the middle)
    ensureCenterHeroLogo();

    // E. Replace Model Avatar Badges (handles "OI" fallback and applies official icons)
    replaceModelAvatars();

    // F. Sanitize Text in the DOM
    sanitizeTextNodes(document.body || document.documentElement);

    // G. Hide Update Banner
    document.querySelectorAll('a[href*="github.com/open-webui/open-webui/releases"]').forEach(function (el) {
      var container = el.closest('div.fixed, div.toast, div[class*="bottom-"]');
      if (container) container.style.display = 'none';
    });
  }

  // Load models branding configuration
  loadModelsBrandingConfig();

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
