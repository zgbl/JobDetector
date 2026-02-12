// App State
console.warn('--- JOB DETECTOR MAIN.JS ATTACHED v1.0.3 ---');
let jobs = [];
let companies = [];
let currentCompanyJobs = [];
let filteredJobs = [];
let filteredCompanies = [];
let currentFilters = {
    q: '',
    job_type: '',
    remote_only: false,
    category: '',
    locations: [],
    keywords: [], // Added for multi-tag keyword search
    days: '',
    company: '',
    companies: [],
    favorites_only: false
};
let currentTotalCount = 0;
let currentFilter = 'all';
let currentSearchQuery = '';
let currentCompanySearch = '';
let currentView = 'jobs'; // 'jobs' or 'companies'
let currentUser = null;

// DOM Elements
const jobsGrid = document.getElementById('jobsGrid');
const jobSearch = document.getElementById('jobSearch');
const totalJobsCount = document.getElementById('totalJobsCount');
const companyCount = document.getElementById('companyCount');
const remoteCount = document.getElementById('remoteCount');
const filterBtns = document.querySelectorAll('.filter-btn');
const quickTags = document.querySelectorAll('.tag-btn');
const jobModal = document.getElementById('jobModal');
const authModal = document.getElementById('authModal');
const loginForm = document.getElementById('loginForm');
const registerForm = document.getElementById('registerForm');
const userProfile = document.getElementById('userProfile');
const modalBody = document.getElementById('modalBody');
const navJobs = document.getElementById('navJobs');
const navCompanies = document.getElementById('navCompanies');
const keywordFilter = document.getElementById('keywordFilter');
const categoryFilter = document.getElementById('categoryFilter');
const locationFilter = document.getElementById('locationFilter');
const dateFilter = document.getElementById('dateFilter');
const clearFiltersBtn = document.getElementById('clearFilters');
const locationTagsContainer = document.getElementById('locationTags');
const keywordTagsContainer = document.getElementById('keywordTags');
const filterPills = document.querySelectorAll('.filter-pill');

// Pagination State
let currentPage = 1;
const PAGE_LIMIT = 50;
const paginationContainer = document.getElementById('pagination-container');
const adminPaginationContainer = document.getElementById('admin-pagination-container');
let currentFeedbackPage = 1;
const FEEDBACK_LIMIT = 10;
let feedbackTotalCount = 0;
const jobsSection = document.querySelector('.hero-section').parentNode; // The main dashboard
const companySection = document.getElementById('companySection');
const companiesGrid = document.getElementById('companiesGrid');
const companySearch = document.getElementById('companySearch');
const companyModal = document.getElementById('companyModal');
const companyModalBody = document.getElementById('companyModalBody');
const companyClose = document.querySelector('.company-close');

// We need a better way to target sections
const jobsDashboardParts = [
    document.querySelector('.hero-section'),
    document.querySelector('.filters-section'),
    document.getElementById('jobsGrid')
];

// Init
async function init() {
    console.warn('!!! JOB DETECTOR JS v1.0.3 BOOTING !!!');
    setupEventListeners();

    // Keyword Search Listener moved to setupEventListeners for consolidation

    // Load filters from URL
    loadFiltersFromURL();

    // Check if there's a job ID in URL
    const params = new URLSearchParams(window.location.search);
    const jobId = params.get('jobId');

    // Then fetch data in parallel or sequence, wrapped in try/catch
    try {
        checkAuth();
        updateVisitCount(); // Fire and forget
    } catch (e) {
        console.error('Auth check or visit count failed:', e);
    }

    try {
        await fetchStats();
        await fetchJobs();

        // If jobId in URL, open that job modal
        if (jobId) {
            await showJobDetailsById(jobId);
        }
    } catch (e) {
        console.error('Data loading failed:', e);
    }

    // Check for email verification success
    const verified = params.get('verified');
    if (verified === 'true') {
        alert('Email verified successfully! You can now log in.');
    }

    // Check for password reset success
    const reset = params.get('reset');
    if (reset === 'success') {
        alert('Password reset successful! You can now log in with your new password.');
    }
}

// Forgot Password Handler
document.addEventListener('DOMContentLoaded', () => {
    const forgotPasswordLink = document.getElementById('forgotPasswordLink');
    const forgotPasswordBtn = document.getElementById('forgotPasswordBtn');
    const forgotPasswordModal = document.getElementById('forgotPasswordModal');

    if (forgotPasswordLink) {
        forgotPasswordLink.onclick = (e) => {
            e.preventDefault();
            document.getElementById('authModal').style.display = 'none';
            forgotPasswordModal.style.display = 'block';
        };
    }

    if (forgotPasswordBtn) {
        forgotPasswordBtn.onclick = async () => {
            const email = document.getElementById('forgotEmail').value;

            if (!email) {
                alert('Please enter your email address');
                return;
            }

            forgotPasswordBtn.disabled = true;
            forgotPasswordBtn.textContent = 'Sending...';

            try {
                const response = await fetch('/api/auth/forgot-password', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ email })
                });

                const data = await response.json();

                if (response.ok) {
                    alert('Password reset link sent! Please check your email.');
                    forgotPasswordModal.style.display = 'none';
                    document.getElementById('forgotEmail').value = '';
                } else {
                    alert(data.detail || 'Failed to send reset link');
                }
            } catch (error) {
                alert('An error occurred. Please try again.');
            } finally {
                forgotPasswordBtn.disabled = false;
                forgotPasswordBtn.textContent = 'Send Reset Link';
            }
        };
    }
});

// Fetch Functions
async function fetchStats() {
    try {
        const response = await fetch('/api/stats');
        const stats = await response.json();

        totalJobsCount.textContent = stats.total_jobs || 0;
        companyCount.textContent = stats.company_stats?.length || 0;
        remoteCount.textContent = stats.remote_count || 0;
    } catch (error) {
        console.error('Error fetching stats:', error);
    }
}

