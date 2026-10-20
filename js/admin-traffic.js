const $ = id => document.getElementById(id);
const escapeHtml = value => String(value ?? '').replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'})[char]);
const number = value => Number(value || 0).toLocaleString();
let loading = false;

function renderTable(id, rows) {
  $(id).innerHTML = rows.length ? rows.map(row => `<tr><td>${escapeHtml(row.label)}</td><td>${number(row.count)}</td></tr>`).join('') : '<tr><td colspan="2">No activity recorded in this period.</td></tr>';
}

async function load() {
  if (loading) return;
  loading = true; $('refreshTraffic').disabled = true;
  try {
    const token = localStorage.getItem('token');
    const query = new URLSearchParams({days: $('trafficDays').value, include_owner: $('includeOwner').checked});
    const response = await fetch(`/api/traffic/admin?${query}`, {headers: token ? {Authorization:`Bearer ${token}`} : {}, cache:'no-store'});
    if (!response.ok) {
      $('trafficReport').hidden = true; $('trafficGate').hidden = false;
      $('trafficGate').innerHTML = response.status === 401 ? '<h2>Sign in as Tuxy</h2><p>Sign in on JobDetector, then return to this page.</p><a href="/">Open JobDetector sign in</a>' : '<h2>Access denied</h2><p>This dashboard is private to the configured Tuxy account.</p>';
      return;
    }
    const data = await response.json();
    $('trafficGate').hidden = true; $('trafficReport').hidden = false;
    const summary = data.summary;
    const metrics = [['Page views',summary.page_views,'Selected period'],['Unique visitors',summary.unique_visitors,'Estimated browser IDs'],['Sessions',summary.sessions,'30-minute activity window'],['Search clicks',summary.search_clicks,'LinkedIn searches opened'],['Subscribe clicks',summary.subscribe_clicks,'Intent to subscribe'],['Checkout starts',summary.checkouts_started,'Live Stripe sessions'],['New paying users',summary.new_paying_users,'First paid subscription in period'],['Active subscribers',summary.active_subscribers,`${summary.monthly_subscribers} monthly · ${summary.annual_subscribers} annual`]];
    $('trafficMetrics').innerHTML = metrics.map(([label,value,note])=>`<article class="traffic-metric"><span>${label}</span><strong>${number(value)}</strong><small>${escapeHtml(note)}</small></article>`).join('');
    const max = Math.max(1,...data.daily.flatMap(row=>[row.views,row.searches]));
    $('trafficTrend').innerHTML = data.daily.map(row=>`<div class="trend-row"><span>${escapeHtml(row.date.slice(5))}</span><div><div class="trend-track"><i style="width:${row.views/max*100}%"></i></div><div class="trend-track searches"><i style="width:${row.searches/max*100}%"></i></div></div><strong>${number(row.views)} / ${number(row.searches)}</strong></div>`).join('');
    renderTable('trafficPages',data.top_pages); renderTable('trafficSources',data.top_sources); renderTable('trafficSearches',data.top_searches);
    $('trackingSince').textContent = data.tracking_since ? `This report's instrumentation started ${new Date(data.tracking_since).toLocaleString()}. Earlier traffic is available in Product analytics. Daily totals use New York time.` : 'Tracking starts with this deployment. No earlier activity is backfilled.';
    $('trafficUpdated').textContent = `Updated ${new Date(data.generated_at).toLocaleTimeString()}`;
  } catch { $('trafficUpdated').textContent='Could not load metrics. Please try Refresh.'; }
  finally { loading=false; $('refreshTraffic').disabled=false; }
}
$('trafficDays').addEventListener('change',load); $('includeOwner').addEventListener('change',load); $('refreshTraffic').addEventListener('click',load);
$('checkStripe').addEventListener('click', async () => {
  $('checkStripe').disabled=true;
  $('stripeCheckResult').textContent='Checking Stripe…';
  try {
    const response=await fetch('/api/billing/preflight',{method:'POST',headers:{Authorization:`Bearer ${localStorage.getItem('token') || ''}`},cache:'no-store'});
    const result=await response.json();
    if (!response.ok) throw new Error(typeof result.detail==='string'?result.detail:'Could not verify Stripe setup.');
    $('stripeCheckResult').textContent=`${result.mode==='live'?'Live':'Test'} account verified: $1/month and $9.99/year. ${result.enabled?'Checkout is enabled.':'Checkout is not enabled yet.'} Send a signed test event from Stripe to confirm webhook delivery.`;
  } catch(error) { $('stripeCheckResult').textContent=error.message; }
  finally { $('checkStripe').disabled=false; }
});
load();
