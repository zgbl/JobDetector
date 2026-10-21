const $ = id => document.getElementById(id);
let status = null;
let registering = false;
let subscribeAfterLogin = false;
let busy = false;
let trialTimer;
const selectedPlan = () => document.querySelector('input[name="billingPlan"]:checked').value;
const priceLabel = () => selectedPlan() === 'annual' ? '$9.99/year' : '$1/month';

function message(text) { $('billingMessage').textContent = text; }
function token() { try { return localStorage.getItem('token'); } catch { return null; } }

async function api(path, method = 'GET', body) {
  const auth = token();
  const response = await fetch(path, {method, cache: 'no-store', headers: {
    ...(auth ? {Authorization: `Bearer ${auth}`} : {}), ...(body ? {'Content-Type': 'application/json'} : {}),
  }, ...(body ? {body: JSON.stringify(body)} : {})});
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    if (response.status === 401) { localStorage.removeItem('token'); status = {...status, authenticated: false}; }
    throw new Error(typeof data.detail === 'string' ? data.detail : 'The request could not be completed. Please try again.');
  }
  return data;
}

const trialEndLabel = () => status?.trial_ends_at ? new Date(status.trial_ends_at*1000).toLocaleString() : '';
function update() {
  $('billingAccountButton').hidden = !status || (!status.enabled && !status.authenticated);
  $('billingAccountButton').textContent = status?.vip_lifetime ? 'Lifetime VIP' : status?.trial_active ? 'Plus trial' : 'Account';
  if (!status) return;
  $('trafficNavLink').hidden = !status.is_owner;
  $('billingTerms').hidden = status.vip_lifetime || status.trial_active || !status.authenticated;
  $('billingTerms').textContent = status.test_mode ? 'Stripe test mode. No real payment will be collected.' : 'USD. Renews automatically at your selected interval. Cancel anytime in Manage subscription.';
  $('billingPlans').hidden = status.full_access || !status.authenticated;
  $('subscribeButton').hidden = status.full_access || !status.authenticated;
  $('subscribeButton').disabled = busy || !status.checkout_available;
  $('subscribeButton').textContent = `Subscribe · ${priceLabel()}`;
  $('billingSignIn').hidden = status.authenticated;
  $('billingSignOut').hidden = !status.authenticated;
  $('manageSubscription').hidden = !status.authenticated || status.status === 'none';
  $('billingAccount').textContent = status.authenticated ? 'Signed in to your JobDetector account' : 'Register for 7 days of Plus · No card required';
  $('billingTitle').textContent = status.vip_lifetime ? 'Lifetime VIP · 永久有效' : status.trial_active ? 'Your 7-day Plus trial is active.' : !status.authenticated ? 'Create an account. Get 7 days of Plus.' : status.trial_expired && !status.full_access ? 'Your 7-day Plus trial has ended.' : status.full_access ? 'Your full search library is unlocked.' : 'Try a few searches. Unlock the full library.';
  $('billingDescription').textContent = status.vip_lifetime ? 'Every search is permanently unlocked. No subscription or renewal is required.' : status.trial_active ? `Every search is unlocked until ${trialEndLabel()}. No automatic charge. Choose a paid plan after your trial ends.` : !status.authenticated ? 'Verify your email to unlock every search for 7 days. No card required.' : status.subscribed ?
    `${status.plan === 'annual' ? 'Annual' : 'Monthly'} subscription${status.cancel_at_period_end ? ' · Renewal cancelled; access continues until the current period ends.' : ' · Manage billing or cancel at any time.'}` :
    status.full_access ? 'Full access is available on this account.' : 'Every role, hiring signal, and search shortcut. Choose monthly or annual billing.';
  $('welcomePlus').hidden = !status.enabled || status.vip_lifetime || (status.full_access && !status.trial_active);
  $('welcomePlusText').textContent = !status.authenticated ? 'Create an account and verify your email for 7 days of Plus. All searches unlocked. No card required.' : status.trial_active ? `Plus trial · All searches unlocked until ${trialEndLabel()}. No automatic charge.` : status.trial_expired ? 'Your 7-day Plus trial has ended. Subscribe to keep the full library unlocked.' : 'Sign in with your registered account to manage Plus access.';
  $('welcomePlusAction').textContent = !status.authenticated ? 'Create account · 7 days free' : status.trial_active ? 'View access' : 'View plans';
  clearTimeout(trialTimer);
  if (status.trial_active) trialTimer = setTimeout(async () => { await refreshStatus(); document.dispatchEvent(new Event('billingchange')); }, Math.max(1000,status.trial_ends_at*1000-Date.now()+100));
  if (status.enabled && !status.checkout_available && !status.full_access) message('Subscriptions are not available yet. You can still try the free searches.');
}

async function refreshStatus() {
  try { status = await api('/api/billing/status'); update(); return status; }
  catch (error) {
    $('billingAccountButton').hidden = false;
    message(error.message);
    $('subscribeButton').disabled = true;
    $('billingSignIn').hidden = false;
    return null;
  }
}