async function fetchJobs(page = 1) {
    showLoading();
    currentPage = page;

    // Smooth scroll to top when changing pages
    if (page > 1) {
        window.scrollTo({ top: 0, behavior: 'smooth' });
    }

    try {
        const params = new URLSearchParams();

        // Combine keyword tags and live search query
        let fullQuery = [...currentFilters.keywords];
        if (currentFilters.q && !fullQuery.includes(currentFilters.q)) {
            fullQuery.push(currentFilters.q);
        }

        if (fullQuery.length > 0) {
            params.append('q', fullQuery.join(' '));
        }
        if (currentFilters.job_type) params.append('job_type', currentFilters.job_type);
        if (currentFilters.remote_only) params.append('remote_type', 'Remote');
        if (currentFilters.category) params.append('category', currentFilters.category);

        // Handle multiple locations
        if (currentFilters.locations && currentFilters.locations.length > 0) {
            currentFilters.locations.forEach(loc => params.append('locations', loc));
        }

        if (currentFilters.days) params.append('days', currentFilters.days);
        if (currentFilters.company) params.append('company', currentFilters.company);

        // Pagination params
        const skip = (page - 1) * PAGE_LIMIT;
        params.append('skip', skip);
        params.append('limit', PAGE_LIMIT);

        // Add companies list filter (e.g. from Collections)
        if (currentFilters.companies && currentFilters.companies.length > 0) {
            currentFilters.companies.forEach(c => params.append('companies', c));
        }

        // Handle Favorites Mode
        if (currentFilters.favorites_only) {
            const token = localStorage.getItem('token');
            if (token) {
                try {
                    const favResp = await fetch('/api/user/favorites', {
                        headers: { 'Authorization': `Bearer ${token}` }
                    });
                    if (favResp.ok) {
                        const favorites = await favResp.json();
                        if (favorites.length === 0) {
                            jobs = [];
                            currentTotalCount = 0;
                            updateURL();
                            applyFilterAndRender();
                            return;
                        }
                        const companyNames = favorites.map(f => f.name);
                        companyNames.forEach(c => params.append('companies', c));
                    }
                } catch (e) {
                    console.error('Error handling favorites:', e);
                }
            }
        }

        const response = await fetch(`/api/jobs?${params.toString()}`);
        const data = await response.json();

        if (data && typeof data === 'object' && data.jobs) {
            jobs = data.jobs;
            currentTotalCount = data.total;
        } else {
            jobs = Array.isArray(data) ? data : [];
            currentTotalCount = jobs.length;
        }

        // Update URL
        updateURL();
        applyFilterAndRender();

    } catch (error) {
        console.error('Error fetching jobs:', error);
        jobsGrid.innerHTML = '<div class="error">Failed to load opportunities. Please try again later.</div>';
    }
}

async function fetchCompanies(query = '') {
    currentCompanySearch = query;
    try {
        const url = query ? `/api/companies?q=${encodeURIComponent(query)}` : '/api/companies';
        const response = await fetch(url);
        companies = await response.json();
        renderCompanies();
    } catch (error) {
        console.error('Error fetching companies:', error);
        companiesGrid.innerHTML = '<div class="error-msg">Failed to load companies.</div>';
    }
}

// Render Functions
function applyFilterAndRender() {
    filteredJobs = [...jobs];
    resultsCount.textContent = currentTotalCount || filteredJobs.length;
    renderJobs();
    renderPagination();
}

function renderJobs() {
    if (filteredJobs.length === 0) {
        jobsGrid.innerHTML = '<div class="no-results">No opportunities found matching your criteria.</div>';
        return;
    }

    jobsGrid.innerHTML = filteredJobs.map(job => `
        <div class="job-card glass-card">
            <div class="job-header">
                <div class="company-logo-type" onclick="event.stopPropagation(); showCompanyDetailsByName('${job.company}')" style="cursor: pointer;">${job.company[0]}</div>
                <div class="job-posted">${formatDate(job.posted_date)}</div>
            </div>
            <div onclick="showJobDetails('${job._id}')">
                <h3 class="job-title">${highlightText(job.title, currentSearchQuery)}</h3>
                <div class="job-company" onclick="event.stopPropagation(); showCompanyDetailsByName('${job.company}')">
                    <i class="fas fa-building"></i> ${highlightText(job.company, currentSearchQuery)}
                </div>
                <div class="job-location">
                    <i class="fas fa-map-marker-alt"></i> ${job.location}
                </div>
                <div class="job-meta">
                    <span class="tag blue">${job.job_type}</span>
                    <span class="tag purple">${job.remote_type}</span>
                    ${job.skills.slice(0, 3).map(skill => `<span class="tag">${highlightText(skill, currentSearchQuery)}</span>`).join('')}
                </div>
            </div>
        </div>
    `).join('');
}

function renderPagination() {
    if (currentView !== 'jobs' || !currentTotalCount || currentTotalCount <= PAGE_LIMIT) {
        if (paginationContainer) paginationContainer.style.display = 'none';
        return;
    }

    const totalPages = Math.ceil(currentTotalCount / PAGE_LIMIT);
    if (paginationContainer) paginationContainer.style.display = 'flex';

    let html = '';

    // Previous Button
    html += `<button class="page-btn" ${currentPage === 1 ? 'disabled' : ''} onclick="fetchJobs(${currentPage - 1})">
        <i class="fas fa-chevron-left"></i>
    </button>`;

    // Page numbers logic (show standard sliding window)
    const delta = 2;
    const range = [];
    const rangeWithDots = [];
    let l;

    for (let i = 1; i <= totalPages; i++) {
        if (i == 1 || i == totalPages || i >= currentPage - delta && i <= currentPage + delta) {
            range.push(i);
        }
    }

    for (let i of range) {
        if (l) {
            if (i - l === 2) {
                rangeWithDots.push(l + 1);
            } else if (i - l !== 1) {
                rangeWithDots.push('...');
            }
        }
        rangeWithDots.push(i);
        l = i;
    }

    rangeWithDots.forEach(i => {
        if (i === '...') {
            html += `<span class="pagination-dots">...</span>`;
        } else {
            html += `<button class="page-btn ${i === currentPage ? 'active' : ''}" onclick="fetchJobs(${i})">${i}</button>`;
        }
    });

    // Next Button
    html += `<button class="page-btn" ${currentPage === totalPages ? 'disabled' : ''} onclick="fetchJobs(${currentPage + 1})">
        <i class="fas fa-chevron-right"></i>
    </button>`;

    // Jump to page input
    html += `
        <div class="pagination-jump">
            <span class="jump-label">Page</span>
            <input type="number" 
                   id="jumpPageInput" 
                   class="page-input" 
                   value="${currentPage}" 
                   min="1" 
                   max="${totalPages}"
                   onkeypress="if(event.key === 'Enter') jumpToPage()">
            <span class="jump-total">/ ${totalPages}</span>
            <button class="btn-jump" onclick="jumpToPage()">Go</button>
        </div>
    `;

    paginationContainer.innerHTML = html;
}

function jumpToPage() {
    const input = document.getElementById('jumpPageInput');
    const page = parseInt(input.value);
    const totalPages = Math.ceil(currentTotalCount / PAGE_LIMIT);

    if (page && page >= 1 && page <= totalPages) {
        fetchJobs(page);
    } else {
        alert(`Please enter a valid page number between 1 and ${totalPages}`);
    }
}

