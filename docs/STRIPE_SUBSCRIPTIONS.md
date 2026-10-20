# Search Console subscriptions and owner analytics

The existing FastAPI/MongoDB application serves Stripe-hosted Checkout and Customer Portal.
The supplied Stripe product is `prod_VTQVFnqvuTNwG0`:

| Plan | Recurring price | Live Stripe Price ID |
| --- | --- | --- |
| Monthly | USD $1.00 per month | `price_1USTeLFC3kxu6kUOBgyDTB6A` |
| Annual | USD $9.99 per year | `price_1USTfIFC3kxu6kUOZksDu146` |

These IDs are not secrets. The backend verifies product, amount, currency, and interval before opening Checkout.

## Activate

1. Add `STRIPE_SECRET_KEY` to Vercel's Production environment for project `job-detector`.
   Use the key from the same account/mode as the prices. Never put it in source, chat, or frontend code.
2. In Stripe Workbench, choose **Create an event destination**, **Your account**, and **Snapshot** payloads. Create a webhook endpoint at
   `https://jobdetector.blackrice.top/api/billing/webhook` with:
   - `checkout.session.completed`
   - `checkout.session.async_payment_succeeded`
   - `checkout.session.async_payment_failed`
   - `customer.subscription.created`
   - `customer.subscription.updated`
   - `customer.subscription.deleted`
   - `invoice.paid`
   - `invoice.payment_failed`
3. Add its signing secret as `STRIPE_WEBHOOK_SECRET` in Vercel Production.
4. Customer Portal uses a dedicated JobDetector configuration, created automatically on first use.
   It enables cancellation at period end, invoice history, and payment-method updates, with plan switching disabled.
   It does not change the account's default portal configuration or TensuGo's portal settings.
5. Ensure `BASE_URL=https://jobdetector.blackrice.top` and `ADMIN_EMAIL` identifies Tuxy's existing verified account.
6. Sign in as Tuxy at `/admin-traffic.html` and click **Check Stripe setup**. This verifies both prices and creates no payment.
7. After the test checklist below passes, set `BILLING_ENABLED=true` and redeploy. Send a signed test event from Stripe Workbench to verify webhook delivery.

Until enabled, the full existing library stays available and checkout endpoints refuse payment.
If billing is enabled but credentials are incomplete, only the free preview is served and checkout remains disabled.
There is no browser-side flag that grants subscription access.

## Test before accepting live payments

Use Stripe test mode with separate test product/prices and override all three IDs through
`STRIPE_PRODUCT_ID`, `STRIPE_MONTHLY_PRICE_ID`, and `STRIPE_ANNUAL_PRICE_ID`.
Use matching test keys/webhook secrets and set `BILLING_ENABLED=true` in the test deployment.
Do not use test keys with the supplied live Price IDs.

- A logged-out visitor receives one usable search per category (10 total).
- Sign up, verify email, and sign in with a non-admin account.
- Test both plans with Stripe's test card `4242 4242 4242 4242`, a future expiry, and any three-digit CVC.
- Confirm the displayed amount/interval, return to the site, and check all 131 searches unlock.
- Reopening Checkout while active must not create another subscription.
- Cancel through Manage subscription; access should continue while Stripe's subscription is active.
- Send payment-failure/cancellation events and verify access follows the current Stripe subscription status.
- Verify an unsigned webhook returns 400 and `?billing=success` cannot grant access on its own.
- Verify test payments do not count as live paid conversions in the traffic report.
- Replace test settings with live settings only after these checks. No real payment is made by automated tests.

## Runtime behavior

`GET /api/linkedin/presets` returns full queries only for a current subscriber (or administrator),
and 10 free searches otherwise. The complete catalog is in `data/linkedin_search_presets.json`,
outside the application's public static mounts. The public JS contains only the URL builder.
This repository has historically been public; payment gates the hosted service rather than making
previously published search terms secret.

Checkout is tied to the authenticated, verified user. Customer and Price IDs are selected on the server.
A per-user lock and reused open Checkout Session prevent parallel subscription checkout.
Stripe webhook signatures are verified against the raw body with a five-minute tolerance.
Webhooks retrieve the current Stripe state, so replayed or delayed events cannot restore expired access.
Access is checked against Stripe on protected catalog requests; a client return URL is never proof of payment.
Only `active` subscriptions grant access; `past_due`, `unpaid`, `incomplete`, and `canceled` do not.
Do not add price overrides without migrating existing subscribers: access recognizes the currently configured prices.

## Traffic and subscriber report

Open `/admin-traffic.html`. Data at `/api/traffic/admin` requires a valid token for the verified,
active account identified by `ADMIN_EMAIL` or the server-stored owner flag. Another account with `is_admin=true` is denied.
The public HTML shell contains no report data. The owner sees links in the homepage navigation,
Search Console navigation, and existing Product Analytics page after signing in.

The report shows 7/30/90-day page views, estimated browser visitors, 30-minute sessions,
search clicks, subscribe clicks, live checkout starts, new paying users, current monthly/annual
subscribers, daily trends, pages, sources, and popular searches. Daily buckets use America/New_York.
Owner activity is excluded by default. Test-mode payments are excluded from paid metrics.

New events use random browser IDs and sanitized page paths/referrer domains; no raw IP, email,
URL query strings, passwords, or Stripe Checkout URLs are saved in the traffic collection.
IDs can be cleared and public events can be blocked/spoofed, so visitor figures are estimates.
Collection starts at deployment; older traffic remains in the existing Product Analytics report.

## Verification

```sh
python -m pytest tests/test_billing.py tests/test_traffic.py -q
node --test tests/linkedin_search.test.mjs
```

The automated tests mock Stripe and MongoDB and validate signed-webhook handling using the official SDK.
They do not prove that live credentials, webhooks, Customer Portal, or a real payment are configured.

## Owner subscription ledger

`/admin-traffic.html#subscriptions` reads current Stripe subscription data through
`GET /api/billing/admin/subscriptions`, restricted to the verified configured owner.
It displays customer email/name, monthly/annual amount, status/access, latest invoice amount paid,
start date, renewal/end date, scheduled cancellation, and links to Stripe management.
Search, status/plan filters, pagination and CSV export work over the returned records.
`GET /api/billing/admin/subscriptions/{id}/invoices` provides paginated bill history after
checking that the subscription contains a configured JobDetector price. Other products are excluded.
The scan is capped at 2,000 account subscriptions with an explicit incomplete-report warning.
No report response is publicly cached. Expected MRR uses renewing active subscriptions at list price,
annual prices divided by 12, before discounts/tax/refunds; it is not cash revenue.

Stripe Python 16 uses API version 2026-09-30.endive: do not send `payment_method_types`
to Checkout Session creation. Payment methods follow the account's Dashboard settings.
The request idempotency namespace was bumped to v2 to avoid replaying older failed requests.

## Lifetime owner access

Tuxy has server-stored `vip_lifetime=true` and `is_owner=true` on the verified existing user record.
Owner identity also supports the configured `ADMIN_EMAIL`. Public registration cannot set these fields.
Lifetime access does not expire, does not require Stripe, and cannot create paid Checkout Sessions.
Display names never grant permissions. The account entry shows Lifetime VIP; pricing is presented
in an on-demand dialog rather than a banner above the search controls.
