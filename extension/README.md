# JobDetector — Job Source Check (Chrome extension)

While you browse jobs on LinkedIn / Indeed, it automatically checks the
**employer's own ATS** (Greenhouse / Lever / Ashby / Workable / SmartRecruiters /
Workday / Breezy / Recruitee, …) to see whether the **original posting is still
open**, and annotates the result with a badge right next to the job title.

- Still open at the source → safe to apply
- Closed at the source → this is probably a zombie posting on LinkedIn / Indeed, **don't apply**
- Can't determine → network, bot protection or page-structure problem

It also offers two extra capabilities: **Apply at the source** (skip the
aggregator and open the ATS application page directly) and
**Ghost job risk analysis** (calls your own backend LLM service on demand and
returns a ghost-job risk score).

---

## 1. Install (Load unpacked)

1. Open Chrome and go to `chrome://extensions`
2. Turn on **Developer mode** in the top right
3. Click **Load unpacked**
4. Select this repository's `extension/` folder (the folder containing this README)
5. Open any LinkedIn / Indeed job page — the badge appears next to the job title

No build step, no npm, no third-party dependencies: every file is a plain ES
Module that Chrome loads directly.

> If the badge does not appear: confirm the page is `linkedin.com/jobs/*` or
> `indeed.com/viewjob*`, then click "Reload" once on `chrome://extensions` and
> refresh the page.

---

## 2. Badge legend

| Badge | Meaning |
| --- | --- |
| `Checking…` | Requesting the backend / running the local check |
| `🟢 Open at the source` | The source ATS explicitly reports this posting as still open |
| `⚠️ Closed at the source · don't apply` | The source ATS has taken the posting down (404 / id missing from the board list / closing date passed) |
| `❓ Can't determine` | The source could not be reached or its response could not be interpreted |
| `🟠 Backend unreachable (checked locally)` | The backend request failed and the result came from the extension's built-in local checker (usually lower confidence) |

Click the badge to expand the detail card:

