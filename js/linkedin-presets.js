// LinkedIn URL builder. Search catalog is served by the access-controlled API.
export function buildLinkedInUrl(query, destination = 'posts', location = 'any', date = 'week') {
  const locationTerms = { any: '', us: ' "United States"', ny: ' ("New York" OR "New Jersey")', remote: ' (remote OR distributed)' };
  if (!(location in locationTerms)) throw new Error('Unknown location');
  const dateFilters = { all: null, day: ['past-24h', 'r86400'], week: ['past-week', 'r604800'], month: ['past-month', 'r2592000'] };
  if (!Object.hasOwn(dateFilters, date)) throw new Error('Unknown date range');
  const url = new URL(destination === 'jobs'
    ? 'https://www.linkedin.com/jobs/search/'
    : 'https://www.linkedin.com/search/results/content/');
  url.searchParams.set('keywords', query + locationTerms[location]);
  if (dateFilters[date]) {
    url.searchParams.set(destination === 'jobs' ? 'f_TPR' : 'datePosted',
      destination === 'jobs' ? dateFilters[date][1] : JSON.stringify(dateFilters[date][0]));
  }
  return url.toString();
}
