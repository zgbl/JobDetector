/**
 * content/content.js — annotates LinkedIn / Indeed job pages with an ATS
 * source-of-truth badge rendered inside a Shadow DOM host.
 *
 * Injected as a classic content script (after content/extract.js). It must
 * never throw into the host page, so every entry point is wrapped in try/catch.
 */
(function () {
  'use strict';

  const EX = globalThis.JobDetectorExtract;
  if (!EX) {
    console.debug('[JobDetector] extract adapter missing, skipping');
    return;
  }

  const HOST_ID = 'jobdetector-badge-host';
  const FIXED_CLASS = 'jd-badge-host--fixed';
  const MUTATION_DEBOUNCE_MS = 800;
  const NAV_DEBOUNCE_MS = 300;
  const POLL_MS = 2500;

  let hostEl = null;
  let shadow = null;
  let refs = null;
  let expanded = false;
  let settingsCache = null;
  let running = false;
  let scheduled = false;
  let lastKey = null;
  let currentJob = null;
  let currentResponse = null;

  /* ---------------------------------------------------------------- *
   * Settings
   * ---------------------------------------------------------------- */
  async function getSettings() {
    if (settingsCache) return settingsCache;
    try {
      const res = await chrome.runtime.sendMessage({ type: 'GET_SETTINGS' });
      settingsCache = res || {};
    } catch {
      settingsCache = { enableLinkedIn: true, enableIndeed: true, autoVerify: true, showGhostButton: true };
    }
    return settingsCache;
  }

  try {
    chrome.storage.onChanged.addListener(() => {
      settingsCache = null;
    });
  } catch {
    /* ignore */
  }

  /* ---------------------------------------------------------------- *
   * Shadow DOM badge
   * ---------------------------------------------------------------- */
  const SHADOW_CSS = `
    .jd-wrap { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif; font-size: 12px; line-height: 1.5; color: #202124; text-align: left; }
    .jd-badge { display: inline-flex; align-items: center; gap: 6px; padding: 3px 10px; border-radius: 14px; font-size: 12px; font-weight: 600; cursor: pointer; border: 1px solid transparent; user-select: none; max-width: 420px; }
    .jd-badge--loading { background: #f1f3f5; color: #495057; border-color: #dee2e6; }
    .jd-badge--open { background: #e6f4ea; color: #137333; border-color: #b7e1c1; }
    .jd-badge--closed { background: #fdecea; color: #b3261e; border-color: #f5c6c2; }
    .jd-badge--unknown { background: #f1f3f5; color: #5f6368; border-color: #dadce0; }
    .jd-badge--degraded { background: #fff4e5; color: #b06000; border-color: #ffd8a8; }
    .jd-badge:hover { filter: brightness(0.97); }
    .jd-spinner { width: 10px; height: 10px; border: 2px solid #adb5bd; border-top-color: transparent; border-radius: 50%; animation: jd-spin 0.8s linear infinite; flex: none; }
    @keyframes jd-spin { to { transform: rotate(360deg); } }
    .jd-card { margin-top: 6px; width: 320px; max-width: 90vw; background: #fff; border: 1px solid #e3e6ea; border-radius: 10px; box-shadow: 0 6px 20px rgba(0,0,0,0.12); padding: 10px 12px; }
    .jd-row { margin-top: 6px; word-break: break-word; }
    .jd-label { color: #6b7280; }
    .jd-strong { font-weight: 600; }
    .jd-link { color: #1a73e8; text-decoration: underline; word-break: break-all; }
    .jd-actions { display: flex; gap: 8px; margin-top: 10px; }
    .jd-btn { flex: 1; padding: 6px 8px; border-radius: 8px; border: 1px solid #d0d7de; background: #fff; color: #202124; cursor: pointer; font-size: 12px; font-family: inherit; }
    .jd-btn--primary { background: #1a73e8; color: #fff; border-color: #1a73e8; }
    .jd-btn[disabled] { opacity: 0.5; cursor: not-allowed; }
    .jd-ghost { margin-top: 8px; padding-top: 8px; border-top: 1px dashed #e3e6ea; }
    .jd-factors { margin: 4px 0 0 16px; padding: 0; }
    .jd-factors li { margin: 2px 0; }
    .jd-err { color: #b3261e; margin-top: 6px; }
    .jd-muted { color: #6b7280; }
  `;

  function el(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined && text !== null) node.textContent = String(text);
    return node;
  }

  function ensureUi() {
    if (hostEl && hostEl.isConnected) return refs;

    hostEl = document.getElementById(HOST_ID);
    if (!hostEl) {
      hostEl = document.createElement('div');
      hostEl.id = HOST_ID;
      hostEl.style.display = 'inline-block';
      hostEl.style.marginLeft = '8px';
      hostEl.style.verticalAlign = 'middle';
    }
    if (!hostEl.shadowRoot) {
      shadow = hostEl.attachShadow({ mode: 'open' });
      const style = document.createElement('style');
      style.textContent = SHADOW_CSS;
      shadow.appendChild(style);

      const wrap = el('div', 'jd-wrap');
      const badge = el('div', 'jd-badge jd-badge--loading');
      const spinner = el('span', 'jd-spinner');
      const badgeText = el('span', null, 'Checking…');
      badge.appendChild(spinner);
      badge.appendChild(badgeText);

      const card = el('div', 'jd-card');
      card.style.display = 'none';

      wrap.appendChild(badge);
      wrap.appendChild(card);
      shadow.appendChild(wrap);

      badge.addEventListener('click', (event) => {
        event.preventDefault();
        event.stopPropagation();
        expanded = !expanded;
        card.style.display = expanded ? 'block' : 'none';
      });
      // Keep clicks inside the card from bubbling into the host page.
      card.addEventListener('click', (event) => event.stopPropagation());

      refs = { wrap, badge, badgeText, spinner, card };
    } else {
      shadow = hostEl.shadowRoot;
    }
    return refs;
  }

  function anchorBadge() {
    const ui = ensureUi();
    const anchor = EX.findBadgeAnchor(EX.detectSite());
    if (anchor && anchor.parentElement) {
      if (hostEl.parentElement !== anchor.parentElement || hostEl.previousElementSibling !== anchor) {
        anchor.insertAdjacentElement('afterend', hostEl);
      }
      hostEl.classList.remove(FIXED_CLASS);
      hostEl.style.marginLeft = '8px';
    } else if (hostEl.parentElement !== document.body) {
      document.body.appendChild(hostEl);
      hostEl.classList.add(FIXED_CLASS);
      hostEl.style.marginLeft = '0';
    }
    return ui;
  }

  function removeBadge() {
    if (hostEl && hostEl.parentElement) hostEl.parentElement.removeChild(hostEl);
    hostEl = null;
    shadow = null;
    refs = null;
    expanded = false;
  }

  function setBadge(kind, text, opts = {}) {
    const ui = anchorBadge();
    ui.badge.className = `jd-badge jd-badge--${kind}`;
    ui.badgeText.textContent = text;
    ui.badge.title = opts.title || text;
    ui.spinner.style.display = kind === 'loading' ? 'inline-block' : 'none';
  }

  function renderLoading() {
    try {
      const ui = anchorBadge();
      ui.card.style.display = 'none';
      expanded = false;
      ui.card.replaceChildren();
      setBadge('loading', 'Checking…', { title: 'Checking the employer\'s ATS source…' });
    } catch (err) {
      console.debug('[JobDetector] renderLoading failed', err);
    }
  }

  function fmtTime(iso) {
    if (!iso) return '';
    const date = new Date(iso);
    if (Number.isNaN(date.getTime())) return String(iso);
    return date.toLocaleString('en-US', { hour12: false });
  }

  function statusHeadline(result) {
    if (result.status === 'open') return 'Open at the source';
    if (result.status === 'closed') return "Closed at the source · don't apply";
    return "Can't determine";
  }

  function setBadgeFromResult(result, degraded) {
    if (degraded) {
      setBadge('degraded', '🟠 Backend unreachable (checked locally)', { title: result.reason_en || result.reason || 'Backend unreachable, so this result came from the local checker' });
      return;
    }
    if (result.status === 'open') {
      setBadge('open', '🟢 Open at the source', { title: result.reason_en || result.reason || 'The source ATS still lists this posting as open' });
    } else if (result.status === 'closed') {
      setBadge('closed', "⚠️ Closed at the source · don't apply", { title: result.reason_en || result.reason || 'The source ATS has taken this posting down' });
    } else {
      setBadge('unknown', "❓ Can't determine", { title: result.reason_en || result.reason || 'The source status could not be determined' });
    }
  }

  function buildCard(job, result, degraded, label) {
    const ui = anchorBadge();
    const card = ui.card;
    card.replaceChildren();

    card.appendChild(el('div', 'jd-row jd-strong', statusHeadline(result)));

    const reasonText = result.reason_en || result.reason;
    if (reasonText) {
      const reasonRow = el('div', 'jd-row');
      reasonRow.appendChild(el('span', 'jd-label', 'Verdict:'));
      reasonRow.appendChild(el('span', null, reasonText));
      card.appendChild(reasonRow);
    }

    const atsRow = el('div', 'jd-row');
    atsRow.appendChild(el('span', 'jd-label', 'Source:'));
    atsRow.appendChild(el('span', null, label || result.ats || 'Unknown source'));
    card.appendChild(atsRow);

    if (result.matched_title) {
      const row = el('div', 'jd-row');
      row.appendChild(el('span', 'jd-label', 'Matched role:'));
      row.appendChild(el('span', null, result.matched_title));
      card.appendChild(row);
    }

    // Explicit link says "closed", but the employer has a similar role open.
    const alt = result.alternative;
    if (alt && alt.status === 'open') {
      const row = el('div', 'jd-row jd-muted');
      row.appendChild(el('span', 'jd-label', 'But this employer has a similar role still open: '));
      const text = alt.matched_title ? `"${alt.matched_title}" (${alt.ats || 'source'})` : (alt.ats || 'source ATS');
      row.appendChild(el('span', null, text));
      const altUrl = alt.apply_url || alt.canonical_url;
      if (altUrl) {
        const link = el('a', 'jd-link', ' Apply to this one →');
        link.href = altUrl;
        link.target = '_blank';
        link.rel = 'noopener noreferrer';
        row.appendChild(link);
      }
      card.appendChild(row);
    }

    if (result.canonical_url) {
      const row = el('div', 'jd-row');
      row.appendChild(el('span', 'jd-label', 'Source link:'));
      const link = el('a', 'jd-link', result.canonical_url);
      link.href = result.canonical_url;
      link.target = '_blank';
      link.rel = 'noopener noreferrer';
      row.appendChild(link);
      card.appendChild(row);
    }

    const timeRow = el('div', 'jd-row');
    timeRow.appendChild(el('span', 'jd-label', 'Checked:'));
    timeRow.appendChild(el('span', null, fmtTime(result.checked_at) || '—'));
    if (result.status === 'closed' && result.posted_at) {
      timeRow.appendChild(el('span', 'jd-label', ' · Closed:'));
      timeRow.appendChild(el('span', null, result.posted_at));
    }
    card.appendChild(timeRow);

    if (degraded) {
      card.appendChild(el('div', 'jd-row jd-muted', 'Backend unreachable — this result came from the local checker.'));
    }

    /* --- actions --- */
    const actions = el('div', 'jd-actions');
    const applyBtn = el('button', 'jd-btn jd-btn--primary', 'Apply at the source →');
    applyBtn.type = 'button';
    applyBtn.addEventListener('click', (event) => {
      event.preventDefault();
      event.stopPropagation();
      const target = result.apply_url || result.canonical_url;
      if (target) window.open(target, '_blank', 'noopener,noreferrer');
    });
    actions.appendChild(applyBtn);

    const ghostEnabled = !degraded && (settingsCache ? settingsCache.showGhostButton !== false : true);
    const ghostBtn = el('button', 'jd-btn', 'Ghost job risk analysis');
    ghostBtn.type = 'button';
    if (!ghostEnabled) {
      ghostBtn.disabled = true;
      ghostBtn.title = 'Backend required';
    }
    actions.appendChild(ghostBtn);
    card.appendChild(actions);

    const ghostBox = el('div', 'jd-ghost');
    ghostBox.style.display = 'none';
    card.appendChild(ghostBox);

    ghostBtn.addEventListener('click', async (event) => {
      event.preventDefault();
      event.stopPropagation();
      await runGhost(ghostBtn, ghostBox, job, result);
    });

    return card;
  }

  function renderResult(job, response) {
    try {
      const result = response && response.result ? response.result : { status: 'unknown', ats: 'unknown' };
      const degraded = Boolean(response && response.degraded);
      setBadgeFromResult(result, degraded);
      const label = result.ats && result.ats !== 'unknown' ? result.ats : '';
      buildCard(job, result, degraded, label);
    } catch (err) {
      console.debug('[JobDetector] renderResult failed', err);
    }
  }

  function renderGhostResult(box, data) {
    box.replaceChildren();
    if (!data || typeof data !== 'object') {
      box.appendChild(el('div', 'jd-err', 'Ghost job analysis returned an empty result.'));
      return;
    }
    const oneLiner = data.one_liner || '';
    if (oneLiner) box.appendChild(el('div', 'jd-row jd-strong', oneLiner));

    const scoreRow = el('div', 'jd-row');
    scoreRow.appendChild(el('span', 'jd-label', 'Ghost risk score:'));
    const score = Number(data.ghost_score);
    scoreRow.appendChild(el('span', 'jd-strong', Number.isFinite(score) ? `${Math.round(score)} / 100` : '—'));
    if (data.is_ghost_job) scoreRow.appendChild(el('span', 'jd-err', ' · High risk: likely a ghost job'));
    box.appendChild(scoreRow);

    const factors = Array.isArray(data.risk_factors) ? data.risk_factors : [];
    if (factors.length) {
      box.appendChild(el('div', 'jd-row jd-label', 'Risk factors:'));
      const list = el('ul', 'jd-factors');
      for (const factor of factors) list.appendChild(el('li', null, String(factor)));
      box.appendChild(list);
    }

    if (data.recommendation) {
      const row = el('div', 'jd-row');
      row.appendChild(el('span', 'jd-label', 'Recommendation:'));
      row.appendChild(el('span', null, data.recommendation));
      box.appendChild(row);
    }
    if (data.provider) {
      box.appendChild(el('div', 'jd-row jd-muted', `Analysis source: ${data.provider}${data.cached ? ' (cached)' : ''}`));
    }
  }

  function renderGhostError(box, message) {
    box.replaceChildren();
    box.appendChild(el('div', 'jd-err', message));
  }

  async function runGhost(ghostBtn, ghostBox, job, result) {
    ghostBox.style.display = 'block';
    const original = ghostBtn.textContent;
    ghostBtn.disabled = true;
    ghostBtn.textContent = 'Analyzing…';
    try {
      const res = await chrome.runtime.sendMessage({
        type: 'GHOST_ANALYZE',
        payload: {
          job_title: job.title || '',
          company_name: job.company || '',
          post_age_days: job.postAgeDays,
          source_type: job.site || 'unknown',
          jd_text: String(job.jdText || '').slice(0, 6000),
          source_status: result && result.status ? result.status : null,
        },
      });
      if (res && res.ok) {
        renderGhostResult(ghostBox, res.data);
      } else {
        renderGhostError(ghostBox, (res && res.error) || 'Ghost job analysis failed. Please try again later.');
        ghostBtn.disabled = true;
        ghostBtn.title = 'Backend required';
      }
    } catch {
      renderGhostError(ghostBox, 'Could not reach the backend. Check your network or the backend URL in Settings.');
      ghostBtn.disabled = true;
      ghostBtn.title = 'Backend required';
    } finally {
      ghostBtn.textContent = original || 'Ghost job risk analysis';
      if (!ghostBtn.title) ghostBtn.disabled = false;
    }
  }

  /* ---------------------------------------------------------------- *
   * Verification run
   * ---------------------------------------------------------------- */
  async function runVerify(force) {
    if (running) return currentResponse;
    running = true;
    try {
      const settings = await getSettings();
      const job = EX.extractJob();
      if (!job.supported) {
        removeBadge();
        return null;
      }
      if (job.site === 'linkedin' && settings.enableLinkedIn === false) {
        removeBadge();
        return null;
      }
      if (job.site === 'indeed' && settings.enableIndeed === false) {
        removeBadge();
        return null;
      }

      currentJob = job;
      lastKey = job.key;
      currentResponse = null;
      expanded = false;
      renderLoading();

      let response = null;
      try {
        response = await chrome.runtime.sendMessage({
          type: 'VERIFY_JOB',
          payload: {
            url: location.href,
            urls: job.urls,
            company: job.company,
            title: job.title,
            location: job.location,
            sourceType: job.site,
            refresh: Boolean(force),
          },
        });
      } catch (err) {
        console.debug('[JobDetector] background unreachable', err);
      }

      if (!response || !response.result) {
        response = {
          ok: false,
          degraded: true,
          result: {
            input_url: location.href,
            status: 'unknown',
            ats: 'unknown',
            confidence: 0,
            reason: 'The extension background worker is unavailable, so the check could not run',
            canonical_url: '',
            apply_url: '',
            matched_title: '',
            company: '',
            location: '',
            posted_at: '',
            http_status: null,
            checked_at: new Date().toISOString(),
            elapsed_ms: 0,
            cached: false,
          },
        };
      }
      currentResponse = response;
      renderResult(job, response);
      return response;
    } catch (err) {
      console.debug('[JobDetector] runVerify failed', err);
      return null;
    } finally {
      running = false;
    }
  }

  /** True when automatic (page-load / SPA-navigation) verification is allowed. */
  async function autoVerifyAllowed() {
    const settings = await getSettings();
    return settings.autoVerify !== false;
  }

  function scheduleVerify(delay) {
    if (scheduled) return;
    scheduled = true;
    setTimeout(() => {
      scheduled = false;
      Promise.resolve()
        .then(async () => {
          const job = safeExtract();
          if (!job || !job.supported) return;
          if (job.key === lastKey && currentResponse) return;
          if (!(await autoVerifyAllowed())) return;
          runVerify(false);
        })
        .catch((err) => console.debug('[JobDetector] scheduleVerify failed', err));
    }, delay);
  }

  function safeExtract() {
    try {
      return EX.extractJob();
    } catch (err) {
      console.debug('[JobDetector] extract failed', err);
      return null;
    }
  }

  /* ---------------------------------------------------------------- *
   * SPA navigation hooks
   * ---------------------------------------------------------------- */
  function patchHistory() {
    for (const method of ['pushState', 'replaceState']) {
      const original = history[method];
      if (typeof original !== 'function' || original.__jdPatched) continue;
      const patched = function patchedHistory() {
        const value = original.apply(this, arguments);
        try {
          scheduleVerify(NAV_DEBOUNCE_MS);
        } catch (err) {
          console.debug('[JobDetector] history hook failed', err);
        }
        return value;
      };
      patched.__jdPatched = true;
      history[method] = patched;
    }
  }

  function startObservers() {
    try {
      window.addEventListener('popstate', () => scheduleVerify(NAV_DEBOUNCE_MS));
      window.addEventListener('hashchange', () => scheduleVerify(NAV_DEBOUNCE_MS));
    } catch (err) {
      console.debug('[JobDetector] nav listeners failed', err);
    }

    try {
      const observer = new MutationObserver(() => scheduleVerify(MUTATION_DEBOUNCE_MS));
      observer.observe(document.body, { childList: true, subtree: true });
    } catch (err) {
      console.debug('[JobDetector] mutation observer failed', err);
    }

    // Polling fallback: LinkedIn soft-navigates without a DOM mutation we can see.
    setInterval(() => {
      Promise.resolve()
        .then(async () => {
          const job = safeExtract();
          if (!job || !job.supported) return;
          if (job.key === lastKey && currentResponse) return;
          if (!(await autoVerifyAllowed())) return;
          runVerify(false);
        })
        .catch((err) => console.debug('[JobDetector] poll failed', err));
    }, POLL_MS);
  }

  /* ---------------------------------------------------------------- *
   * Popup bridge
   * ---------------------------------------------------------------- */
  chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
    const type = message && message.type;
    if (type === 'GET_STATE') {
      (async () => {
        const job = currentJob || safeExtract();
        if (!job || !job.supported) {
          sendResponse({ supported: false });
          return;
        }
        if (!currentResponse) await runVerify(false);
        sendResponse({
          supported: true,
          job: {
            site: job.site,
            title: job.title,
            company: job.company,
            location: job.location,
            jdText: String(job.jdText || '').slice(0, 6000),
            postAgeDays: job.postAgeDays,
          },
          response: currentResponse,
        });
      })().catch(() => sendResponse({ supported: false }));
      return true;
    }
    if (type === 'REVERIFY') {
      runVerify(true)
        .then((response) => {
          const job = currentJob || safeExtract() || {};
          sendResponse({
            supported: true,
            job: {
              site: job.site,
              title: job.title,
              company: job.company,
              location: job.location,
              jdText: String(job.jdText || '').slice(0, 6000),
              postAgeDays: job.postAgeDays,
            },
            response,
          });
        })
        .catch(() => sendResponse({ supported: false }));
      return true;
    }
    return false;
  });

  /* ---------------------------------------------------------------- *
   * Boot
   * ---------------------------------------------------------------- */
  try {
    patchHistory();
    startObservers();
    scheduleVerify(600);
  } catch (err) {
    console.debug('[JobDetector] boot failed', err);
  }
})();
