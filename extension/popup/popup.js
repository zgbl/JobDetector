/**
 * popup/popup.js — toolbar popup.
 *
 * Reads the current tab's job + verification state from the content script
 * (which owns the page scrape) and lets the user re-verify or run the ghost
 * analysis on demand.
 */

const $ = (id) => document.getElementById(id);

const ui = {
  job: $('jd-job'),
  jobTitle: $('jd-job-title'),
  jobCompany: $('jd-job-company'),
  status: $('jd-status'),
  badge: $('jd-status-badge'),
  reason: $('jd-status-reason'),
  meta: $('jd-status-meta'),
  reverify: $('jd-reverify'),
  openSource: $('jd-open-source'),
  ghost: $('jd-ghost'),
  ghostBtn: $('jd-ghost-btn'),
  ghostResult: $('jd-ghost-result'),
  unsupported: $('jd-unsupported'),
  optionsLink: $('jd-options-link'),
};

let state = { supported: false, job: null, response: null };

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined && text !== null) node.textContent = String(text);
  return node;
}

function fmtTime(iso) {
  if (!iso) return '';
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return String(iso);
  return date.toLocaleString('en-US', { hour12: false });
}

function setGhostEnabled(enabled, tooltip) {
  ui.ghostBtn.disabled = !enabled;
  ui.ghostBtn.title = enabled ? '' : tooltip || 'Backend required';
}

function render() {
  if (!state.supported) {
    ui.unsupported.classList.remove('jd-hidden');
    ui.job.classList.add('jd-hidden');
    ui.status.classList.add('jd-hidden');
    ui.ghost.classList.add('jd-hidden');
    return;
  }

  ui.unsupported.classList.add('jd-hidden');
  ui.job.classList.remove('jd-hidden');
  ui.status.classList.remove('jd-hidden');
  ui.ghost.classList.remove('jd-hidden');

  const job = state.job || {};
  ui.jobTitle.textContent = job.title || 'No job title detected';
  ui.jobCompany.textContent = [job.company, job.location].filter(Boolean).join(' · ');

  const response = state.response;
  const result = response && response.result ? response.result : null;
  const degraded = Boolean(response && response.degraded);

  if (!result) {
    ui.badge.className = 'jd-badge jd-badge--loading';
    ui.badge.textContent = 'Checking…';
    ui.reason.textContent = '';
    ui.meta.textContent = '';
    ui.openSource.disabled = true;
    return;
  }

  if (degraded) {
    ui.badge.className = 'jd-badge jd-badge--degraded';
    ui.badge.textContent = '🟠 Backend unreachable (checked locally)';
  } else if (result.status === 'open') {
    ui.badge.className = 'jd-badge jd-badge--open';
    ui.badge.textContent = '🟢 Open at the source';
  } else if (result.status === 'closed') {
    ui.badge.className = 'jd-badge jd-badge--closed';
    ui.badge.textContent = "⚠️ Closed at the source · don't apply";
  } else {
    ui.badge.className = 'jd-badge jd-badge--unknown';
    ui.badge.textContent = "❓ Can't determine";
  }

  ui.reason.textContent = result.reason_en || result.reason || '';

  const metaParts = [];
  if (result.ats && result.ats !== 'unknown') metaParts.push(`Source: ${result.ats}`);
  if (result.confidence) metaParts.push(`Confidence: ${Math.round(result.confidence * 100)}%`);
  if (result.checked_at) metaParts.push(`Checked: ${fmtTime(result.checked_at)}`);
  if (result.cached) metaParts.push('From cache');
  ui.meta.textContent = metaParts.join(' · ');

  const applyUrl = result.apply_url || result.canonical_url;
  ui.openSource.disabled = !applyUrl;
  ui.openSource.dataset.url = applyUrl || '';

  setGhostEnabled(!degraded, 'Backend required');
}

