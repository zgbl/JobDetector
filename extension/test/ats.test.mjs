/**
 * test/ats.test.mjs — dependency-free unit tests for lib/ats.js.
 *
 * Run with:  node --test extension/test/
 */

import test from 'node:test';
import assert from 'node:assert/strict';

import { identifyAts, cacheKeyFor, unwrapRedirectUrl } from '../lib/ats.js';

test('greenhouse board URL', () => {
  assert.deepEqual(identifyAts('https://boards.greenhouse.io/stripe/jobs/8172487'), {
    ats: 'greenhouse',
    token: 'stripe',
    jobId: '8172487',
  });
});

test('greenhouse job-boards + boards-api variants', () => {
  assert.deepEqual(identifyAts('https://job-boards.greenhouse.io/acme/jobs/123456'), {
    ats: 'greenhouse',
    token: 'acme',
    jobId: '123456',
  });
  assert.deepEqual(identifyAts('https://boards-api.greenhouse.io/v1/boards/acme/jobs/123456'), {
    ats: 'greenhouse',
    token: 'acme',
    jobId: '123456',
  });
});

test('greenhouse gh_jid query param on a company domain', () => {
  assert.deepEqual(identifyAts('https://stripe.com/jobs/search?gh_jid=8172487'), {
    ats: 'greenhouse',
    token: null,
    jobId: '8172487',
  });
  assert.deepEqual(identifyAts('https://example.com/careers?gh_jid=555&for=acme'), {
    ats: 'greenhouse',
    token: 'acme',
    jobId: '555',
  });
});

test('lever', () => {
  assert.deepEqual(identifyAts('https://jobs.lever.co/netflix/abc-123-def'), {
    ats: 'lever',
    token: 'netflix',
    jobId: 'abc-123-def',
  });
  assert.deepEqual(identifyAts('https://api.lever.co/v0/postings/netflix/abc-123-def'), {
    ats: 'lever',
    token: 'netflix',
    jobId: 'abc-123-def',
  });
});

test('ashby', () => {
  assert.deepEqual(identifyAts('https://jobs.ashbyhq.com/openai/9f1f2c3d-4e5a-6789-abcd-ef0123456789'), {
    ats: 'ashby',
    token: 'openai',
    jobId: '9f1f2c3d-4e5a-6789-abcd-ef0123456789',
  });
  assert.deepEqual(identifyAts('https://api.ashbyhq.com/posting-api/job-board/openai'), {
    ats: 'ashby',
    token: 'openai',
    jobId: null,
  });
});

test('workable short code form /j/{code}', () => {
  assert.deepEqual(identifyAts('https://apply.workable.com/j/ABC123DEF'), {
    ats: 'workable',
    token: null,
    jobId: 'ABC123DEF',
  });
});

test('workable account form /{token}/j/{code}', () => {
  assert.deepEqual(identifyAts('https://apply.workable.com/acme/j/ABC123DEF/'), {
    ats: 'workable',
    token: 'acme',
    jobId: 'ABC123DEF',
  });
});

test('smartrecruiters', () => {
  assert.deepEqual(identifyAts('https://jobs.smartrecruiters.com/AcmeCorp/744000012345-senior-engineer'), {
    ats: 'smartrecruiters',
    token: 'AcmeCorp',
    jobId: '744000012345',
  });
});

test('workday without locale prefix', () => {
  assert.deepEqual(identifyAts('https://acme.wd1.myworkdayjobs.com/careers/job/Senior-Engineer_R123'), {
    ats: 'workday',
    token: 'acme',
    jobId: 'job/Senior-Engineer_R123',
  });
});

test('workday with locale prefix', () => {
  assert.deepEqual(identifyAts('https://acme.wd5.myworkdayjobs.com/en-US/careers/job/Senior-Engineer_R123'), {
    ats: 'workday',
    token: 'acme',
    jobId: 'job/Senior-Engineer_R123',
  });
});

test('breezy', () => {
  assert.deepEqual(identifyAts('https://acme.breezy.hr/p/abc123-senior-engineer'), {
    ats: 'breezy',
    token: 'acme',
    jobId: 'abc123-senior-engineer',
  });
});

test('recruitee', () => {
  assert.deepEqual(identifyAts('https://acme.recruitee.com/o/senior-engineer'), {
    ats: 'recruitee',
    token: 'acme',
    jobId: 'senior-engineer',
  });
});

test('unknown URL and empty input', () => {
  assert.deepEqual(identifyAts('https://example.com/jobs/12345'), {
    ats: 'unknown',
    token: null,
    jobId: null,
  });
  assert.deepEqual(identifyAts(''), { ats: 'unknown', token: null, jobId: null });
  assert.deepEqual(identifyAts(null), { ats: 'unknown', token: null, jobId: null });
});

test('cacheKeyFor prefers ats|token|jobId, falls back to normalized URL', () => {
  assert.equal(
    cacheKeyFor(identifyAts('https://jobs.lever.co/netflix/abc-123'), 'https://linkedin.com/jobs/view/1'),
    'lever|netflix|abc-123'
  );
  assert.equal(cacheKeyFor(identifyAts('https://example.com/x'), 'example.com/jobs/1#frag'), 'https://example.com/jobs/1#frag');
});

test('unwrapRedirectUrl unwraps LinkedIn / tracking wrappers', () => {
  assert.equal(
    unwrapRedirectUrl(
      'https://www.linkedin.com/redir/redirect?url=https%3A%2F%2Fjobs.lever.co%2Fpalantir%2Fabc-123&urlhash=x'
    ),
    'https://jobs.lever.co/palantir/abc-123'
  );
  assert.equal(
    unwrapRedirectUrl('https://track.example.com/r?dest=https%3A%2F%2Fjobs.ashbyhq.com%2Fsnowflake%2Fabc'),
    'https://jobs.ashbyhq.com/snowflake/abc'
  );
  // Already an ATS URL → untouched
  assert.equal(
    unwrapRedirectUrl('https://job-boards.greenhouse.io/stripe/jobs/1'),
    'https://job-boards.greenhouse.io/stripe/jobs/1'
  );
  // Unknown wrapper → untouched
  assert.equal(unwrapRedirectUrl('https://www.indeed.com/rc/clk?jk=abc'), 'https://www.indeed.com/rc/clk?jk=abc');
  assert.equal(unwrapRedirectUrl(''), '');
});

test('identifyAts unwraps redirect wrappers before classifying', () => {
  assert.deepEqual(
    identifyAts('https://www.linkedin.com/redir/redirect?url=https%3A%2F%2Fjobs.lever.co%2Fpalantir%2Fabc-123'),
    { ats: 'lever', token: 'palantir', jobId: 'abc-123' }
  );
});
