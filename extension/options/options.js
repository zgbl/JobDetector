/**
 * options/options.js — settings page.
 *
 * Settings live in `chrome.storage.sync` under the `settings` object; the flat
 * dotted keys (`settings.backendBaseUrl`, …) are mirrored for compatibility.
 */

const SETTINGS_KEY = 'settings';
const CACHE_KEY = 'jd_cache_v1';
const DEFAULTS = {
  backendBaseUrl: 'https://jobdetector.blackrice.top',
  enableLinkedIn: true,
  enableIndeed: true,
  autoVerify: true,
  showGhostButton: true,
  cacheTtlHours: 12,
};

const $ = (id) => document.getElementById(id);
const fields = {
  backendBaseUrl: $('backendBaseUrl'),
  enableLinkedIn: $('enableLinkedIn'),
  enableIndeed: $('enableIndeed'),
  autoVerify: $('autoVerify'),
  showGhostButton: $('showGhostButton'),
  cacheTtlHours: $('cacheTtlHours'),
};

let toastTimer = null;

function cleanBaseUrl(value) {
  return String(value || '').trim().replace(/\/+$/, '');
}

function showToast(message, isError) {
  const toast = $('toast');
  toast.textContent = message;
  toast.style.background = isError ? '#b3261e' : '#202124';
  toast.classList.add('jd-toast--show');
  if (toastTimer) clearTimeout(toastTimer);
  toastTimer = setTimeout(() => toast.classList.remove('jd-toast--show'), 2400);
}

async function loadSettings() {
  const flatKeys = Object.keys(DEFAULTS).map((k) => `${SETTINGS_KEY}.${k}`);
  let stored = {};
  try {
    stored = await chrome.storage.sync.get([SETTINGS_KEY, ...flatKeys]);
  } catch {
    stored = {};
  }
  const bundle = stored[SETTINGS_KEY] && typeof stored[SETTINGS_KEY] === 'object' ? stored[SETTINGS_KEY] : {};
  const merged = { ...DEFAULTS, ...bundle };
  for (const key of Object.keys(DEFAULTS)) {
    const dotted = stored[`${SETTINGS_KEY}.${key}`];
    if (dotted !== undefined && bundle[key] === undefined) merged[key] = dotted;
  }
  return merged;
}

function fillForm(settings) {
  fields.backendBaseUrl.value = settings.backendBaseUrl || DEFAULTS.backendBaseUrl;
  fields.enableLinkedIn.checked = settings.enableLinkedIn !== false;
  fields.enableIndeed.checked = settings.enableIndeed !== false;
  fields.autoVerify.checked = settings.autoVerify !== false;
  fields.showGhostButton.checked = settings.showGhostButton !== false;
  const ttl = Number(settings.cacheTtlHours);
  fields.cacheTtlHours.value = Number.isFinite(ttl) && ttl > 0 ? ttl : DEFAULTS.cacheTtlHours;
}

function readForm() {
  const ttl = Number(fields.cacheTtlHours.value);
  return {
    backendBaseUrl: cleanBaseUrl(fields.backendBaseUrl.value) || DEFAULTS.backendBaseUrl,
    enableLinkedIn: fields.enableLinkedIn.checked,
    enableIndeed: fields.enableIndeed.checked,
    autoVerify: fields.autoVerify.checked,
    showGhostButton: fields.showGhostButton.checked,
    cacheTtlHours: Number.isFinite(ttl) && ttl > 0 ? ttl : DEFAULTS.cacheTtlHours,
  };
}

async function persist(settings) {
  const payload = { [SETTINGS_KEY]: settings };
  for (const key of Object.keys(DEFAULTS)) payload[`${SETTINGS_KEY}.${key}`] = settings[key];
  await chrome.storage.sync.set(payload);
}

/* --- events --- */

$('save').addEventListener('click', async () => {
  try {
    const settings = readForm();
    await persist(settings);
    fillForm(settings);
    showToast('Saved');
  } catch (err) {
    showToast(`Save failed: ${err && err.message ? err.message : 'unknown error'}`, true);
  }
});

$('testConnection').addEventListener('click', async () => {
  const resultEl = $('testResult');
  const button = $('testConnection');
  const base = cleanBaseUrl(fields.backendBaseUrl.value) || DEFAULTS.backendBaseUrl;
  resultEl.className = 'jd-test-result';
  resultEl.textContent = 'Testing…';
  button.disabled = true;
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 8000);
  try {
    const res = await fetch(`${base}/api/health`, { signal: controller.signal, headers: { Accept: 'application/json' } });
    const data = await res.json().catch(() => null);
    if (res.ok && data && data.status === 'ok') {
      resultEl.className = 'jd-test-result jd-ok';
      resultEl.textContent = '✅ Connection OK';
    } else {
      resultEl.className = 'jd-test-result jd-bad';
      resultEl.textContent = `❌ Connection failed (HTTP ${res.status})`;
    }
  } catch (err) {
    resultEl.className = 'jd-test-result jd-bad';
    resultEl.textContent = `❌ Connection failed: ${err && err.name === 'AbortError' ? 'request timed out' : 'the address is unreachable'}`;
  } finally {
    clearTimeout(timer);
    button.disabled = false;
  }
});

$('clearCache').addEventListener('click', async () => {
  const resultEl = $('clearResult');
  try {
    await chrome.storage.local.remove(CACHE_KEY);
    resultEl.className = 'jd-test-result jd-ok';
    resultEl.textContent = '✅ Local cache cleared';
  } catch (err) {
    resultEl.className = 'jd-test-result jd-bad';
    resultEl.textContent = `Clear failed: ${err && err.message ? err.message : 'unknown error'}`;
  }
});

loadSettings()
  .then(fillForm)
  .catch(() => fillForm(DEFAULTS));
