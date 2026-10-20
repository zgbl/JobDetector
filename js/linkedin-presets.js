// Search terms are intentionally stored in source: this page works without an account or setup.
// A query is a keyword search, never a promise about LinkedIn's result ranking.
export const GROUPS = [
  { id: 'fde', name: 'Forward Deployed Engineer', short: 'FDE', description: 'Embedded engineering and customer-facing AI roles', items: [
    ['exact', 'Exact title', '"Forward Deployed Engineer"'],
    ['hyphen', 'Hyphenated title', '"Forward-Deployed Engineer"'],
    ['broad', 'Broad FDE', '"Forward Deployed" engineer'],
    ['ai', 'FDE + AI', '"Forward Deployed Engineer" AI'],
    ['startup', 'FDE + startup', '"Forward Deployed Engineer" startup'],
    ['hiring', 'FDE hiring posts', '"Forward Deployed Engineer" hiring']
  ] },
  { id: 'applied', name: 'Applied AI & Engineering', short: 'Applied AI', description: 'Application, agent, RAG, and senior engineering roles', items: [
    ['applied', 'Applied AI Engineer', '"Applied AI Engineer"'],
    ['applied-hiring', 'Applied AI hiring', '"Applied AI Engineer" hiring'],
    ['ai', 'AI Engineer hiring', '"AI Engineer" hiring'],
    ['senior', 'Senior AI Engineer', '"Senior AI Engineer" hiring'],
    ['staff', 'Staff AI Engineer', '"Staff AI Engineer" hiring'],
    ['genai', 'Generative AI Engineer', '"Generative AI Engineer" hiring'],
    ['llm', 'LLM Engineer', '"LLM Engineer" hiring'],
    ['llm-app', 'LLM Application Engineer', '"LLM Application Engineer" hiring'],
    ['agent', 'AI Agent Engineer', '"AI Agent Engineer" hiring'],
    ['agentic', 'Agentic AI Engineer', '"Agentic AI Engineer" hiring'],
    ['rag', 'RAG Engineer', '"RAG Engineer" hiring'],
    ['software', 'AI Software Engineer', '"AI Software Engineer" hiring']
  ] },
  { id: 'platform', name: 'AI Platform & Infrastructure', short: 'AI Platform', description: 'Infrastructure, inference, GPU, and MLOps', items: [
    ['ai-platform', 'AI Platform Engineer', '"AI Platform Engineer" hiring'],
    ['ml-platform', 'ML Platform Engineer', '"ML Platform Engineer" hiring'],
    ['llm-platform', 'LLM Platform Engineer', '"LLM Platform Engineer" hiring'],
    ['ai-infra', 'AI Infrastructure Engineer', '"AI Infrastructure Engineer" hiring'],
    ['ml-infra', 'ML Infrastructure Engineer', '"ML Infrastructure Engineer" hiring'],
    ['ml-machine', 'Machine Learning Platform', '"Machine Learning Platform" engineer hiring'],
    ['inference', 'Inference Infrastructure', '"Inference Infrastructure" engineer hiring'],
    ['gpu', 'GPU Infrastructure', '"GPU Infrastructure" engineer hiring'],
    ['systems', 'AI Systems Engineer', '"AI Systems Engineer" hiring'],
    ['mlops', 'MLOps Engineer', '"MLOps Engineer" hiring']
  ] },
  { id: 'architect', name: 'AI Solutions Architecture', short: 'Architecture', description: 'Cloud, generative AI, and technical consulting', items: [
    ['solutions', 'AI Solutions Architect', '"AI Solutions Architect" hiring'],
    ['genai', 'Generative AI Architect', '"Generative AI Architect" hiring'],
    ['ai', 'AI Architect', '"AI Architect" hiring'],
    ['cloud', 'Cloud AI Architect', '"Cloud AI Architect" hiring'],
    ['cloud-solutions', 'AI Cloud Solutions Architect', '"AI Cloud Solutions Architect" hiring'],
    ['genai-solutions', 'Generative AI Solutions', '"Generative AI Solutions" hiring'],
    ['consultant', 'AI Technical Consultant', '"AI Technical Consultant" hiring'],
    ['forward', 'AI Forward Deployed', '"AI Forward Deployed" engineer']
  ] },
  { id: 'founder', name: 'Startup Founders Hiring', short: 'Founders', description: 'Posts with founder and early-team context', items: [
    ['founder', 'Founder hiring AI', '"founder" "AI engineer" hiring'],
    ['cto', 'CTO hiring AI', '"CTO" "AI engineer" hiring'],
    ['cofounder', 'Co-founder hiring AI', '"co-founder" "AI engineer" hiring'],
    ['founding-ai', 'Founding engineer + AI', '"founding engineer" AI'],
    ['founding-hiring', 'Founding engineer hiring', '"founding engineer" hiring'],
    ['first', 'First engineer at AI startup', '"first engineer" startup AI'],
    ['we', 'We are hiring AI', '"we are hiring" AI engineer'],
    ['im', "I'm hiring AI", '"I\'m hiring" AI engineer'],
    ['join', 'Join our AI team', '"join our team" AI engineer'],
    ['building', 'Building an AI team', '"building our team" AI'],
    ['looking', 'Looking for AI engineer', '"looking for an engineer" AI'],
    ['early', 'Early-stage AI startup', '"early-stage startup" AI engineer']
  ] },
  { id: 'leaders', name: 'Recruiters & Engineering Leaders', short: 'People', description: 'Find direct hiring contacts and team leads', items: [
    ['recruiter-ai', 'Technical recruiter + AI', '"Technical Recruiter" AI engineer'],
    ['recruiter-fde', 'Technical recruiter + FDE', '"Technical Recruiter" "Forward Deployed"'],
    ['talent', 'Talent acquisition + AI', '"Talent Acquisition" AI engineer'],
    ['head-eng', 'Head of Engineering', '"Head of Engineering" AI hiring'],
    ['vp-eng', 'VP Engineering', '"VP Engineering" AI hiring'],
    ['manager', 'Engineering Manager + AI', '"Engineering Manager" "AI Engineer"'],
    ['director', 'Director of Engineering', '"Director of Engineering" AI hiring'],
    ['head-ai', 'Head of AI', '"Head of AI" hiring engineer'],
    ['startup', 'AI hiring at startup', '"AI hiring" startup'],
    ['team', 'Engineering team hiring', '"engineering team" AI hiring']
  ] },
  { id: 'agents', name: 'Agents, RAG & Production AI', short: 'Agents & RAG', description: 'Production systems and enterprise AI applications', items: [
    ['agents', 'AI agents', '"AI agents" engineer hiring'],
    ['agentic', 'Agentic AI', '"agentic AI" engineer hiring'],
    ['rag', 'RAG engineering', '"RAG" engineer hiring'],
    ['apps', 'LLM applications', '"LLM applications" engineer hiring'],
    ['production', 'Production AI', '"production AI" engineer hiring'],
    ['platform', 'Startup AI platform', '"AI platform" startup hiring'],
    ['enterprise', 'Enterprise AI', '"enterprise AI" engineer hiring'],
    ['deployment', 'AI deployment', '"AI deployment" engineer hiring'],
    ['systems', 'AI production systems', '"AI production systems" engineer'],
    ['inference', 'LLM inference', '"LLM inference" engineer hiring']
  ] },
  { id: 'cloud', name: 'Cloud & Backend', short: 'Cloud / Backend', description: 'Adjacent roles aligned with your infrastructure background', items: [
    ['architect', 'Cloud Architect + AI', '"Cloud Architect" AI hiring'],
    ['infra', 'Cloud Infrastructure Engineer', '"Cloud Infrastructure Engineer" AI'],
    ['platform', 'Platform Engineer + AI', '"Platform Engineer" AI hiring'],
    ['staff', 'Staff Software Engineer', '"Staff Software Engineer" AI platform'],
    ['principal', 'Principal Engineer', '"Principal Engineer" AI infrastructure'],
    ['backend', 'Backend Engineer + LLM', '"Backend Engineer" LLM hiring'],
    ['python', 'Python Engineer + AI', '"Python Engineer" AI hiring'],
    ['distributed', 'Distributed Systems Engineer', '"Distributed Systems Engineer" AI'],
    ['native', 'Cloud Native + AI', '"Cloud Native" AI engineer'],
    ['devops', 'DevOps Engineer + AI', '"DevOps Engineer" AI platform']
  ] }
];