function renderCompanies() {
    if (companies.length === 0) {
        companiesGrid.innerHTML = '<div class="no-results">No companies found.</div>';
        return;
    }

    companiesGrid.innerHTML = companies.map(company => {
        const sizeClass = (company.metadata?.size || '').toLowerCase().replace(' ', '-');
        const activeJobs = company.stats?.active_jobs || 0;
        const isSilent = activeJobs === 0;

        return `
            <div class="company-card glass-card ${isSilent ? 'silent' : ''}" onclick="showCompanyDetailsByName('${company.name}')">
                <div class="logo-large">${company.name[0]}</div>
                <h3>${company.name}</h3>
                <div class="domain">${company.domain}</div>
                <div class="company-meta">
                    <span class="badge ${sizeClass}">${company.metadata?.size || 'Unknown Size'}</span>
                    <div style="margin-top: 10px; font-size: 0.8rem; color: var(--text-dim);">
                        ${company.metadata?.industry || ''}
                    </div>
                    <div class="company-job-count ${activeJobs > 0 ? 'active' : 'none'}">
                        <i class="fas fa-briefcase"></i> ${activeJobs} Jobs
                    </div>
                </div>
            </div>
    `;
    }).join('');
}

function showJobDetails(jobId, jobData = null) {
    const job = jobData || jobs.find(j => j._id === jobId);
    if (!job) return;

    // Update URL with job ID
    const newUrl = `${window.location.pathname}?jobId=${jobId}`;
    window.history.pushState({ jobId }, '', newUrl);

    modalBody.innerHTML = `
        <div class="modal-header">
            <div class="job-company" onclick="showCompanyDetailsByName('${job.company}')" style="cursor: pointer; color: var(--accent-blue);">${job.company}</div>
            <h1 class="modal-title">${job.title}</h1>
            <div class="job-meta">
                <span class="tag blue"><i class="fas fa-briefcase"></i> ${job.job_type}</span>
                <span class="tag purple"><i class="fas fa-globe"></i> ${job.remote_type}</span>
                <span class="tag"><i class="fas fa-map-marker-alt"></i> ${job.location}</span>
                <span class="tag gray"><i class="fas fa-calendar-alt"></i> ${formatDate(job.posted_date)}</span>
                <a href="${job.source_url}" target="_blank" class="tag blue">Apply Directly <i class="fas fa-external-link-alt"></i></a>
            </div>
        </div>
        <div class="jd-content">
            ${highlightText(job.description || "No description provided.", currentSearchQuery)}
        </div>
        <div class="skills-section">
            <h4>Extracted Skills</h4>
            <div class="job-meta">
                ${job.skills.map(skill => `<span class="tag">${skill}</span>`).join('')}
            </div>
        </div>
`;
    jobModal.style.display = "block";
    document.body.style.overflow = "hidden"; // Prevent scroll
}

async function showCompanyDetailsByName(companyName) {
    // Hide job modal if it was open
    jobModal.style.display = "none";

    // Fetch company info and jobs
    try {
        // Find company in current list if possible, otherwise we might need a dedicated endpoint
        let company = companies.find(c => c.name === companyName);
        if (!company) {
            const resp = await fetch(`/api/companies?q=${encodeURIComponent(companyName)}`);
            const results = await resp.json();
            company = results.find(c => c.name === companyName);
        }

        if (!company) {
            alert("Company details not found.");
            return;
        }

        const jobsResp = await fetch(`/api/companies/${encodeURIComponent(companyName)}/jobs`);
        currentCompanyJobs = await jobsResp.json();
        const companyJobs = currentCompanyJobs;

        const sizeClass = (company.metadata?.size || '').toLowerCase().replace(' ', '-');

        companyModalBody.innerHTML = `
            <div class="company-header">
                <div class="logo-large" style="margin: 0;">${company.name[0]}</div>
                <div class="company-header-info">
                    <span class="badge ${sizeClass}">${company.metadata?.size || 'Unknown Size'}</span>
                    <h1>${company.name}</h1>
                    <a href="https://${company.domain}" target="_blank" style="color: var(--accent-blue); text-decoration: none;">
                        <i class="fas fa-external-link-alt"></i> ${company.domain}
                    </a>
                </div>
            </div>

            <div class="company-stats-grid">
                <div class="mini-stat-card">
                    <i class="fas fa-layer-group"></i>
                    <strong>${companyJobs.length}</strong>
                    <span>Active Jobs</span>
                </div>
                <div class="mini-stat-card">
                    <i class="fas fa-map-marker-alt"></i>
                    <strong>${company.metadata?.headquarters || 'Remote First'}</strong>
                    <span>Headquarters</span>
                </div>
                <div class="mini-stat-card">
                    <i class="fas fa-industry"></i>
                    <strong>${company.metadata?.industry || 'Technology'}</strong>
                    <span>Industry</span>
                </div>
            </div>

            <div class="company-jobs-list">
                <h3>Open Positions at ${company.name}</h3>
                ${companyJobs.length > 0 ? companyJobs.map(j => `
                    <div class="job-item-compact" onclick="showJobDetailsFromExternal('${j._id}', '${companyName}')" style="cursor: pointer;">
                        <div class="job-info">
                            <h4>${j.title}</h4>
                            <span><i class="fas fa-map-marker-alt"></i> ${j.location}</span>
                        </div>
                        <span class="job-posted">${formatDate(j.posted_date)}</span>
                    </div>
                `).join('') : '<p>No active jobs found for this company.</p>'}
            </div>
        `;

        companyModal.style.display = "block";
        document.body.style.overflow = "hidden";
    } catch (error) {
        console.error("Error showing company details:", error);
    }
}

// Special helper because 'jobs' state might not have all company jobs if they are many
async function showJobDetailsFromExternal(jobId, companyName) {
    companyModal.style.display = "none";

    // Check local states
    let job = jobs.find(j => j._id === jobId) || currentCompanyJobs.find(j => j._id === jobId);

    if (!job) {
        console.error("Job not found in local state:", jobId);
        // Fallback: try to fetch by ID specifically if we had an endpoint, 
        // but for now we rely on the cached currentCompanyJobs.
    }

    if (job) {
        showJobDetails(job._id, job);
    }
}

// Helper to fetch and show job by ID (for direct links)
async function showJobDetailsById(jobId) {
    // First check if job is already in local state
    let job = jobs.find(j => j._id === jobId);

    if (job) {
        showJobDetails(jobId, job);
        return;
    }

    // If not found locally, we need to fetch it from API
    // Since we don't have a direct /api/jobs/:id endpoint, we'll search for it
    try {
        const response = await fetch(`/api/jobs?limit=1000`);
        const data = await response.json();
        const allJobs = data.jobs || data;
        job = allJobs.find(j => j._id === jobId);

        if (job) {
            showJobDetails(jobId, job);
        } else {
            console.error('Job not found:', jobId);
            alert('Job not found or no longer available');
        }
    } catch (error) {
        console.error('Error fetching job:', error);
        alert('Failed to load job details');
    }
}