- **Verdict**: a human-readable reason (identical to the backend's `reason_en`)
- **Source**: the recognised ATS name
- **Source link**: `canonical_url`
- **Apply at the source →**: opens `apply_url` in a new tab (`rel="noopener"`)
- **Ghost job risk analysis**: calls `POST /api/ghost/analyze` and shows `one_liner`,
  `ghost_score`, `risk_factors[]`, `recommendation`. When the backend is
  unavailable the button is disabled with the tooltip "Backend required".

Toolbar badge on the extension icon: `✓` (green, open) / `!` (red, closed) /
`?` (grey, can't determine).

---

## 3. Backend HTTP contract

The default backend URL is `https://jobdetector.blackrice.top` and can be changed
on the settings page (`chrome.storage.sync` → `settings.backendBaseUrl`). All
endpoints are CORS-open (`Access-Control-Allow-Origin: *`).

| Method | Path | Request | Response |
| --- | --- | --- | --- |
| POST | `/api/verify/source` | `{urls: string[], company, title, location, refresh: bool}` | `{count, results: VerifyResult[], lookup: VerifyResult \| null}` |
| POST | `/api/verify/lookup` | `{company, title}` | `{result: VerifyResult \| null}` |
| POST | `/api/ghost/analyze` | `{job_title, company_name, post_age_days: number\|null, source_type, jd_text, source_status, lang: 'en'}` | `{ghost_score, is_ghost_job, risk_factors[], recommendation, one_liner, provider, cached}` |
| GET | `/api/health` | — | `{"status": "ok", ...}` (used by "Test connection" on the settings page) |

`VerifyResult` (every field is always present; unknown values are an empty string / `null`):

```
{ input_url, status: "open"|"closed"|"unknown", ats, confidence: 0..1, reason, reason_en,
  canonical_url, apply_url, matched_title, company, location, posted_at,
  http_status: int|null, checked_at: ISO8601, elapsed_ms: int, cached: bool }
```

The response always carries both `reason` (Chinese) and `reason_en` (English);
the extension displays `reason_en` whenever it is available.

`lookup` in `/api/verify/source` is the backend's fallback: when no ATS link was
found on the page, the backend reverse-looks-up `company + title` in its company
index, and may be `null`.

### Request flow

1. The content script scrapes the job title, company, location and **all**
   outbound ATS links on the page (including `a[href]`, embedded JSON `<script>`
   tags and `data-*` attributes; for Indeed it additionally parses
   `#applyJobLinkContainer a`).
2. The background worker calls `POST /api/verify/source` (`AbortController`
   timeout 8s).
3. On success → combine `results` + `lookup` and pick the best result by
   `open > closed > unknown`, then by `confidence`.
4. On failure (network error / timeout / no backend configured) → fall back to
   the local checker and mark the payload `degraded: true`.

### Local (offline) verification coverage

`verifyLocal()` in `lib/ats.js` does not need the backend and covers:

- **Greenhouse**: `GET boards-api.greenhouse.io/v1/boards/{token}/jobs/{id}`,
  200 = open; on 404/410 it re-checks the board list (present = unlisted job post,
  absent = closed)
- **Lever**: `GET api.lever.co/v0/postings/{token}/{id}`, on 404 it falls back to
  comparing against the board list
- **Ashby**: `GET api.ashbyhq.com/posting-api/job-board/{org}`, matched by `id`
  inside `jobs[]`
- **Generic page probe**: HTTP status code (404/410 = closed) + expired-posting
  notice phrases + whether the URL was redirected to a listing page

Other ATSs (Workable / SmartRecruiters / Workday / Breezy / Recruitee, …) are only
checked when the **backend is available**; when the backend is down they return
"Can't determine".

---

## 4. Caching model

- Storage location: `chrome.storage.local`, key `jd_cache_v1`
- Cache key: `ats|token|jobId` when the source is identifiable, otherwise the
  normalized URL
- TTL (background constants, at the top of `background.js`):
  - `open` → **12 hours** (a recruitable state is stable and changes slowly)
  - `closed` / `unknown` → **6 hours** (negative results are more likely to
    change, for example when a posting is re-opened)
  - If `cacheTtlHours` is changed on the settings page, `open` uses that value
    and `closed`/`unknown` use half of it
- Capacity cap: **500 entries**; when exceeded, the oldest by `checkedAt` are
  evicted first
- Clicking "Re-check" sends `refresh: true`, **skips the cache** and refreshes
  that entry

---

## 5. Privacy

- The extension does not collect or upload any browsing history or account
  information.
- Page scraping (job title, company, location, outbound links, JD text) is used
  **in local memory only**.
- Network requests to the **backend that you configure yourself** happen in only
  two cases:
  1. Automatic verification: the page URL list + company + job title are sent to
     `POST /api/verify/source` (to decide whether the source posting is still
     open);
  2. You **manually click** "Ghost job risk analysis": only then is the JD text
     (truncated to 6000 characters) sent to `POST /api/ghost/analyze`.
- Apart from that, local ATS verification talks directly to the public job-board
  APIs of Greenhouse / Lever / Ashby.
- Clearing the cache: settings page → "Clear local cache" (deletes `jd_cache_v1`).

---

## 6. Troubleshooting

**The badge always shows "🟠 Backend unreachable (checked locally)"**
- Check that the backend URL is correct (settings page → Test connection); it
  should return `{"status":"ok"}`.
- Open the DevTools Console and look for CORS errors; the backend must allow
  `Access-Control-Allow-Origin: *` and allow `POST` +
  `Content-Type: application/json` (the `OPTIONS` preflight must return 204/200).
- Self-signed certificates / HTTPS certificate errors also make the request fail.

**The badge never appears**
- Only `linkedin.com/jobs/*` (`/jobs/view/*`, `/jobs/search*`,
  `/jobs/collections/*`) and `indeed.com/viewjob*` are injected.
- On the settings page, confirm the toggle for that site is on.
- LinkedIn is an SPA: the extension patches `history.pushState/replaceState`,
  listens for `popstate`, and uses a `MutationObserver` (800ms debounce) plus a
  2.5s polling fallback; if it still does not appear, reload the whole page.

**LinkedIn / Indeed changed their DOM structure**
- The site adapters live in `content/extract.js`. When a selector breaks, the
  badge degrades to "❓ Can't determine" or the JD text cannot be scraped, but the
  page is **never** broken.
- To fix it: update the `*_TITLE` / `*_COMPANY` / `*_LOCATION` / `*_JD` selector
  arrays in that file.

**The ghost analysis button is greyed out**
- This means the backend is unavailable (`degraded`); hovering it shows
  "Backend required". Once the backend connection is fixed, click "Re-check" to
  recover.

---

## 7. Directory structure

```
extension/
├── manifest.json          # MV3 manifest (no icons, no build step)
├── background.js          # Service Worker: verification orchestration, cache, badge, message routing
├── lib/ats.js             # Pure functions: identifyAts / verifyLocal (no chrome.*, node-testable)
├── content/
│   ├── extract.js         # LinkedIn / Indeed site adapters (classic script, attaches to globalThis)
│   ├── content.js         # Shadow DOM badge + detail card + SPA navigation listeners
│   └── content.css        # Host-element positioning styles only
├── popup/                 # Toolbar popup
├── options/               # Settings page
└── test/ats.test.mjs      # node --test unit tests
```

Running the tests:

```bash
node --test extension/test/*.test.mjs
```

> As of Node.js 24, `node --test` no longer accepts a "directory" argument
> (`node --test extension/test/` fails with
> `Cannot find module .../extension/test`), so use the glob form above.