async function openStripe(endpoint, body) {
  if (busy) return;
  busy = true; update(); message('Opening secure Stripe checkout…');
  try {
    const result = await api(endpoint, 'POST', body);
    const url = new URL(result.url);
    if (url.protocol !== 'https:' || !['checkout.stripe.com', 'billing.stripe.com'].includes(url.hostname)) throw new Error('Stripe returned an unexpected checkout address. Please try again.');
    window.location.assign(url.href);
  } catch (error) { message(error.message); }
  finally { busy = false; update(); }
}

function showAuth(subscribe = false, register = false) {
  subscribeAfterLogin = subscribe;
  registering = register;
  renderAuthMode();
  $('billingAuthMessage').textContent = '';
  $('billingAuthDialog').showModal();
  $('billingAuthEmail').focus();
}

function openAccount() {
  if (!$('billingPanel').open) $('billingPanel').showModal();
}
const showAccess = () => !status?.authenticated ? showAuth(false,true) : openAccount();
$('billingAccountButton').addEventListener('click',showAccess);
$('welcomePlusAction').addEventListener('click',showAccess);
$('closeBillingPanel').addEventListener('click',()=> $('billingPanel').close());
document.addEventListener('click', event => {
  if (event.target.closest('[data-subscribe]')) { showAccess(); return; }
  if (!event.target.closest('[data-checkout]')) return;
  if (status?.full_access) return;
  if (!status?.checkout_available) { message('Subscriptions are not available yet. Please try again later.'); return; }
  if (!status.authenticated) { showAuth(true,true); return; }
  openStripe('/api/billing/checkout', {plan: selectedPlan()});
});
$('billingSignIn').addEventListener('click', () => showAuth());
$('billingSignOut').addEventListener('click', () => { localStorage.removeItem('token'); window.location.assign('/linkedin-search.html'); });
$('manageSubscription').addEventListener('click', () => openStripe('/api/billing/portal'));
$('closeBillingAuth').addEventListener('click', () => $('billingAuthDialog').close());
document.querySelectorAll('input[name="billingPlan"]').forEach(input => input.addEventListener('change', update));
function renderAuthMode() {
  $('billingAuthIntro').textContent = registering ? 'Verify your email to get 7 days of Plus. No card required.' : 'Sign in to use your Plus access or manage your account.';
  $('billingNameField').hidden = !registering;
  $('billingAuthTitle').textContent = registering ? 'Get 7 days of Plus free' : 'Sign in to JobDetector';
  $('billingAuthSubmit').textContent = registering ? 'Create account' : 'Sign in';
  $('billingAuthPassword').autocomplete = registering ? 'new-password' : 'current-password';
  $('billingAuthPassword').minLength = registering ? 8 : 1;
  $('toggleBillingAuth').textContent = registering ? 'Already have an account? Sign in' : 'New here? Create an account';
  $('billingAuthMessage').textContent = '';
}
$('toggleBillingAuth').addEventListener('click',()=>{ registering=!registering;renderAuthMode(); });
$('billingAuthForm').addEventListener('submit', async event => {
  event.preventDefault();
  $('billingAuthSubmit').disabled = true;
  $('billingAuthMessage').textContent = '';
  try {
    const result = await api(`/api/auth/${registering ? 'register' : 'login'}`, 'POST', {
      email: $('billingAuthEmail').value.trim(), password: $('billingAuthPassword').value,
      ...(registering ? {full_name: $('billingAuthName').value.trim(), signup_source:'linkedin-search'} : {}),
    });
    $('billingAuthPassword').value = '';
    if (registering) { $('billingAuthMessage').textContent = 'Check your email to verify your account. Your 7 free days of Plus start when you verify. Then sign in here.'; return; }
    localStorage.setItem('token', result.access_token);
    $('billingAuthDialog').close();
    await refreshStatus();
    document.dispatchEvent(new Event('billingchange'));
    if (subscribeAfterLogin && status && !status.full_access) await openStripe('/api/billing/checkout', {plan: selectedPlan()});
  } catch (error) { $('billingAuthMessage').textContent = error.message; }
  finally { $('billingAuthSubmit').disabled = false; }
});

async function initialize() {
  await refreshStatus();
  if (status?.vip_lifetime) return;
  const query = new URLSearchParams(window.location.search);
  if (query.get('verified')==='true' && !status?.authenticated) { showAuth(false,false); $('billingAuthMessage').textContent='Email verified. Sign in to use your 7-day Plus access.'; }
  if (['success','cancelled'].includes(query.get('billing'))) openAccount();
  if (query.get('billing') === 'cancelled') message('Checkout cancelled. You have not started a new subscription.');
  if (query.get('billing') !== 'success') return;
  message('Confirming your subscription with Stripe…');
  // The return URL never grants access. Only the server's Stripe check can unlock searches.
  for (let attempt = 0; attempt < 5; attempt += 1) {
    if (status?.subscribed) {
      message('Subscription confirmed. Your full library is unlocked.');
      document.dispatchEvent(new Event('billingchange'));
      return;
    }
    await new Promise(resolve => setTimeout(resolve, 2000));
    await refreshStatus();
  }
  message('Payment confirmation is still pending. Please refresh in a moment. If you paid, do not subscribe again.');
}
initialize();