// Utility Functions
function setupEventListeners() {
    // Search with debounce
    let timeout = null;
    jobSearch.addEventListener('input', (e) => {
        clearTimeout(timeout);
        timeout = setTimeout(() => {
            currentFilters.q = e.target.value;
            fetchJobs(1);
        }, 500);
    });

    // Filters
    filterBtns.forEach(btn => {
        btn.addEventListener('click', () => {
            filterBtns.forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            currentFilter = btn.dataset.filter;
            applyFilterAndRender();
        });
    });

    // Quick Tags
    quickTags.forEach(btn => {
        btn.addEventListener('click', () => {
            const tag = btn.dataset.tag;
            jobSearch.value = tag;
            currentFilters.q = tag;
            fetchJobs(1);
        });
    });

    // Modal Closers (Universal)
    document.querySelectorAll('.close-modal, .auth-close, .company-close, .modal-close').forEach(btn => {
        btn.onclick = function () {
            const modal = this.closest('.modal');
            if (modal) {
                modal.style.display = "none";
                document.body.style.overflow = "auto";

                // Clean up job URL if closing job modal
                if (modal.id === 'jobModal') {
                    const params = new URLSearchParams(window.location.search);
                    if (params.has('jobId')) {
                        params.delete('jobId');
                        const newUrl = params.toString() ? `${window.location.pathname}?${params.toString()}` : window.location.pathname;
                        window.history.pushState({}, '', newUrl);
                    }
                }
            }
        };
    });

    window.onclick = (event) => {
        if (event.target.classList.contains('modal')) {
            event.target.style.display = "none";
            document.body.style.overflow = "auto";

            // Clean up job URL if closing job modal
            if (event.target.id === 'jobModal') {
                const params = new URLSearchParams(window.location.search);
                if (params.has('jobId')) {
                    params.delete('jobId');
                    const newUrl = params.toString() ? `${window.location.pathname}?${params.toString()}` : window.location.pathname;
                    window.history.pushState({}, '', newUrl);
                }
            }
        }
    };

    // Navigation Switching
    navJobs.onclick = (e) => {
        // Allow default navigation to '/'
        // No need to prevent default
    };

    navCompanies.onclick = (e) => {
        // Allow default navigation to '/?view=companies'
        // No need to prevent default
    };

    const companyStatCard = document.getElementById('companyStatCard');
    if (companyStatCard) {
        companyStatCard.onclick = () => window.location.href = '/?view=companies';
    }

    // Company Search
    let companyTimeout = null;
    companySearch.addEventListener('input', (e) => {
        clearTimeout(companyTimeout);
        companyTimeout = setTimeout(() => {
            fetchCompanies(e.target.value);
        }, 500);
    });

    // Auth Listeners
    const showLoginBtn = document.getElementById('showLogin');
    if (showLoginBtn) {
        showLoginBtn.onclick = () => {
            authModal.style.display = "block";
            loginForm.style.display = "block";
            registerForm.style.display = "none";
        };
    }

    /* authClose.onclick handled by universal closer */

    document.getElementById('showRegister').onclick = (e) => {
        e.preventDefault();
        loginForm.style.display = "none";
        registerForm.style.display = "block";
    };

    document.getElementById('showLoginLink').onclick = (e) => {
        e.preventDefault();
        registerForm.style.display = "none";
        loginForm.style.display = "block";
    };

    document.getElementById('loginBtn').onclick = handleLogin;
    document.getElementById('registerBtn').onclick = handleRegister;

    // Advanced Filters (Listeners)
    if (categoryFilter) {
        categoryFilter.onchange = (e) => {
            currentFilters.category = e.target.value;
            fetchJobs();
        };
    }

    // Keyword Filter Sync
    if (keywordFilter) {
        keywordFilter.oninput = (e) => {
            clearTimeout(timeout);
            timeout = setTimeout(() => {
                currentFilters.q = e.target.value;
                currentSearchQuery = e.target.value; // For highlighting
                // Sync with nav search
                if (jobSearch) jobSearch.value = e.target.value;
                currentPage = 1;
                fetchJobs();
            }, 500);
        };

        keywordFilter.onkeydown = (e) => {
            if (e.key === 'Enter') {
                e.preventDefault();
                const val = e.target.value.trim();
                if (val) {
                    addKeywordTag(val);
                    e.target.value = '';
                    currentFilters.q = ''; // Clear live query as it's now a tag
                    fetchJobs();
                } else if (currentFilters.q) {
                    fetchJobs();
                }
            }
        };
    }

    // Keyword Tag Delegation
    if (keywordTagsContainer) {
        keywordTagsContainer.addEventListener('click', (e) => {
            const removeBtn = e.target.closest('.remove-tag');
            if (removeBtn) {
                const keyword = removeBtn.dataset.keyword;
                if (keyword) removeKeywordTag(keyword);
            }
        });
    }

    // Location Filter (Multi-tag interaction)
    if (locationFilter) {
        locationFilter.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') {
                e.preventDefault();
                const val = e.target.value.trim();
                if (val) {
                    addLocationTag(val);
                    e.target.value = '';
                    fetchJobs();
                }
            }
        });

        // Also support picking from datalist via input event
        locationFilter.oninput = (e) => {
            const val = e.target.value.trim();
            const options = document.getElementById('locationOptions').querySelectorAll('option');
            for (let opt of options) {
                if (opt.value === val) {
                    addLocationTag(val);
                    e.target.value = '';
                    fetchJobs();
                    break;
                }
            }
        };
    }

    // Delegation for tag removal (more robust)
    if (locationTagsContainer) {
        locationTagsContainer.addEventListener('click', (e) => {
            console.log('LocationTagsContainer clicked, target:', e.target);
            const removeBtn = e.target.closest('.remove-tag');
            if (removeBtn) {
                const loc = removeBtn.dataset.loc;
                console.log('Remove button detected for:', loc);
                if (loc) removeLocationTag(loc);
            }
        });
    }

    /* locationFilter.onchange replaced by oninput above */

    dateFilter.onchange = (e) => {
        currentFilters.days = e.target.value;
        fetchJobs();
    };

    if (clearFiltersBtn) {
        clearFiltersBtn.onclick = () => {
            currentFilters = {
                q: '',
                job_type: '',
                remote_only: false,
                category: '',
                locations: [],
                keywords: [],
                days: '',
                company: '',
                companies: [],
                favorites_only: false
            };
            if (categoryFilter) categoryFilter.value = '';
            if (locationFilter) locationFilter.value = '';
            if (keywordFilter) keywordFilter.value = '';
            if (dateFilter) dateFilter.value = '';
            if (jobSearch) jobSearch.value = '';
            if (filterPills) filterPills.forEach(p => p.classList.remove('active'));
            const allPill = document.querySelector('.filter-pill[data-filter="all"]');
            if (allPill) allPill.classList.add('active');
            renderLocationTags();
            renderKeywordTags();
            fetchJobs();
        };
    }

    filterPills.forEach(pill => {
        pill.onclick = () => {
            filterPills.forEach(p => p.classList.remove('active'));
            pill.classList.add('active');

            if (pill.dataset.filter === 'all') {
                currentFilters.job_type = '';
                currentFilters.remote_only = false;
            } else if (pill.dataset.toggle === 'job_type') {
                currentFilters.job_type = pill.dataset.value;
            } else if (pill.dataset.toggle === 'remote_only') {
                currentFilters.remote_only = true;
            }
            fetchJobs();
        };
    });

    // Update main search to use global filters
    jobSearch.oninput = (e) => {
        clearTimeout(timeout);
        timeout = setTimeout(() => {
            currentFilters.q = e.target.value;
            // Sync with filter input
            if (keywordFilter) keywordFilter.value = e.target.value;
            fetchJobs();
        }, 500);
    };
}

