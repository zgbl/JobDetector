// App State
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
    location: '',
    days: '',
    company: '',
    favorites_only: false
};
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
// const closeModal = document.querySelector('.close-modal'); // Removed to avoid conflict
// const authClose = document.querySelector('.auth-close'); // Consolidation

// New Elements
const navJobs = document.getElementById('navJobs');
const navCompanies = document.getElementById('navCompanies');
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
    // Setup listeners first so UI remains responsive even if data loads slow/fails
    // Setup listeners first so UI remains responsive even if data loads slow/fails
    setupEventListeners();

    // Load filters from URL
    loadFiltersFromURL();

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
    } catch (e) {
        console.error('Data loading failed:', e);
    }
}

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

async function fetchJobs() {
    showLoading();
    try {
        const params = new URLSearchParams();
        if (currentFilters.q) params.append('q', currentFilters.q);
        if (currentFilters.job_type) params.append('job_type', currentFilters.job_type);
        if (currentFilters.remote_only) params.append('remote_type', 'Remote');
        if (currentFilters.category) params.append('category', currentFilters.category);
        if (currentFilters.location) params.append('location', currentFilters.location);
        if (currentFilters.days) params.append('days', currentFilters.days);
        if (currentFilters.company) params.append('company', currentFilters.company);

        // Handle Favorites Mode
        if (currentFilters.favorites_only) {
            console.log("DEBUG: Favorites mode active. Token check...");
            const token = localStorage.getItem('token');
            if (token) {
                try {
                    const favResp = await fetch('/api/user/favorites', {
                        headers: { 'Authorization': `Bearer ${token}` }
                    });
                    console.log("DEBUG: Favorites API response status:", favResp.status);

                    if (favResp.ok) {
                        const favorites = await favResp.json();
                        console.log("DEBUG: Favorites fetched:", favorites);

                        if (favorites.length === 0) {
                            console.log("DEBUG: No favorites found. Clearing jobs.");
                            // User has no favorites, show empty state immediately and return
                            jobs = [];
                            updateURL();
                            applyFilterAndRender();
                            return;
                        }
                        const companyNames = favorites.map(f => f.name);
                        // Append each company as a separate 'companies' parameter
                        companyNames.forEach(c => params.append('companies', c));
                        console.log("DEBUG: Companies appended to params:", params.getAll('companies'));
                    }
                } catch (e) {
                    console.error('Error fetching favorites for filter:', e);
                }
            } else {
                console.log("DEBUG: No token found for favorites filter.");
            }
        }

        console.log("DEBUG: Final Fetch URL:", `/api/jobs?${params.toString()}`);

        const response = await fetch(`/api/jobs?${params.toString()}`);
        jobs = await response.json();

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
    // Backend already does most filtering, but we keep this for local refinements if needed
    resultsCount.textContent = filteredJobs.length;
    renderJobs();
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

function renderCompanies() {
    if (companies.length === 0) {
        companiesGrid.innerHTML = '<div class="no-results">No companies found.</div>';
        return;
    }

    companiesGrid.innerHTML = companies.map(company => {
        const sizeClass = (company.metadata?.size || '').toLowerCase().replace(' ', '-');
        return `
            <div class="company-card glass-card" onclick="showCompanyDetailsByName('${company.name}')">
                <div class="logo-large">${company.name[0]}</div>
                <h3>${company.name}</h3>
                <div class="domain">${company.domain}</div>
                <div class="company-meta">
                    <span class="badge ${sizeClass}">${company.metadata?.size || 'Unknown Size'}</span>
                    <div style="margin-top: 10px; font-size: 0.8rem; color: var(--text-dim);">
                        ${company.metadata?.industry || ''}
                    </div>
                </div>
            </div>
    `;
    }).join('');
}

function showJobDetails(jobId, jobData = null) {
    const job = jobData || jobs.find(j => j._id === jobId);
    if (!job) return;

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

// Utility Functions
function setupEventListeners() {
    // Search with debounce
    let timeout = null;
    jobSearch.addEventListener('input', (e) => {
        clearTimeout(timeout);
        timeout = setTimeout(() => {
            fetchJobs(e.target.value);
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
            fetchJobs(tag);
        });
    });

    // Modal Closers (Universal)
    document.querySelectorAll('.close-modal, .auth-close, .company-close, .modal-close').forEach(btn => {
        btn.onclick = function () {
            const modal = this.closest('.modal');
            if (modal) {
                modal.style.display = "none";
                document.body.style.overflow = "auto";
            }
        };
    });

    window.onclick = (event) => {
        if (event.target.classList.contains('modal')) {
            event.target.style.display = "none";
            document.body.style.overflow = "auto";
        }
    };

    // Navigation Switching
    navJobs.onclick = (e) => {
        e.preventDefault();
        switchToView('jobs');
    };

    navCompanies.onclick = (e) => {
        e.preventDefault();
        switchToView('companies');
    };

    const companyStatCard = document.getElementById('companyStatCard');
    if (companyStatCard) {
        companyStatCard.onclick = () => switchToView('companies');
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

    // Advanced Filters
    const keywordFilter = document.getElementById('keywordFilter');
    const categoryFilter = document.getElementById('categoryFilter');
    const locationFilter = document.getElementById('locationFilter');
    const dateFilter = document.getElementById('dateFilter');
    const clearFiltersBtn = document.getElementById('clearFilters');
    const filterPills = document.querySelectorAll('.filter-pill');

    categoryFilter.onchange = (e) => {
        currentFilters.category = e.target.value;
        fetchJobs();
    };

    // Keyword Filter Sync
    keywordFilter.oninput = (e) => {
        clearTimeout(timeout);
        timeout = setTimeout(() => {
            currentFilters.q = e.target.value;
            // Sync with nav search
            if (jobSearch) jobSearch.value = e.target.value;
            fetchJobs();
        }, 500);
    };

    // Location Filter (Input + Datalist)
    locationFilter.oninput = (e) => {
        clearTimeout(timeout);
        timeout = setTimeout(() => {
            currentFilters.location = e.target.value;
            fetchJobs();
        }, 500);
    };

    /* locationFilter.onchange replaced by oninput above */

    dateFilter.onchange = (e) => {
        currentFilters.days = e.target.value;
        fetchJobs();
    };

    clearFiltersBtn.onclick = () => {
        currentFilters = {
            q: '', job_type: '', remote_only: false, category: '', location: '', days: ''
        };
        categoryFilter.value = '';
        locationFilter.value = '';
        keywordFilter.value = ''; // Clear keyword input
        dateFilter.value = '';
        jobSearch.value = '';
        filterPills.forEach(p => p.classList.remove('active'));
        document.querySelector('.filter-pill[data-filter="all"]').classList.add('active');
        fetchJobs();
    };

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
    } else {
        userProfile.innerHTML = `<button class="btn-signin" id="showLogin">Sign In</button>`;
        // Re-attach listener if switched back
        document.getElementById('showLogin').onclick = () => {
            authModal.style.display = "block";
        };
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
    if (view === 'jobs') {
        navJobs.classList.add('active');
        navCompanies.classList.remove('active');
        jobsDashboardParts.forEach(p => p.style.display = 'block');
        companySection.style.display = 'none';
        applyFilterAndRender();
    } else {
        navJobs.classList.remove('active');
        navCompanies.classList.add('active');
        jobsDashboardParts.forEach(p => p.style.display = 'none');
        companySection.style.display = 'block';
        fetchCompanies();
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
    if (currentFilters.location) params.set('location', currentFilters.location);
    if (currentFilters.days) params.set('days', currentFilters.days);
    if (currentFilters.job_type) params.set('job_type', currentFilters.job_type);
    if (currentFilters.remote_only) params.set('remote_only', 'true');

    const newUrl = `${window.location.pathname}?${params.toString()}`;
    window.history.replaceState({}, '', newUrl);
}

function loadFiltersFromURL() {
    const params = new URLSearchParams(window.location.search);

    currentFilters.q = params.get('q') || '';
    currentFilters.category = params.get('category') || '';
    currentFilters.location = params.get('location') || '';
    currentFilters.days = params.get('days') || '';
    currentFilters.job_type = params.get('job_type') || '';
    currentFilters.remote_only = params.get('remote_only') === 'true';
    currentFilters.company = params.get('company') || '';
    currentFilters.favorites_only = params.get('favorites') === 'true';

    // Populate UI
    const keywordInput = document.getElementById('keywordFilter');
    if (keywordInput) keywordInput.value = currentFilters.q;

    const navSearch = document.getElementById('jobSearch');
    if (navSearch && currentFilters.q) navSearch.value = currentFilters.q;
    // If we have a company filter but no keyword, maybe show it in search bar for context?
    // Or we could have a dedicated pill. For now let's just allow it to work silently or put in search
    if (currentFilters.company && !currentFilters.q && navSearch) {
        navSearch.value = `Company: ${currentFilters.company}`;
        // Note: this is visually indicating but search logic uses 'q' or 'company' param separately
    }

    const catSelect = document.getElementById('categoryFilter');
    if (catSelect) catSelect.value = currentFilters.category;

    const locInput = document.getElementById('locationFilter');
    if (locInput) locInput.value = currentFilters.location;

    const dateSelect = document.getElementById('dateFilter');
    if (dateSelect) dateSelect.value = currentFilters.days;

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
