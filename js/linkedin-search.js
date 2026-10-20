import { GROUPS, SIGNALS, PRESETS, ALL_PRESETS, buildLinkedInUrl } from './linkedin-presets.js?v=20261019_data_bi';

const STORAGE_KEY = 'jobdetector-linkedin-console-v1';
const byId = new Map(ALL_PRESETS.map(preset => [preset.id, preset]));
const groupById = new Map(GROUPS.map(group => [group.id, group]));
const state = { view: 'all', text: '', destination: 'posts', location: 'any', date: 'week', sort: 'relevant', favorites: [], recent: [], counts: {} };
try {
  const saved = JSON.parse(localStorage.getItem(STORAGE_KEY) || '{}');
  state.favorites = Array.isArray(saved.favorites) ? saved.favorites.filter(id => byId.has(id)) : [];
  state.recent = Array.isArray(saved.recent) ? saved.recent.filter(id => byId.has(id)).slice(0, 12) : [];
  state.counts = saved.counts && typeof saved.counts === 'object' ? saved.counts : {};
} catch { /* Private browsing or disabled storage should not stop searches. */ }

const $ = id => document.getElementById(id);
const escapeHtml = value => String(value).replace(/[&<>"']/g, char => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[char]);
const save = () => { try { localStorage.setItem(STORAGE_KEY, JSON.stringify({ favorites: state.favorites, recent: state.recent, counts: state.counts })); } catch { /* Search remains usable. */ } };
let toastTimer;
function toast(message) {
  $('toast').textContent = message;
  $('toast').classList.add('visible');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => $('toast').classList.remove('visible'), 3800);
}

function linkFor(preset, broad = false) {
  return buildLinkedInUrl(broad ? preset.broadQuery : preset.query, state.destination, state.location, state.date);
}

function searchCard(preset) {
  const favorite = state.favorites.includes(preset.id);
  const count = Number(state.counts[preset.id]) || 0;
  return `<article class="search-card" data-id="${escapeHtml(preset.id)}">
    <div class="card-main"><div class="card-title-row"><h4>${escapeHtml(preset.label)}</h4>${count ? `<span class="use-count" title="Opened ${count} times">${count}×</span>` : ''}</div>
      <p class="query-text">${escapeHtml(preset.query)}</p></div>
    <div class="card-actions"><button class="mini-action favorite-action ${favorite ? 'is-favorite' : ''}" data-action="favorite" data-id="${escapeHtml(preset.id)}" aria-label="${favorite ? 'Remove' : 'Add'} ${escapeHtml(preset.label)} ${favorite ? 'from' : 'to'} favorites" title="${favorite ? 'Remove favorite' : 'Save favorite'}"><i class="${favorite ? 'fas' : 'far'} fa-star" aria-hidden="true"></i></button>
      <button class="mini-action" data-action="copy" data-id="${escapeHtml(preset.id)}" aria-label="Copy keywords for ${escapeHtml(preset.label)}" title="Copy keywords"><i class="far fa-copy" aria-hidden="true"></i></button>
      <a class="open-link" href="${escapeHtml(linkFor(preset))}" target="_blank" rel="noopener noreferrer" data-action="open" data-id="${escapeHtml(preset.id)}" aria-label="Search ${escapeHtml(preset.label)} on LinkedIn in a new tab">Search <i class="fas fa-arrow-up-right-from-square" aria-hidden="true"></i></a></div>
  </article>`;
}

function signalCard(preset) {
  return `<article class="signal-card"><div><h3>${escapeHtml(preset.label)}</h3><p>${escapeHtml(preset.query)}</p></div><div class="signal-actions">
    <a href="${escapeHtml(linkFor(preset))}" target="_blank" rel="noopener noreferrer" data-action="open" data-id="${escapeHtml(preset.id)}">Search signal <i class="fas fa-arrow-up-right-from-square" aria-hidden="true"></i></a>
    <a class="broad-link" href="${escapeHtml(linkFor(preset, true))}" target="_blank" rel="noopener noreferrer" data-action="open" data-id="${escapeHtml(preset.id)}" data-broad="true" title="Search without the hiring phrase">Broaden</a>
  </div></article>`;
}

function matches(preset) {
  const needle = state.text.toLocaleLowerCase();
  return !needle || `${preset.label} ${preset.query} ${preset.broadQuery || ''}`.toLocaleLowerCase().includes(needle);
}

function renderNav() {
  const entries = [{ id: 'all', label: 'All searches', count: PRESETS.length, icon: 'fa-layer-group' }, ...GROUPS.map(group => ({ id: group.id, label: group.short, count: group.items.length, icon: 'fa-arrow-right' })), { id: 'signals', label: 'Hiring signals', count: SIGNALS.length, icon: 'fa-bolt' }];
  $('categoryNav').innerHTML = entries.map(entry => `<button data-view="${entry.id}" class="category-item ${state.view === entry.id ? 'active' : ''}" ${state.view === entry.id ? 'aria-current="true"' : ''}><i class="fas ${entry.icon}" aria-hidden="true"></i><span>${escapeHtml(entry.label)}</span><small>${entry.count}</small></button>`).join('');
  $('favoriteCount').textContent = state.favorites.length;
  $('recentCount').textContent = state.recent.length;
  document.querySelectorAll('.sidebar-special').forEach(button => button.classList.toggle('active', button.dataset.view === state.view));
  document.querySelectorAll('.quick-row [data-view]').forEach(button => button.classList.toggle('active', button.dataset.view === state.view));
  document.querySelectorAll('.quick-row [data-location]').forEach(button => button.classList.toggle('active', button.dataset.location === state.location));
  document.querySelectorAll('.quick-row [data-date]').forEach(button => button.classList.toggle('active', button.dataset.date === state.date));
}

function render() {
  renderNav();
  const title = state.view === 'all' ? 'All searches' : state.view === 'signals' ? 'Direct Hiring Signals' : state.view === 'favorites' ? 'Favorites' : state.view === 'recent' ? 'Recently opened' : state.view === 'recruiters' ? 'Recruiter posts' : state.view === 'eng-leaders' ? 'Engineering leader posts' : groupById.get(state.view)?.name || 'All searches';
  $('viewTitle').textContent = title;
  $('viewDescription').textContent = state.view === 'favorites' ? 'Your saved searches stay on this device.' : state.view === 'recent' ? 'The last searches you opened on this device.' : state.view === 'signals' ? 'Posts that explicitly mention hiring, with a broader alternative for each.' : state.view === 'recruiters' ? 'Find internal technical recruiters and talent teams.' : state.view === 'eng-leaders' ? 'Find engineering managers and team leaders who may be hiring.' : groupById.get(state.view)?.description || 'Every ready-to-use LinkedIn search in one place.';

  let sections = [];
  if (state.view === 'favorites' || state.view === 'recent') {
    const ids = state.view === 'favorites' ? state.favorites : state.recent;
    const selected = ids.map(id => byId.get(id)).filter(Boolean).filter(matches);
    sections = selected.length ? [{ id: state.view, name: title, items: selected }] : [];
  } else if (state.view !== 'signals') {
    const isPeopleSubset = state.view === 'recruiters' || state.view === 'eng-leaders';
    sections = GROUPS.filter(group => state.view === 'all' || state.view === group.id || (isPeopleSubset && group.id === 'leaders')).map(group => ({ ...group, items: PRESETS.filter(preset => preset.category === group.id && matches(preset) && (!isPeopleSubset || (state.view === 'recruiters' ? ['leaders-recruiter-ai', 'leaders-recruiter-fde', 'leaders-talent'].includes(preset.id) : !['leaders-recruiter-ai', 'leaders-recruiter-fde', 'leaders-talent'].includes(preset.id)))) })).filter(group => group.items.length);
  }
  $('presetGroups').innerHTML = sections.map(group => `<section class="preset-section" aria-labelledby="heading-${group.id}"><div class="group-heading"><div><span class="group-mark"></span><h3 id="heading-${group.id}">${escapeHtml(group.name)}</h3></div><span>${group.items.length} search${group.items.length === 1 ? '' : 'es'}</span></div><div class="preset-grid">${group.items.map(searchCard).join('')}</div></section>`).join('');

  const showSignals = state.view === 'all' || state.view === 'signals';
  const visibleSignals = showSignals ? SIGNALS.filter(matches) : [];
  $('signalsSection').hidden = !visibleSignals.length;
  $('signalsGrid').innerHTML = visibleSignals.map(signalCard).join('');
  const total = sections.reduce((sum, group) => sum + group.items.length, 0) + visibleSignals.length;
  $('resultSummary').textContent = `${total} search${total === 1 ? '' : 'es'} shown · ${state.destination === 'posts' ? 'Hiring posts' : 'Job listings'} destination · ${$('dateSelect').selectedOptions[0].textContent} · ${state.location === 'any' ? 'No location keywords' : $('locationSelect').selectedOptions[0].textContent + ' keywords'}`;
  $('emptyState').hidden = total !== 0;
  updateFilterExplainer();
}

function updateFilterExplainer() {
  $('filterExplainer').innerHTML = `<i class="fas fa-circle-info" aria-hidden="true"></i> ${state.date === 'all' ? 'No date restriction.' : `${$('dateSelect').selectedOptions[0].textContent} is included in every LinkedIn search link.`} ${state.sort === 'recent' ? 'On LinkedIn, choose Sort by → Most recent, if offered. ' : 'Sort is set on LinkedIn. '}Location adds keywords; it does not verify eligibility or apply a LinkedIn location filter.`;
}

function setView(view) { state.view = view; render(); document.querySelector('.results-toolbar').scrollIntoView({ behavior: 'smooth', block: 'start' }); }
document.addEventListener('click', async event => {
  const viewButton = event.target.closest('[data-view]');
  if (viewButton) { setView(viewButton.dataset.view); return; }
  const locationButton = event.target.closest('[data-location]');
  if (locationButton) { state.location = locationButton.dataset.location; $('locationSelect').value = state.location; render(); return; }
  const dateButton = event.target.closest('[data-date]');
  if (dateButton) { state.date = dateButton.dataset.date; state.destination = 'posts'; $('dateSelect').value = state.date; document.querySelector('input[name="destination"][value="posts"]').checked = true; render(); toast('Every search link now includes Past 24 hours.'); return; }
  const action = event.target.closest('[data-action]');
  if (!action) return;
  const preset = byId.get(action.dataset.id);
  if (!preset) return;
  if (action.dataset.action === 'open') {
    // A real anchor handles navigation and still works if a popup blocker disallows window.open.
    state.recent = [preset.id, ...state.recent.filter(id => id !== preset.id)].slice(0, 12);
    state.counts[preset.id] = (Number(state.counts[preset.id]) || 0) + 1;
    save(); renderNav();
    const countLabel = action.closest('.search-card')?.querySelector('.use-count');
    if (countLabel) { countLabel.textContent = `${state.counts[preset.id]}×`; countLabel.title = `Opened ${state.counts[preset.id]} times`; }
    if (state.sort === 'recent') toast('On LinkedIn, choose Sort by → Most recent, if offered.');
  } else if (action.dataset.action === 'favorite') {
    state.favorites = state.favorites.includes(preset.id) ? state.favorites.filter(id => id !== preset.id) : [...state.favorites, preset.id];
    save(); render();
  } else if (action.dataset.action === 'copy') {
    try { await navigator.clipboard.writeText(preset.query); toast('Keywords copied.'); }
    catch { toast('Copy unavailable here. Select the visible query text to copy it.'); }
  }
});

document.querySelectorAll('input[name="destination"]').forEach(input => input.addEventListener('change', () => { state.destination = input.value; render(); }));
$('locationSelect').addEventListener('change', event => { state.location = event.target.value; render(); });
$('dateSelect').addEventListener('change', event => { state.date = event.target.value; render(); });
$('sortSelect').addEventListener('change', event => { state.sort = event.target.value; render(); });
$('filterInput').addEventListener('input', event => { state.text = event.target.value.trim(); render(); });
$('clearFilter').addEventListener('click', () => { state.text = ''; $('filterInput').value = ''; render(); $('filterInput').focus(); });
document.addEventListener('keydown', event => { if (event.key === '/' && !['INPUT', 'SELECT', 'TEXTAREA'].includes(document.activeElement.tagName)) { event.preventDefault(); $('filterInput').focus(); } });
$('presetTotal').textContent = `${PRESETS.length + SIGNALS.length}`;
render();