// Auth Functions
async function checkAuth() {
    const token = localStorage.getItem('token');
    if (!token) return;

    try {
        const response = await fetch('/api/auth/me', {
            headers: { 'Authorization': `Bearer ${token}` }
        });
        if (response.ok) {
            currentUser = await response.json();
            updateAuthUI();
        } else {
            localStorage.removeItem('token');
        }
    } catch (error) {
        console.error('Auth check failed:', error);
    }
}

async function handleLogin(e) {
    if (e) e.preventDefault();
    const email = document.getElementById('loginEmail').value;
    const password = document.getElementById('loginPassword').value;

    try {
        const response = await fetch('/api/auth/login', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ email, password })
        });

        if (response.ok) {
            const data = await response.json();
            localStorage.setItem('token', data.access_token);
            currentUser = data.user;
            authModal.style.display = "none";
            updateAuthUI();
            alert(`Welcome back, ${currentUser.full_name || currentUser.email}!`);
        } else {
            const err = await response.json();
            alert(err.detail || 'Login failed');
        }
    } catch (error) {
        alert('Internal error during login');
    }
}

async function handleRegister(e) {
    if (e) e.preventDefault();
    const email = document.getElementById('regEmail').value;
    const password = document.getElementById('regPassword').value;
    const full_name = document.getElementById('regName').value;

    try {
        const response = await fetch('/api/auth/register', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ email, password, full_name })
        });

        if (response.ok) {
            alert('Registration successful! Please login.');
            registerForm.style.display = "none";
            loginForm.style.display = "block";
        } else {
            const err = await response.json();
            alert(err.detail || 'Registration failed');
        }
    } catch (error) {
        alert('Internal error during registration');
    }
}

function updateAuthUI() {
    const adminLink = document.getElementById('adminNavLink');
    if (currentUser) {
        userProfile.innerHTML = `
            <div class="user-display">
                <div class="avatar">${(currentUser.full_name || currentUser.email || '?')[0].toUpperCase()}</div>
                <div class="user-info">
                    <div class="user-name">${currentUser.full_name || currentUser.email || 'User'}</div>
                    <div class="logout-link" onclick="logout()">Logout</div>
                </div>
            </div>
        `;
        // Show Admin link if user is admin
        if (currentUser.is_admin && adminLink) {
            adminLink.style.display = 'inline-block';
        }
    } else {
        userProfile.innerHTML = `<button class="btn-signin" id="showLogin">Sign In</button>`;
        // Re-attach listener if switched back
        document.getElementById('showLogin').onclick = () => {
            authModal.style.display = "block";
        };
        if (adminLink) adminLink.style.display = 'none';
    }
}

function logout() {
    localStorage.removeItem('token');
    currentUser = null;
    updateAuthUI();
    location.reload(); // Refresh to clear any auth state in memory
}

function switchToView(view) {
    currentView = view;
    const adminNavLink = document.getElementById('adminNavLink');
    const adminSection = document.getElementById('adminSection');

    // Reset all nav items
    navJobs.classList.remove('active');
    navCompanies.classList.remove('active');
    if (adminNavLink) adminNavLink.classList.remove('active');

    // Hide all sections
    jobsDashboardParts.forEach(p => p.style.display = 'none');
    companySection.style.display = 'none';
    if (adminSection) adminSection.style.display = 'none';
    if (paginationContainer) paginationContainer.style.display = 'none';
    if (adminPaginationContainer) adminPaginationContainer.style.display = 'none';

    if (view === 'jobs') {
        navJobs.classList.add('active');
        jobsDashboardParts.forEach(p => p.style.display = 'block');
        applyFilterAndRender();
    } else if (view === 'companies') {
        navCompanies.classList.add('active');
        companySection.style.display = 'block';
        fetchCompanies();
    } else if (view === 'admin') {
        if (adminNavLink) adminNavLink.classList.add('active');
        if (adminSection) adminSection.style.display = 'block';
        currentFeedbackPage = 1;
        fetchAdminFeedbacks(1);
    }
}

function formatDate(dateStr) {
    if (!dateStr) return 'Just now';
    const date = new Date(dateStr);
    const now = new Date();
    const diffTime = Math.abs(now - date);
    const diffHours = Math.floor(diffTime / (1000 * 60 * 60));
    const diffDays = Math.ceil(diffTime / (1000 * 60 * 60 * 24));

    if (diffHours < 1) return 'Just now';
    if (diffHours < 24) return `${diffHours}h ago`;
    if (diffDays <= 7) return `${diffDays}d ago`;
    if (diffDays <= 30) return `${diffDays}d ago`;
    return date.toLocaleDateString();
}

function highlightText(text, query) {
    if (!query || !text) return text;
    const regex = new RegExp(`(${query})`, 'gi');
    return text.toString().replace(regex, '<mark>$1</mark>');
}

function showLoading() {
    jobsGrid.innerHTML = `
        <div class="loading-spinner">
            <i class="fas fa-spinner fa-spin"></i>
            <span>Scanning opportunities...</span>
        </div>
    `;
}

// --- Saved Searches & Alerts ---

function openSaveSearchModal() {
    if (!localStorage.getItem('token')) {
        openAuthModal();
        return;
    }
    document.getElementById('saveSearchModal').style.display = 'flex';
}

