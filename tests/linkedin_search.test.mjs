import test from 'node:test';
import assert from 'node:assert/strict';
import { GROUPS, PRESETS, SIGNALS, ALL_PRESETS, buildLinkedInUrl } from '../js/linkedin-presets.js';

test('all requested groups and direct hiring signals are ready to use', () => {
  assert.deepEqual(GROUPS.map(group => group.items.length), [6, 12, 10, 8, 12, 10, 10, 10]);
  assert.equal(PRESETS.length, 78);
  assert.equal(SIGNALS.length, 10);
  assert.equal(new Set(ALL_PRESETS.map(preset => preset.id)).size, ALL_PRESETS.length);
  for (const preset of ALL_PRESETS) {
    assert.ok(preset.label && preset.query && preset.category, preset.id);
  }
  for (const signal of SIGNALS) assert.ok(signal.broadQuery && signal.broadQuery !== signal.query);
});

test('every preset produces a correctly encoded LinkedIn URL in both modes', () => {
  for (const destination of ['posts', 'jobs']) {
    const urls = ALL_PRESETS.map(preset => buildLinkedInUrl(preset.query, destination));
    // The brief intentionally repeats “I'm hiring” in both Founders and Direct Hiring Signals.
    assert.equal(new Set(urls).size, urls.length - 1);
    for (let i = 0; i < urls.length; i += 1) {
      const url = new URL(urls[i]);
      assert.equal(url.origin, 'https://www.linkedin.com');
      assert.equal(url.pathname, destination === 'posts' ? '/search/results/content/' : '/jobs/search/');
      assert.equal(url.searchParams.get('keywords'), ALL_PRESETS[i].query);
      assert.deepEqual([...url.searchParams.keys()], ['keywords']);
    }
  }
});

test('location shortcuts add explicit keywords without fabricating LinkedIn filters', () => {
  assert.equal(new URL(buildLinkedInUrl('"AI Engineer" hiring', 'posts', 'ny')).searchParams.get('keywords'), '"AI Engineer" hiring ("New York" OR "New Jersey")');
  assert.equal(new URL(buildLinkedInUrl('"AI Engineer" hiring', 'jobs', 'remote')).searchParams.get('keywords'), '"AI Engineer" hiring (remote OR distributed)');
  assert.throws(() => buildLinkedInUrl('AI', 'posts', 'made-up'));
});
