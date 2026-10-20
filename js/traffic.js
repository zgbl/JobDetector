(() => {
  if (window.__jobDetectorTraffic) return;
  window.__jobDetectorTraffic = true;
  let visitor, session;
  try {
    visitor = localStorage.getItem('jd-visitor-v1') || crypto.randomUUID();
    localStorage.setItem('jd-visitor-v1', visitor);
    const old = JSON.parse(localStorage.getItem('jd-session-v1') || 'null');
    session = old && Date.now() - old.last < 30 * 60 * 1000 ? old.id : crypto.randomUUID();
    localStorage.setItem('jd-session-v1', JSON.stringify({id: session, last: Date.now()}));
  } catch { visitor = crypto.randomUUID(); session = crypto.randomUUID(); }

  function record(event, target) {
    const payload = {event_id: crypto.randomUUID(), visitor_id: visitor, session_id: session,
      event, page: location.pathname, referrer: document.referrer ? new URL(document.referrer).origin : '',
      preset_id: target?.dataset.id || '', plan: document.querySelector('input[name="billingPlan"]:checked')?.value || 'monthly'};
    let token = null;
    try { token = localStorage.getItem('token'); } catch { /* Anonymous analytics remain available. */ }
    fetch('/api/traffic/event', {method: 'POST', headers: {'Content-Type': 'application/json', ...(token ? {Authorization: `Bearer ${token}`} : {})}, body: JSON.stringify(payload), keepalive: true}).catch(() => {});
  }
  record('page_view');
  document.addEventListener('click', event => {
    const search = event.target.closest('a[data-action="open"]');
    const subscribe = event.target.closest('[data-checkout]');
    if (search) record('search_open', search);
    else if (subscribe) record('subscribe_click', subscribe);
    try { localStorage.setItem('jd-session-v1', JSON.stringify({id: session, last: Date.now()})); } catch { /* Optional storage. */ }
  }, {capture: true});
})();