async function handleSaveSearch(e) {
    if (e) e.preventDefault();
    const token = localStorage.getItem('token');
    const name = document.getElementById('searchName').value;
    const emailAlert = document.getElementById('emailAlert').checked;

    // Capture current filters
    const searchInput = document.getElementById('jobSearch');
    const criteria = {
        ...currentFilters,
        q: searchInput ? searchInput.value : ''
    };

    try {
        const response = await fetch('/api/user/searches', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${token}`
            },
            body: JSON.stringify({ name, criteria, email_alert: emailAlert })
        });

        if (response.ok) {
            closeModal('saveSearchModal');
            alert('Search saved successfully');
        } else {
            const err = await response.json();
            alert(err.detail || 'Failed to save search');
        }
    } catch (error) {
        console.error('Save search error:', error);
        alert('Network error saving search');
    }
}

async function openSavedSearches() {
    if (!localStorage.getItem('token')) {
        openAuthModal();
        return;
    }

    document.getElementById('savedSearchesModal').style.display = 'flex';
    const listEl = document.getElementById('savedSearchesList');
    listEl.innerHTML = '<div class="loading-spinner"><i class="fas fa-spinner fa-spin"></i> Loading...</div>';

    const token = localStorage.getItem('token');
    try {
        const response = await fetch('/api/user/searches', {
            headers: { 'Authorization': `Bearer ${token}` }
        });

        if (response.ok) {
            const searches = await response.json();
            renderSavedSearches(searches);
        } else {
            listEl.innerHTML = '<div class="error-state">Failed to load searches</div>';
        }
    } catch (error) {
        console.error('Load searches error:', error);
        listEl.innerHTML = '<div class="error-state">Network error</div>';
    }
}

function renderSavedSearches(searches) {
    const listEl = document.getElementById('savedSearchesList');
    if (searches.length === 0) {
        listEl.innerHTML = '<div class="empty-state">No saved searches yet.</div>';
        return;
    }

    listEl.innerHTML = searches.map(s => `
        <div class="saved-search-item glass-card" style="margin-bottom: 1rem; padding: 1rem; display: flex; justify-content: space-between; align-items: center;">
            <div class="search-info">
                <h3 style="margin: 0 0 0.5rem 0; color: white;">${s.name}</h3>
                <div class="search-tags" style="display: flex; gap: 0.5rem; flex-wrap: wrap; margin-bottom: 0.5rem;">
                    ${s.criteria.q ? `<span class="tag small">${s.criteria.q}</span>` : ''}
                    ${s.criteria.location ? `<span class="tag small">${s.criteria.location}</span>` : ''}
                    ${s.criteria.category ? `<span class="tag small">${s.criteria.category}</span>` : ''}
                </div>
                <div class="search-meta" style="font-size: 0.8rem; color: #888;">
                    <label class="toggle-switch" style="display: flex; align-items: center; gap: 0.5rem; cursor: pointer;">
                        <input type="checkbox" ${s.email_alert ? 'checked' : ''} 
                               onchange="toggleSearchAlert('${s.id}', this.checked)">
                        <span>Email Alerts</span>
                    </label>
                </div>
            </div>
            <div class="search-actions" style="display: flex; gap: 0.5rem;">
                <button class="btn-sm btn-primary" onclick='loadSavedSearch(${JSON.stringify(s.criteria).replace(/'/g, "&#39;")})'>Load</button>
                <button class="btn-sm btn-danger" onclick="deleteSavedSearch('${s.id}')" style="background: rgba(255,50,50,0.2); color: #ff5555; border: none; padding: 0.5rem; border-radius: 4px; cursor: pointer;"><i class="fas fa-trash"></i></button>
            </div>
        </div>
    `).join('');
}

async function loadSavedSearch(criteria) {
    // Update global filters
    currentFilters = {
        q: criteria.q || '',
        job_type: criteria.job_type || '',
        remote_only: criteria.remote_only || false,
        location: criteria.location || '',
        category: criteria.category || '',
        location: criteria.location || '',
        category: criteria.category || '',
        days: criteria.days || ''
    };

    // Update new inputs
    const keywordInput = document.getElementById('keywordFilter');
    if (keywordInput) keywordInput.value = currentFilters.q;

    const locInput = document.getElementById('locationFilter');
    if (locInput) locInput.value = currentFilters.location;

    // Update search input
    const searchInput = document.getElementById('jobSearch');
    if (searchInput) searchInput.value = currentFilters.q;

    // Reset pills
    document.querySelectorAll('.filter-pill').forEach(btn => btn.classList.remove('active'));
    if (!currentFilters.job_type && !currentFilters.remote_only) {
        document.querySelector('[data-filter="all"]')?.classList.add('active');
    }
    if (currentFilters.job_type) {
        document.querySelector(`[data-toggle="job_type"][data-value="${currentFilters.job_type}"]`)?.classList.add('active');
    }
    if (currentFilters.remote_only) {
        document.querySelector('[data-toggle="remote_only"]')?.classList.add('active');
    }

    // Update Dropdowns
    /* locSelect handled above */

    const catSelect = document.getElementById('categoryFilter');
    if (catSelect) catSelect.value = currentFilters.category;

    const dateSelect = document.getElementById('dateFilter');
    if (dateSelect) dateSelect.value = currentFilters.days;

    document.getElementById('savedSearchesModal').style.display = 'none';
    document.body.style.overflow = "auto";

    await fetchJobs();
}

async function deleteSavedSearch(id) {
    if (!confirm('Delete this saved search?')) return;

    const token = localStorage.getItem('token');
    try {
        const response = await fetch(`/api/user/searches/${id}`, {
            method: 'DELETE',
            headers: { 'Authorization': `Bearer ${token}` }
        });

        if (response.ok) {
            openSavedSearches(); // Reload list
        }
    } catch (e) {
        console.error('Delete error', e);
    }
}

async function toggleSearchAlert(id, enabled) {
    const token = localStorage.getItem('token');
    try {
        await fetch(`/api/user/searches/${id}`, {
            method: 'PATCH',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${token}`
            },
            body: JSON.stringify({ email_alert: enabled })
        });
    } catch (e) {
        console.error('Toggle alert error', e);
        alert('Failed to update alert setting');
    }
}

// URL Persistence
function updateURL() {
    const params = new URLSearchParams();
    if (currentFilters.q) params.set('q', currentFilters.q);
    if (currentFilters.category) params.set('category', currentFilters.category);
    if (currentFilters.locations && currentFilters.locations.length > 0) {
        params.set('locations', currentFilters.locations.join(','));
    }
    if (currentFilters.keywords && currentFilters.keywords.length > 0) {
        params.set('keywords', currentFilters.keywords.join(','));
    }
    if (currentFilters.days) params.set('days', currentFilters.days);
    if (currentFilters.job_type) params.set('job_type', currentFilters.job_type);
    if (currentFilters.remote_only) params.set('remote_only', 'true');

    const newUrl = `${window.location.pathname}?${params.toString()}`;
    window.history.replaceState({}, '', newUrl);
}

