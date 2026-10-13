// Antigravity_App_TC DOM Localization Runtime
// Injected into dist/preload.js; runs in BrowserWindow preload context.
(() => {
  if (typeof globalThis === 'undefined' || globalThis.__agzhtw_loaded) return;
  globalThis.__agzhtw_loaded = true;

  const T = __TRANSLATIONS__;
  const P = __PATTERNS__;

  // Subtrees that must never be translated (AI markdown, user prompts, code editors, terminals, logs)
  const SKIP = [
    'pre', 'code', 'textarea', 'input', 'svg', 'canvas', 'script', 'style',
    '[contenteditable="true"]', '[data-lexical-editor]',
    '.monaco-editor', '.monaco-diff-editor', '.monaco-workbench', '.cm-editor', '.xterm',
    '.md-divider-spacing', '.markdown-frontmatter', '.katex',
    '[data-testid="user-input-step"]',
    '[data-testid="planner-response-text"]',
    '[data-testid="pending-user-messages"]',
    '[data-testid="side-question-question"]',
    '[data-testid="side-question-answer"]',
    '[data-testid="terminal-surface"]',
    '[data-testid="setup-script-output"]',
    '[data-testid="sidecar-logs-content"]',
    '.suggest-widget', '[data-translate="false"]', '.notranslate'
  ].join(',');

  // Keep reasoning effort levels in English
  const EFFORT_RE = /^(Low|Medium|High|Extra|Max)$/i;
  const EFFORT_CTX = [
    '[data-testid="model-selector-effort-option"]',
    '[data-testid="model-selector-effort-group"]',
    '[data-testid="model-selector-trigger"]',
    '[data-testid="model-selector-item"]'
  ].join(',');

  const ATTRS = ['placeholder', 'title', 'aria-label', 'data-tooltip-content'];
  const ATTR_SEL = ATTRS.map(a => '[' + a + ']').join(',');
  const MULTI_STATE = new WeakMap();

  function norm(s) {
    return s.indexOf('\u00a0') !== -1 ? s.replace(/\u00a0/g, ' ').trim() : s.trim();
  }

  function matchPatterns(s) {
    const k = s.slice(0, 3);
    const bucket = P.b[k];
    if (bucket) {
      for (let i = 0; i < bucket.length; i++) {
        const [re, rep] = bucket[i];
        if (re.test(s)) return s.replace(re, rep);
      }
    }
    const fb = P.f;
    for (let i = 0; i < fb.length; i++) {
      const [re, rep] = fb[i];
      if (re.test(s)) return s.replace(re, rep);
    }
    return null;
  }

  function tr(raw) {
    if (!raw || typeof raw !== 'string') return null;
    const s = norm(raw);
    if (!s || s.length < 2) return null;

    let hit = T[s];
    if (hit !== undefined) return hit;

    // Handle trailing colon or ellipsis fallback
    if (s.endsWith(':') && s.length > 2) {
      const base = T[s.slice(0, -1).trim()];
      if (base !== undefined) return base + '：';
    }
    if (s.endsWith('...') && s.length > 4) {
      const base = T[s.slice(0, -3).trim()];
      if (base !== undefined) return base + '...';
    }
    if (s.endsWith('…') && s.length > 2) {
      const base = T[s.slice(0, -1).trim()];
      if (base !== undefined) return base + '…';
    }

    return matchPatterns(s);
  }

  function translatePreservingBounds(raw) {
    if (!raw || raw.length < 2) return null;
    const out = tr(raw);
    if (out === null) return null;
    const leadMatch = raw.match(/^\s*/);
    const tailMatch = raw.match(/\s*$/);
    const lead = leadMatch ? leadMatch[0] : '';
    const tail = tailMatch ? tailMatch[0] : '';
    const next = lead + out + tail;
    return next !== raw ? next : null;
  }

  // Expose menu translator for preload.js native context menus
  function translateMenuItems(items) {
    if (!Array.isArray(items)) return items;
    return items.map(item => {
      if (!item || typeof item !== 'object') return item;
      const copy = { ...item };
      if (typeof copy.label === 'string') {
        const t = tr(copy.label);
        if (t !== null) copy.label = t;
      }
      if (Array.isArray(copy.submenu)) {
        copy.submenu = translateMenuItems(copy.submenu);
      }
      return copy;
    });
  }

  globalThis.__agzhtw_tr = tr;
  globalThis.__agzhtw_menu = translateMenuItems;

  if (typeof window === 'undefined' || typeof document === 'undefined') return;

  function isSkipped(el) {
    if (!el || el.nodeType !== 1) return true;
    return !!el.closest(SKIP);
  }

  function isEffortNode(el, text) {
    if (!EFFORT_RE.test(text)) return false;
    return !!el.closest(EFFORT_CTX);
  }

  function tryCoalescedElement(el) {
    if (!el || el.childElementCount !== 0 || el.childNodes.length <= 1) return false;
    const nodes = [];
    for (let i = 0; i < el.childNodes.length; i++) {
      const cn = el.childNodes[i];
      if (cn.nodeType === 3) nodes.push(cn);
      else if (cn.nodeType !== 8) return false;
    }
    if (nodes.length <= 1) return false;

    let state = MULTI_STATE.get(el);
    if (!state || state.length !== nodes.length || state.some((s, idx) => s.node !== nodes[idx])) {
      state = nodes.map(n => ({ node: n, orig: n.nodeValue || '', set: n.nodeValue || '' }));
      MULTI_STATE.set(el, state);
    } else {
      for (let i = 0; i < state.length; i++) {
        const cur = state[i].node.nodeValue || '';
        if (cur !== state[i].set) {
          state[i].orig = cur;
        }
      }
    }

    const combined = state.map(s => s.orig).join('');
    const trimmed = norm(combined);
    if (!trimmed || isEffortNode(el, trimmed)) return false;

    const translated = translatePreservingBounds(combined);
    if (translated === null) return false;

    if (state[0].node.nodeValue !== translated) {
      state[0].node.nodeValue = translated;
    }
    state[0].set = translated;
    for (let i = 1; i < state.length; i++) {
      if (state[i].node.nodeValue !== '') {
        state[i].node.nodeValue = '';
      }
      state[i].set = '';
    }
    return true;
  }

  function walkText(node) {
    const p = node.parentElement;
    if (!p || isSkipped(p)) return;
    if (p.childElementCount === 0 && p.childNodes.length > 1) {
      if (tryCoalescedElement(p)) return;
    }
    const raw = node.nodeValue;
    if (!raw || raw.length < 2) return;
    const s = norm(raw);
    if (!s || isEffortNode(p, s)) return;
    const next = translatePreservingBounds(raw);
    if (next !== null && node.nodeValue !== next) {
      node.nodeValue = next;
    }
  }

  function walkAttrs(el) {
    if (isSkipped(el)) return;
    for (let i = 0; i < ATTRS.length; i++) {
      const a = ATTRS[i];
      const v = el.getAttribute(a);
      if (v && v.length >= 2) {
        const out = tr(v);
        if (out !== null && out !== v) {
          el.setAttribute(a, out);
        }
      }
    }
  }

  function walkSubtree(root) {
    if (!root) return;
    if (root.nodeType === 3) {
      walkText(root);
      return;
    }
    if (root.nodeType !== 1 || isSkipped(root)) return;

    walkAttrs(root);
    if (root.childElementCount === 0 && root.childNodes.length > 1) {
      tryCoalescedElement(root);
    }

    const tw = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
      acceptNode(n) {
        const p = n.parentElement;
        return p && !isSkipped(p) ? NodeFilter.FILTER_ACCEPT : NodeFilter.FILTER_REJECT;
      }
    });
    let n;
    while ((n = tw.nextNode())) walkText(n);

    if (root.querySelectorAll) {
      const els = root.querySelectorAll(ATTR_SEL);
      for (let i = 0; i < els.length; i++) walkAttrs(els[i]);
    }
  }

  let q = new Set();
  let scheduled = false;

  function flush() {
    scheduled = false;
    const batch = q;
    q = new Set();
    for (const n of batch) walkSubtree(n);
  }

  function enqueue(n) {
    if (!n) return;
    q.add(n);
    if (!scheduled) {
      scheduled = true;
      requestAnimationFrame(flush);
    }
  }

  function start() {
    if (!document.body) {
      requestAnimationFrame(start);
      return;
    }
    walkSubtree(document.body);
    new MutationObserver(muts => {
      for (let i = 0; i < muts.length; i++) {
        const m = muts[i];
        if (m.type === 'characterData') {
          enqueue(m.target);
        } else if (m.type === 'attributes') {
          if (m.target && m.target.nodeType === 1) walkAttrs(m.target);
        } else {
          const added = m.addedNodes;
          for (let j = 0; j < added.length; j++) enqueue(added[j]);
        }
      }
    }).observe(document.body, {
      childList: true,
      subtree: true,
      characterData: true,
      attributes: true,
      attributeFilter: ATTRS
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', start, { once: true });
  } else {
    start();
  }
})();
