# Research Lab experiment

Entry: `/research-lab.html`. The LinkedIn Console has a small Research Lab link in its search controls and a secondary footer link. No experimental item is added to the public navbar.

## Two ways to try

- Paste the expanded text of the LinkedIn post, its author heading and optional job URL. A Basis example fills real input, not a canned report.
- Download `/assets/jobdetector-research-lab.zip`, unpack and load the folder in Chrome's Extensions page. Click the extension toolbar icon on a LinkedIn tab to enable buttons; click Research this job on the desired post. Its capture is transferred in a URL fragment and the lab starts the request. No permalink or database job record is required.

The extension requests only activeTab and scripting, not cookies, history or global host permissions. It reads currently rendered post text. Collapsed text should be expanded by the user first. LinkedIn DOM changes may break selectors. The extraction script was checked on a two-post browser fixture; installation and behavior on every LinkedIn layout are not guaranteed. It is an unpacked prototype, not a Web Store release.

## Actual research scope

The server fetches up to three supplied HTTPS links and employer homepages explicitly linked by supported ATS pages. It does not run a general search engine, log in to LinkedIn, scrape member profiles, or browse arbitrary model-suggested URLs. Unknown values stay unknown. Sources are shown with timestamps, read text and short quotes. Capture-only claims are marked reported; hiring-manager identity remains inference. Model interpretation can still be wrong: quote existence checks do not prove every interpretation is entailed by the quote.

Each DNS result and redirect must be a public IP, then the HTTPS connection pins that IP while preserving TLS hostname/certificate verification. Response size, redirect count and fetch time are bounded. No cookies or authentication headers are forwarded to evidence sites. Captures are not persisted in the database; reports can be downloaded locally as Markdown. Daily per-user attempt counts are stored server-side.

Existing `DEEPSEEK_API_KEY` (preferred) or `OPENROUTER_API_KEY` powers analysis. Neither key is exposed to the client. LLM calls receive only the supplied professional post and fetched source text. Models have no tool authority; web content is untrusted data. Plus/trial users have 5 attempts per UTC day; permanent VIP users 25. A verified signed-in account with full access is required. No automatic messages or job applications are sent.

## Shared navigation correction

`js/site-nav.js` keeps the same public links/order across existing glass-nav pages: Jobs, LinkedIn Search, Verify Job, Favorites, Companies, My Searches, Feedback, About. Existing homepage event handlers and element IDs are preserved. Account-only links live under Tools, and the Console account/VIP button sits in the user-profile area. Admin report and experimental lab shells retain their own back links.

## Verification

`pytest tests/test_research_lab.py` checks private-network/redirect blocking, evidence quote validation, claim downgrading, membership and quotas. The Basis pipeline has also been exercised against its real Lever page and linked employer homepage with the existing LLM. Browser tests cover selected-post isolation, report rendering and common public navigation ordering.
