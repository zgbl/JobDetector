const $ = id => document.getElementById(id);
let status = null;
let registering = false;
let subscribeAfterLogin = false;
let busy = false;
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

function update() {
  $('billingPanel').hidden = !status?.enabled;
  if (!status) return;
  $('trafficNavLink').hidden = !status.is_owner;
  $('billingTerms').textContent = status.test_mode ? 'Stripe test mode. No real payment will be collected.' : 'USD. Renews automatically at your selected interval. Cancel anytime in Manage subscription.';
  $('billingPlans').hidden = status.full_access;
  $('subscribeButton').hidden = status.full_access;
  $('subscribeButton').disabled = busy || !status.checkout_available;
  $('subscribeButton').textContent = `Subscribe · ${priceLabel()}`;
  $('billingSignIn').hidden = status.authenticated;
  $('billingSignOut').hidden = !status.authenticated;
  $('manageSubscription').hidden = !status.authenticated || status.status === 'none';
  $('billingAccount').textContent = status.authenticated ? 'Signed in to your JobDetector account' : '10 free searches · No card needed for the preview';
  $('billingTitle').textContent = status.full_access ? 'Your full search library is unlocked.' : 'Try a few searches. Unlock the full library.';
  $('billingDescription').textContent = status.subscribed ?
    `${status.plan === 'annual' ? 'Annual' : 'Monthly'} subscription${status.cancel_at_period_end ? ' · Renewal cancelled; access continues until the current period ends.' : ' · Manage billing or cancel at any time.'}` :
    status.full_access ? 'Full access is available on this account.' : 'Every role, hiring signal, and search shortcut. Choose monthly or annual billing.';
  if (status.enabled && !status.checkout_available) message('Subscriptions are not available yet. You can still try the free searches.');
}

async function refreshStatus() {
  try { status = await api('/api/billing/status'); update(); return status; }
  catch (error) {
    $('billingPanel').hidden = false;
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

function showAuth(subscribe = false) {
  subscribeAfterLogin = subscribe;
  $('billingAuthMessage').textContent = '';
  $('billingAuthDialog').showModal();
  $('billingAuthEmail').focus();
}

document.addEventListener('click', event => {
  if (!event.target.closest('[data-subscribe]')) return;
  if (!status?.checkout_available) { message('Subscriptions are not available yet. Please try again later.'); return; }
  if (!status.authenticated) { showAuth(true); return; }
  openStripe('/api/billing/checkout', {plan: selectedPlan()});
});
$('billingSignIn').addEventListener('click', () => showAuth());
$('billingSignOut').addEventListener('click', () => { localStorage.removeItem('token'); window.location.assign('/linkedin-search.html'); });
$('manageSubscription').addEventListener('click', () => openStripe('/api/billing/portal'));
$('closeBillingAuth').addEventListener('click', () => $('billingAuthDialog').close());
document.querySelectorAll('input[name="billingPlan"]').forEach(input => input.addEventListener('change', update));
$('toggleBillingAuth').addEventListener('click', () => {
  registering = !registering;
  $('billingNameField').hidden = !registering;
  $('billingAuthTitle').textContent = registering ? 'Create your JobDetector account' : 'Sign in to subscribe';
  $('billingAuthSubmit').textContent = registering ? 'Create account' : 'Sign in';
  $('billingAuthPassword').autocomplete = registering ? 'new-password' : 'current-password';
  $('billingAuthPassword').minLength = registering ? 8 : 1;
  $('toggleBillingAuth').textContent = registering ? 'Already have an account? Sign in' : 'New here? Create an account';
  $('billingAuthMessage').textContent = '';
});
$('billingAuthForm').addEventListener('submit', async event => {
  event.preventDefault();
  $('billingAuthSubmit').disabled = true;
  $('billingAuthMessage').textContent = '';
  try {
    const result = await api(`/api/auth/${registering ? 'register' : 'login'}`, 'POST', {
      email: $('billingAuthEmail').value.trim(), password: $('billingAuthPassword').value,
      ...(registering ? {full_name: $('billingAuthName').value.trim()} : {}),
    });
    $('billingAuthPassword').value = '';
    if (registering) { $('billingAuthMessage').textContent = 'Check your email to verify your account, then return here and sign in.'; return; }
    localStorage.setItem('token', result.access_token);
    $('billingAuthDialog').close();
    await refreshStatus();
    document.dispatchEvent(new Event('billingchange'));
    if (subscribeAfterLogin && !status?.subscribed) await openStripe('/api/billing/checkout', {plan: selectedPlan()});
  } catch (error) { $('billingAuthMessage').textContent = error.message; }
  finally { $('billingAuthSubmit').disabled = false; }
});

async function initialize() {
  await refreshStatus();
  const query = new URLSearchParams(window.location.search);
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
