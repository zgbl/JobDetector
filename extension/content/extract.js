/**
 * content/extract.js — site adapters for LinkedIn / Indeed job pages.
 *
 * This file is injected as a CLASSIC content script (declared before
 * content.js in manifest.json), so it must not use `import` / `export`.
 * It attaches its public surface to `globalThis.JobDetectorExtract` which the
 * other content scripts in the same isolated world can read.
 *
 * Everything here is defensive: the host DOM changes constantly and an
 * exception raised while scraping must never break the page.
 */
(function () {
  'use strict';

  const ATS_HOST_RE =
    /(?:boards|job-boards|boards-api)\.greenhouse\.io|(?:jobs|api|hire)\.lever\.co|(?:jobs\.ashbyhq\.com|api\.ashbyhq\.com)|(?:apply|jobs)\.workable\.com|(?:jobs|careers|api)\.smartrecruiters\.com|\.(?:wd\d+)\.myworkdayjobs\.com|\.breezy\.hr|\.recruitee\.com|\.jobs\.personio\.(?:de|com)|\.teamtailor\.com/i;

  const MAX_URLS = 40;
  const MAX_ATTR_ELEMENTS = 5000;

  /** Query params used by LinkedIn/Indeed to wrap an outbound apply link. */
  const REDIRECT_PARAMS = ['url', 'u', 'target', 'redirect', 'redirect_url', 'dest', 'destination', 'to'];

  /**
   * LinkedIn wraps external apply links as
   * `/redir/redirect?url=https%3A%2F%2Fjobs.lever.co%2F...`; Indeed uses
   * `/rc/clk?jk=...`. Unwrap the first form so the ATS host becomes visible.
   */
  function unwrapEmbeddedUrl(rawUrl) {
    if (!rawUrl || typeof rawUrl !== 'string') return rawUrl;
    if (ATS_HOST_RE.test(rawUrl)) return rawUrl;
    let parsed = null;
    try {
      parsed = new URL(rawUrl, location.href);
    } catch {
      return rawUrl;
    }
    for (const key of REDIRECT_PARAMS) {
      let value = null;
      try {
        value = parsed.searchParams.get(key);
      } catch {
        value = null;
      }
      if (!value) continue;
      let candidate = value;
      try {
        candidate = decodeURIComponent(value);
      } catch {
        candidate = value;
      }
      if (/^https?:\/\//i.test(candidate)) return candidate;
    }
    return rawUrl;
  }

  function textOf(el) {
    if (!el) return '';
    const value = el.textContent;
    return value ? value.replace(/\s+/g, ' ').trim() : '';
  }

  function firstText(selectors) {
    for (const selector of selectors) {
      let nodes;
      try {
        nodes = document.querySelectorAll(selector);
      } catch {
        continue;
      }
      for (const node of nodes) {
        const value = textOf(node);
        if (value) return value;
      }
    }
    return '';
  }

  function firstElement(selectors) {
    for (const selector of selectors) {
      let node = null;
      try {
        node = document.querySelector(selector);
      } catch {
        node = null;
      }
      if (node) return node;
    }
    return null;
  }

  function absolutize(href, base) {
    if (!href || typeof href !== 'string') return '';
    const raw = href.trim();
    if (!raw || raw.startsWith('#') || /^(javascript|mailto|tel|data|blob):/i.test(raw)) return '';
    try {
      return new URL(raw, base || location.href).href;
    } catch {
      return '';
    }
  }

  function pushUrl(bucket, seen, url) {
    if (!url || bucket.length >= MAX_URLS) return;
    const normalized = unwrapEmbeddedUrl(url).split('#')[0];
    if (!normalized || seen.has(normalized)) return;
    seen.add(normalized);
    bucket.push(normalized);
  }

  /** Pull `https://...` strings out of embedded JSON / inline scripts. */
  function scanEmbeddedJson(bucket, seen) {
    let scripts;
    try {
      scripts = document.querySelectorAll('script:not([src])');
    } catch {
      return;
    }
    const re = /https?:\\?\/\\?\/[^\s"'<>\\)\]]+/g;
    let scanned = 0;
    for (const script of scripts) {
      if (scanned > 60) break;
      scanned += 1;
      const raw = script.textContent;
      if (!raw || raw.length > 400000) continue;
      if (!ATS_HOST_RE.test(raw)) continue;
      const matches = raw.match(re);
      if (!matches) continue;
      for (const match of matches) {
        const cleaned = match
          .replace(/\\\//g, '/')
          .replace(/\\u0026/gi, '&')
          .replace(/&amp;/g, '&')
          .replace(/[",]+$/, '');
        if (ATS_HOST_RE.test(cleaned)) pushUrl(bucket, seen, absolutize(cleaned));
      }
    }
  }

  /** Pull ATS URLs out of `data-*` / `href` attributes (Apply button payloads). */
  function scanDataAttributes(bucket, seen) {
    let elements;
    try {
      elements = document.querySelectorAll('a[href], [data-apply-url], [data-url], [data-job-url], [data-external-url], [data-applylink]');
    } catch {
      return;
    }
    let scanned = 0;
    for (const el of elements) {
      if (scanned > MAX_ATTR_ELEMENTS) break;
      scanned += 1;
      let attrs;
      try {
        attrs = el.attributes;
      } catch {
        continue;
      }
      for (const attr of attrs) {
        const value = attr.value;
        if (!value || value.length > 2000) continue;
        if (!ATS_HOST_RE.test(value)) continue;
        const candidate = value.trim().startsWith('http') ? value.trim() : value;
        const url = absolutize(candidate, location.href);
        if (url) pushUrl(bucket, seen, url);
      }
    }
  }

  /** All outbound links whose host looks like an ATS. */
  function scanAnchors(bucket, seen) {
    let anchors;
    try {
      anchors = document.querySelectorAll('a[href]');
    } catch {
      return;
    }
    for (const anchor of anchors) {
      const href = anchor.getAttribute('href') || '';
      if (!href || !ATS_HOST_RE.test(href)) {
        // relative hrefs: absolutize first, then test
        const abs = absolutize(href, location.href);
        if (!abs || !ATS_HOST_RE.test(abs)) continue;
        pushUrl(bucket, seen, abs);
        continue;
      }
      pushUrl(bucket, seen, absolutize(href, location.href));
    }
  }

  /** Indeed-specific outbound apply links. */
  function scanIndeedApply(bucket, seen) {
    const selectors = [
      '#applyButtonLinkContainer a',
      'a[href*="apply"]',
      '[data-testid="applyButtonLinkContainer"] a',
      'a[data-testid="jobsearch-CompanyInfoContainer-applyLink"]',
    ];
    for (const selector of selectors) {
      let nodes;
      try {
        nodes = document.querySelectorAll(selector);
      } catch {
        continue;
      }
      for (const node of nodes) {
        const href = node.getAttribute('href') || '';
        const abs = absolutize(href, location.href);
        if (abs) pushUrl(bucket, seen, abs);
      }
    }
  }

  function collectAtsUrls() {
    const bucket = [];
    const seen = new Set();
    try {
      scanAnchors(bucket, seen);
      scanDataAttributes(bucket, seen);
      scanEmbeddedJson(bucket, seen);
      if (detectSite() === 'indeed') scanIndeedApply(bucket, seen);
    } catch {
      /* ignore: partial results are still useful */
    }
    return bucket.filter((url) => ATS_HOST_RE.test(url));
  }

  /** All outbound hrefs on the page (ATS ones first). */
  function collectAllUrls() {
    const bucket = [];
    const seen = new Set();
    try {
      for (const anchor of document.querySelectorAll('a[href]')) {
        const abs = absolutize(anchor.getAttribute('href') || '', location.href);
        if (abs) pushUrl(bucket, seen, abs);
      }
    } catch {
      /* ignore */
    }
    const ats = collectAtsUrls();
    return ats.concat(bucket.filter((u) => !ats.includes(u)));
  }

  function detectSite() {
    const host = (location.hostname || '').toLowerCase();
    if (/(^|\.)linkedin\.com$/.test(host)) return 'linkedin';
    if (/(^|\.)indeed\.com$/.test(host)) return 'indeed';
    return 'unknown';
  }

  function isSupportedPage(site) {
    const path = location.pathname || '';
    if (site === 'linkedin') {
      return /^\/jobs\/(view|search|collections)/.test(path);
    }
    if (site === 'indeed') {
      return /\/viewjob/.test(path) || /[?&]vjs=/.test(location.search) || /[?&]jk=/.test(location.search);
    }
    return false;
  }

  /** Stable per-job key used to avoid re-running on the same posting. */
  function jobKey(site) {
    try {
      if (site === 'linkedin') {
        const view = (location.pathname || '').match(/\/jobs\/view\/(\d+)/);
        if (view) return `linkedin:${view[1]}`;
        const param = new URLSearchParams(location.search).get('currentJobId');
        if (param) return `linkedin:${param}`;
        return `linkedin:${location.pathname}${location.search}`;
      }
      if (site === 'indeed') {
        const jk = new URLSearchParams(location.search).get('jk');
        if (jk) return `indeed:${jk}`;
        const view = (location.pathname || '').match(/\/viewjob\/([^/]+)/);
        if (view) return `indeed:${view[1]}`;
        return `indeed:${location.pathname}${location.search}`;
      }
    } catch {
      /* fall through */
    }
    return `${site}:${location.href}`;
  }

  const LINKEDIN_TITLE = [
    '.job-details-jobs-unified-top-card__job-title h1',
    '.job-details-jobs-unified-top-card__job-title',
    '.jobs-unified-top-card__job-title',
    '.jobs-details-top-card__job-title',
    'h1.t-24',
    'h1',
  ];
  const LINKEDIN_COMPANY = [
    '.job-details-jobs-unified-top-card__company-name a',
    '.job-details-jobs-unified-top-card__company-name',
    '.jobs-unified-top-card__company-name a',
    '.jobs-unified-top-card__company-name',
    '.job-details-jobs-unified-top-card__primary-description a',
  ];
  const LINKEDIN_LOCATION = [
    '.job-details-jobs-unified-top-card__bullet',
    '.jobs-unified-top-card__bullet',
    '.job-details-jobs-unified-top-card__primary-description-container .tvm__text',
    '.job-details-jobs-unified-top-card__workplace-type',
  ];
  const LINKEDIN_JD = [
    '.jobs-description__content',
    '.jobs-box__html-content',
    '#job-details',
    '.jobs-description-content__text',
  ];

  const INDEED_TITLE = [
    '[data-testid="jobsearch-JobInfoHeader-title"]',
    'h1.jobsearch-JobInfoHeader-title',
    'h2.jobsearch-JobInfoHeader-title',
    '.jobsearch-JobInfoHeader-title',
    'h1',
  ];
  const INDEED_COMPANY = [
    '[data-testid="inlineHeader-companyName"] a',
    '[data-testid="inlineHeader-companyName"]',
    '.jobsearch-CompanyInfoContainer a',
    '.jobsearch-InlineCompanyRating a',
  ];
  const INDEED_LOCATION = [
    '[data-testid="inlineHeader-companyLocation"]',
    '[data-testid="jobsearch-JobInfoHeader-companyLocation"]',
    '.jobsearch-JobInfoHeader-companyLocation',
  ];
  const INDEED_JD = ['#jobDescriptionText', '.jobsearch-JobComponent-description'];

  /** Try to read "3 days ago" style posting age out of the top card. */
  function postAgeDays(site) {
    const scope = firstElement(
      site === 'linkedin'
        ? ['.job-details-jobs-unified-top-card__tertiary-description-container', '.jobs-unified-top-card__subtitle-primary-grouping', '.jobs-details-top-card']
        : ['[data-testid="jobsearch-JobInfoHeader-companyLocation"]', '.jobsearch-JobMetadataHeader-item', '.jobsearch-JobInfoHeader-subtitle']
    );
    const text = textOf(scope) || '';
    if (!text) return null;
    const en = text.match(/(\d+)\s*(day|week|month|hour)s?\s+ago/i);
    if (en) {
      const n = Number(en[1]);
      const unit = en[2].toLowerCase();
      if (unit === 'hour') return Math.floor(n / 24);
      if (unit === 'day') return n;
      if (unit === 'week') return n * 7;
      if (unit === 'month') return n * 30;
    }
    const zh = text.match(/(\d+)\s*(天|周|个月|小时)前/);
    if (zh) {
      const n = Number(zh[1]);
      if (zh[2] === '小时') return Math.floor(n / 24);
      if (zh[2] === '天') return n;
      if (zh[2] === '周') return n * 7;
      if (zh[2] === '个月') return n * 30;
    }
    return null;
  }

  function extractJob() {
    const site = detectSite();
    let title = '';
    let company = '';
    let jobLocation = '';
    let jdText = '';
    try {
      if (site === 'linkedin') {
        title = firstText(LINKEDIN_TITLE);
        company = firstText(LINKEDIN_COMPANY);
        jobLocation = firstText(LINKEDIN_LOCATION);
        jdText = firstText(LINKEDIN_JD);
      } else if (site === 'indeed') {
        title = firstText(INDEED_TITLE);
        company = firstText(INDEED_COMPANY);
        jobLocation = firstText(INDEED_LOCATION);
        jdText = firstText(INDEED_JD);
      }
      if (!title) {
        const meta = document.querySelector('meta[property="og:title"]');
        title = (meta && meta.getAttribute('content')) || document.title || '';
      }
    } catch {
      /* keep whatever we have */
    }

    // LinkedIn appends " | Company | LinkedIn" to document.title
    title = title.replace(/\s*\|\s*LinkedIn\s*$/i, '').trim();
    company = company.replace(/\s*\|\s*LinkedIn\s*$/i, '').trim();

    return {
      site,
      supported: isSupportedPage(site),
      key: jobKey(site),
      title: title.slice(0, 300),
      company: company.slice(0, 300),
      location: jobLocation.slice(0, 300),
      jdText: jdText.slice(0, 6000),
      postAgeDays: postAgeDays(site),
      urls: collectAllUrls(),
      atsUrls: collectAtsUrls(),
    };
  }

  /** Element the badge should sit next to (the job title on both sites). */
  function findBadgeAnchor(site) {
    return firstElement(
      site === 'linkedin'
        ? [
            '.job-details-jobs-unified-top-card__job-title',
            '.jobs-unified-top-card__job-title',
            '.jobs-details-top-card__job-title',
          ]
        : [
            '[data-testid="jobsearch-JobInfoHeader-title"]',
            'h1.jobsearch-JobInfoHeader-title',
            'h2.jobsearch-JobInfoHeader-title',
            '.jobsearch-JobInfoHeader-title',
          ]
    );
  }

  globalThis.JobDetectorExtract = {
    ATS_HOST_RE,
    detectSite,
    isSupportedPage,
    extractJob,
    collectAtsUrls,
    collectAllUrls,
    findBadgeAnchor,
    jobKey,
    unwrapEmbeddedUrl,
  };
})();