async function loadState(force) {
  let tab = null;
  try {
    [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  } catch {
    tab = null;
  }
  if (!tab || typeof tab.id !== 'number') {
    state = { supported: false, job: null, response: null };
    render();
    return;
  }
  try {
    const res = await chrome.tabs.sendMessage(tab.id, { type: force ? 'REVERIFY' : 'GET_STATE' });
    if (res && res.supported) {
      state = { supported: true, job: res.job || null, response: res.response || null };
    } else {
      state = { supported: false, job: null, response: null };
    }
  } catch {
    state = { supported: false, job: null, response: null };
  }
  render();
}

function renderGhost(data) {
  ui.ghostResult.replaceChildren();
  if (!data || typeof data !== 'object') {
    ui.ghostResult.appendChild(el('div', 'jd-err', 'Ghost job analysis returned an empty result.'));
    return;
  }
  if (data.one_liner) ui.ghostResult.appendChild(el('div', 'jd-strong', data.one_liner));

  const score = Number(data.ghost_score);
  const scoreRow = el('div', null);
  scoreRow.appendChild(el('span', 'jd-muted', 'Ghost risk score:'));
  scoreRow.appendChild(el('span', 'jd-strong', Number.isFinite(score) ? `${Math.round(score)} / 100` : '—'));
  if (data.is_ghost_job) scoreRow.appendChild(el('span', 'jd-err', ' · High risk: likely a ghost job'));
  ui.ghostResult.appendChild(scoreRow);

  const factors = Array.isArray(data.risk_factors) ? data.risk_factors : [];
  if (factors.length) {
    ui.ghostResult.appendChild(el('div', 'jd-muted', 'Risk factors:'));
    const list = el('ul');
    for (const factor of factors) list.appendChild(el('li', null, String(factor)));
    ui.ghostResult.appendChild(list);
  }
  if (data.recommendation) {
    const row = el('div');
    row.appendChild(el('span', 'jd-muted', 'Recommendation:'));
    row.appendChild(el('span', null, data.recommendation));
    ui.ghostResult.appendChild(row);
  }
  if (data.provider) {
    ui.ghostResult.appendChild(
      el('div', 'jd-muted', `Analysis source: ${data.provider}${data.cached ? ' (cached)' : ''}`)
    );
  }
}

/* --- events --- */
ui.reverify.addEventListener('click', async () => {
  ui.reverify.disabled = true;
  ui.reverify.textContent = 'Checking…';
  ui.badge.className = 'jd-badge jd-badge--loading';
  ui.badge.textContent = 'Checking…';
  try {
    await loadState(true);
  } finally {
    ui.reverify.disabled = false;
    ui.reverify.textContent = 'Re-check';
  }
});

ui.openSource.addEventListener('click', () => {
  const url = ui.openSource.dataset.url;
  if (url) chrome.tabs.create({ url });
});

ui.ghostBtn.addEventListener('click', async () => {
  const job = state.job || {};
  const result = state.response && state.response.result ? state.response.result : null;
  ui.ghostResult.replaceChildren();
  ui.ghostBtn.disabled = true;
  const original = ui.ghostBtn.textContent;
  ui.ghostBtn.textContent = 'Analyzing…';
  try {
    const res = await chrome.runtime.sendMessage({
      type: 'GHOST_ANALYZE',
      payload: {
        job_title: job.title || '',
        company_name: job.company || '',
        post_age_days: job.postAgeDays ?? null,
        source_type: job.site || 'unknown',
        jd_text: String(job.jdText || '').slice(0, 6000),
        source_status: result ? result.status : null,
      },
    });
    if (res && res.ok) {
      renderGhost(res.data);
    } else {
      ui.ghostResult.appendChild(el('div', 'jd-err', (res && res.error) || 'Ghost job analysis failed. Please try again later.'));
    }
  } catch {
    ui.ghostResult.appendChild(el('div', 'jd-err', 'Could not reach the backend. Check your network or the backend URL in Settings.'));
  } finally {
    ui.ghostBtn.textContent = original || 'Ghost job risk analysis';
    ui.ghostBtn.disabled = false;
  }
});

ui.optionsLink.addEventListener('click', (event) => {
  event.preventDefault();
  chrome.runtime.openOptionsPage();
});

loadState(false);