function loadFiltersFromURL() {
    const params = new URLSearchParams(window.location.search);

    // Check for view parameter
    const view = params.get('view');
    if (view === 'companies') {
        switchToView('companies');
    }

    currentFilters.q = params.get('q') || '';
    currentFilters.category = params.get('category') || '';

    // Parse companies list
    const companies = params.getAll('companies');
    if (companies && companies.length > 0) {
        currentFilters.companies = companies;
    }
    // Parse locations (Support both ?locations=A,B and ?locations=A&locations=B)
    const locsParam = params.get('locations');
    let finalLocs = [];
    if (locsParam) {
        finalLocs = locsParam.split(',').map(l => l.trim()).filter(l => l !== '');
    }
    const locsAll = params.getAll('locations');
    if (locsAll.length > 1) {
        locsAll.forEach(l => {
            if (!finalLocs.includes(l.trim())) finalLocs.push(l.trim());
        });
    }
    currentFilters.locations = finalLocs;

    // Parse keywords
    const keywordsParam = params.get('keywords');
    let finalKeywords = [];
    if (keywordsParam) {
        finalKeywords = keywordsParam.split(',').map(k => k.trim()).filter(k => k !== '');
    }
    const keywordsAll = params.getAll('keywords');
    if (keywordsAll.length > 1) {
        keywordsAll.forEach(k => {
            if (!finalKeywords.includes(k.trim())) finalKeywords.push(k.trim());
        });
    }
    currentFilters.keywords = finalKeywords;
    currentFilters.days = params.get('days') || '';
    currentFilters.job_type = params.get('job_type') || '';
    currentFilters.remote_only = params.get('remote_only') === 'true';
    currentFilters.company = params.get('company') || '';
    currentFilters.favorites_only = params.get('favorites') === 'true';

    // Populate UI
    if (keywordFilter) keywordFilter.value = currentFilters.q;
    if (jobSearch && currentFilters.q) jobSearch.value = currentFilters.q;
    if (categoryFilter) categoryFilter.value = currentFilters.category;

    if (locationFilter) {
        locationFilter.value = '';
        renderLocationTags();
    }

    if (keywordFilter) {
        renderKeywordTags();
    }

    if (dateFilter) dateFilter.value = currentFilters.days;

    // Pills
    if (currentFilters.job_type) {
        document.querySelectorAll('.filter-pill').forEach(p => p.classList.remove('active'));
        document.querySelector(`.filter-pill[data-value="${currentFilters.job_type}"]`)?.classList.add('active');
    }
    if (currentFilters.remote_only) {
        document.querySelectorAll('.filter-pill').forEach(p => p.classList.remove('active'));
        document.querySelector(`.filter-pill[data-toggle="remote_only"]`)?.classList.add('active');
    }
}

// Helper for HTML onclicks
function closeModal(modalId) {
    const m = document.getElementById(modalId);
    if (m) {
        m.style.display = 'none';
        document.body.style.overflow = 'auto';
    }
}

async function updateVisitCount() {
    try {
        const response = await fetch('/api/stats/visit', { method: 'POST' });
        const data = await response.json();
        const visitEl = document.getElementById('siteVisits');
        if (visitEl) {
            visitEl.textContent = data.visits.toLocaleString();
        }
    } catch (error) {
        console.error('Failed to update visit count:', error);
    }
}

// Run
init();
// Feedback and Location Tags Implementation


function addLocationTag(loc) {
    if (!currentFilters.locations.includes(loc)) {
        currentFilters.locations.push(loc);
        renderLocationTags();
    }
}

function removeLocationTag(loc) {
    console.log('!!! LOG: Attempting to remove tag:', loc);
    const originalCount = currentFilters.locations.length;
    currentFilters.locations = currentFilters.locations.filter(l => l.toLowerCase() !== loc.toLowerCase());

    if (currentFilters.locations.length === originalCount) {
        console.warn('!!! LOG: Tag not found or already removed:', loc);
    } else {
        console.log('!!! LOG: Tag removed successfully. New list:', currentFilters.locations);
    }

    renderLocationTags();
    updateURL();
    fetchJobs();
}

function renderLocationTags() {
    if (!locationTagsContainer) {
        console.error('!!! LOG: locationTagsContainer is NULL');
        return;
    }

    // No animations, no fancy tricks - just stable HTML
    locationTagsContainer.innerHTML = (currentFilters.locations || []).map(loc => {
        if (!loc) return '';
        return `
            <div class="location-tag">
                <span class="tag-text">${loc}</span>
                <i class="fas fa-times remove-tag" data-loc="${loc}"></i>
            </div>
        `;
    }).join('');

    console.log('!!! LOG: Rendered tags:', currentFilters.locations);
}

function addKeywordTag(keyword) {
    if (!currentFilters.keywords.includes(keyword)) {
        currentFilters.keywords.push(keyword);
        renderKeywordTags();
    }
}

function removeKeywordTag(keyword) {
    currentFilters.keywords = currentFilters.keywords.filter(k => k !== keyword);
    renderKeywordTags();
    fetchJobs();
}

function renderKeywordTags() {
    if (!keywordTagsContainer) return;

    keywordTagsContainer.innerHTML = (currentFilters.keywords || []).map(k => {
        if (!k) return '';
        return `
            <div class="location-tag">
                <span class="tag-text">${k}</span>
                <i class="fas fa-times remove-tag" data-keyword="${k}"></i>
            </div>
        `;
    }).join('');
}

// Ensure they are available globally if needed
window.addLocationTag = addLocationTag;
window.removeLocationTag = removeLocationTag;
window.renderLocationTags = renderLocationTags;
window.addKeywordTag = addKeywordTag;
window.removeKeywordTag = removeKeywordTag;
window.renderKeywordTags = renderKeywordTags;

document.getElementById('submitFeedbackBtn').onclick = async () => {
    const content = document.getElementById('feedbackContent').value;
    const email = document.getElementById('feedbackEmail').value;

    if (!content) {
        alert('Please provide some feedback content');
        return;
    }

    try {
        const token = localStorage.getItem('token');
        const headers = { 'Content-Type': 'application/json' };
        if (token) headers['Authorization'] = `Bearer ${token}`;

        const response = await fetch('/api/feedback', {
            method: 'POST',
            headers: headers,
            body: JSON.stringify({ content, email })
        });

        if (response.ok) {
            alert('Thank you for your feedback!');
            closeModal('feedbackModal');
            document.getElementById('feedbackForm').reset();
        } else {
            const err = await response.json();
            alert(err.detail || 'Failed to submit feedback');
        }
    } catch (e) {
        alert('Error submitting feedback');
    }
};

// Admin Feedback Functions