export const SIGNALS = [
  ['we', 'We are hiring', '"We are hiring" AI engineer', 'AI engineer'],
  ['im', "I'm hiring", '"I\'m hiring" AI engineer', 'AI engineer'],
  ['were', "We're hiring", '"We\'re hiring" AI', 'AI'],
  ['join', 'Join our team', '"Join our team" AI engineer', 'AI engineer'],
  ['looking', 'Looking for an engineer', '"Looking for an engineer" AI', 'AI engineer'],
  ['now', 'Hiring now', '"Hiring now" AI engineer', 'AI engineer'],
  ['building', 'Building our engineering team', '"Building our engineering team" AI', 'AI engineering team'],
  ['first', 'First engineering hire', '"First engineering hire" AI', 'AI startup engineer'],
  ['founding', 'Founding engineer', '"Founding engineer" AI startup', 'AI startup engineer'],
  ['dm', 'DM me', '"DM me" AI engineer', 'AI engineer']
].map(([id, label, query, broadQuery]) => ({ id: `signal-${id}`, label, query, broadQuery, category: 'signals', destination: 'both', note: 'Explicit hiring language; broaden removes the phrase.' }));

export const PRESETS = GROUPS.flatMap(group => group.items.map(([id, label, query]) => ({
  id: `${group.id}-${id}`, label, query, category: group.id, destination: 'both',
  note: group.description
})));

export const ALL_PRESETS = [...PRESETS, ...SIGNALS];

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