function exportFeedback() {
    const table = document.querySelector('.feedback-table');
    let csv = [];
    const rows = table.querySelectorAll('tr');

    for (let i = 0; i < rows.length; i++) {
        const row = [], cols = rows[i].querySelectorAll('td, th');
        for (let j = 0; j < cols.length; j++) {
            row.push('"' + cols[j].innerText.replace(/"/g, '""') + '"');
        }
        csv.push(row.join(','));
    }

    const csvFile = new Blob([csv.join('\n')], { type: 'text/csv' });
    const downloadLink = document.createElement('a');
    downloadLink.download = `jobdetector_feedback_${new Date().toISOString().split('T')[0]}.csv`;
    downloadLink.href = window.URL.createObjectURL(csvFile);
    downloadLink.style.display = 'none';
    downloadLink.click();
}

// Admin View Functions
function showAdminView() {
    switchToView('admin');
}

let allFeedbacks = [];

async function fetchAdminFeedbacks(page = 1) {
    currentFeedbackPage = page;
    const list = document.getElementById('adminFeedbackList');
    list.innerHTML = '<div class="glass-card" style="padding: 3rem; text-align: center; color: var(--text-dim);">Loading feedbacks...</div>';

    const token = localStorage.getItem('token');
    try {
        const response = await fetch(`/api/admin/feedbacks?page=${page}&limit=${FEEDBACK_LIMIT}`, {
            headers: { 'Authorization': `Bearer ${token}` }
        });

        if (response.ok) {
            const data = await response.json();
            allFeedbacks = data.feedbacks;
            feedbackTotalCount = data.total;
            renderAdminFeedback(allFeedbacks, feedbackTotalCount);
            renderFeedbackPagination();
        } else {
            list.innerHTML = '<div class="glass-card" style="padding: 3rem; text-align: center; color: #ef4444;">Access denied or failed to load feedbacks.</div>';
        }
    } catch (e) {
        console.error('Error loading feedbacks:', e);
        list.innerHTML = '<div class="glass-card" style="padding: 3rem; text-align: center; color: #ef4444;">Error loading feedbacks.</div>';
    }
}

function renderAdminFeedback(feedbacks, total) {
    const list = document.getElementById('adminFeedbackList');
    if (!feedbacks || feedbacks.length === 0) {
        list.innerHTML = '<div class="glass-card" style="padding: 3rem; text-align: center; color: var(--text-dim);">No feedback found.</div>';
        document.getElementById('totalFeedback').textContent = '0';
        document.getElementById('uniqueUsers').textContent = '0';
        return;
    }

    document.getElementById('totalFeedback').textContent = total || feedbacks.length;
    const uniqueUsersCount = new Set(feedbacks.map(f => f.user_email).filter(e => e)).size;
    document.getElementById('uniqueUsers').textContent = uniqueUsersCount;

    list.innerHTML = feedbacks.map(f => `
        <div class="feedback-card glass-card" id="feedback-${f._id}" style="padding: 2rem; position: relative; animation: fadeIn 0.4s ease-out;">
            <div class="feedback-header" style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 1.5rem;">
                <div class="user-meta" style="display: flex; align-items: center; gap: 1rem;">
                    <div class="avatar" style="width: 40px; height: 40px; background: var(--accent-blue); color: white; display: flex; align-items: center; justify-content: center; border-radius: 50%; font-weight: 700;">
                        ${(f.user_email || 'G')[0].toUpperCase()}
                    </div>
                    <div>
                        <div class="user-email" style="font-weight: 600; color: var(--accent-blue);">${f.user_email || 'Guest Account'}</div>
                        <div class="post-date" style="font-size: 0.8rem; color: var(--text-dim);">${new Date(f.created_at).toLocaleString()}</div>
                    </div>
                </div>
                <div class="feedback-actions">
                    <button class="btn-icon delete-feedback-btn" onclick="deleteFeedback('${f._id}')" title="Delete Feedback" style="background: rgba(239, 68, 68, 0.1); color: #ef4444; border: none; padding: 0.5rem; border-radius: 8px; cursor: pointer; transition: all 0.2s;">
                        <i class="fas fa-trash-alt"></i>
                    </button>
                </div>
            </div>
            <div class="feedback-content" style="font-size: 1.05rem; line-height: 1.7; color: var(--text-light); white-space: pre-wrap; word-wrap: break-word; overflow-wrap: break-word;">${escapeHtml(f.content)}</div>
            ${f.provided_email ? `
            <div class="provided-contact" style="margin-top: 1.5rem; padding-top: 1rem; border-top: 1px solid var(--glass-border); font-size: 0.85rem; color: var(--text-dim);">
                <i class="fas fa-envelope"></i> Contact Provided: <span style="color: var(--accent-blue)">${f.provided_email}</span>
            </div>` : ''}
        </div>
    `).join('');
}

function renderFeedbackPagination() {
    if (!feedbackTotalCount || feedbackTotalCount <= FEEDBACK_LIMIT) {
        if (adminPaginationContainer) adminPaginationContainer.style.display = 'none';
        return;
    }

    const totalPages = Math.ceil(feedbackTotalCount / FEEDBACK_LIMIT);
    if (adminPaginationContainer) adminPaginationContainer.style.display = 'flex';

    let html = '';
    // Simple pagination for feedback
    html += `<button class="page-btn" ${currentFeedbackPage === 1 ? 'disabled' : ''} onclick="fetchAdminFeedbacks(${currentFeedbackPage - 1})">
        <i class="fas fa-chevron-left"></i>
    </button>`;

    for (let i = 1; i <= totalPages; i++) {
        if (i === 1 || i === totalPages || (i >= currentFeedbackPage - 1 && i <= currentFeedbackPage + 1)) {
            html += `<button class="page-btn ${i === currentFeedbackPage ? 'active' : ''}" onclick="fetchAdminFeedbacks(${i})">${i}</button>`;
        } else if (i === currentFeedbackPage - 2 || i === currentFeedbackPage + 2) {
            html += `<span class="page-dots">...</span>`;
        }
    }

    html += `<button class="page-btn" ${currentFeedbackPage === totalPages ? 'disabled' : ''} onclick="fetchAdminFeedbacks(${currentFeedbackPage + 1})">
        <i class="fas fa-chevron-right"></i>
    </button>`;

    adminPaginationContainer.innerHTML = html;
}

async function deleteFeedback(id) {
    if (!confirm('Are you sure you want to delete this feedback?')) return;

    const token = localStorage.getItem('token');
    try {
        const response = await fetch(`/api/admin/feedback/${id}`, {
            method: 'DELETE',
            headers: { 'Authorization': `Bearer ${token}` }
        });

        if (response.ok) {
            const card = document.getElementById(`feedback-${id}`);
            if (card) {
                card.style.opacity = '0';
                card.style.transform = 'translateX(20px)';
                setTimeout(() => {
                    card.remove();
                    // Update stats
                    const totalEl = document.getElementById('totalFeedback');
                    if (totalEl) totalEl.textContent = parseInt(totalEl.textContent) - 1;
                    if (parseInt(totalEl.textContent) === 0) {
                        document.getElementById('adminFeedbackList').innerHTML = '<div class="glass-card" style="padding: 3rem; text-align: center; color: var(--text-dim);">No feedback found.</div>';
                    }
                }, 300);
            }
        } else {
            alert('Failed to delete feedback');
        }
    } catch (e) {
        console.error('Delete error:', e);
        alert('Error deleting feedback');
    }
}
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function exportFeedback() {
    if (allFeedbacks.length === 0) {
        alert('No feedback to export');
        return;
    }

    const headers = ['Date', 'User Email', 'Provided Email', 'Content'];
    const csvRows = [headers.join(',')];

    allFeedbacks.forEach(f => {
        const row = [
            new Date(f.created_at).toLocaleString(),
            f.user_email || 'Guest',
            f.provided_email || '',
            `"${(f.content || '').replace(/"/g, '""')}"`
        ];
        csvRows.push(row.join(','));
    });

    const csvContent = "data:text/csv;charset=utf-8," + csvRows.join("\n");
    const encodedUri = encodeURI(csvContent);
    const link = document.createElement("a");
    link.setAttribute("href", encodedUri);
    link.setAttribute("download", `jobdetector_feedback_${new Date().toISOString().split('T')[0]}.csv`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
}
