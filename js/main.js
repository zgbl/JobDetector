// App State
let jobs = [];
let companies = [];
let filteredJobs = [];
let filteredCompanies = [];
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
const closeModal = document.querySelector('.close-modal');
const authClose = document.querySelector('.auth-close');

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
    await checkAuth();
    await fetchStats();
    await fetchJobs();
    setupEventListeners();
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

async function fetchJobs(query = '') {
    showLoading();
    currentSearchQuery = query;
    try {
        const url = query ? `/api/jobs?q=${encodeURIComponent(query)}` : '/api/jobs';
        const response = await fetch(url);
        jobs = await response.json();
        applyFilterAndRender();
    } catch (error) {
        console.error('Error fetching jobs:', error);
        jobsGrid.innerHTML = '<div class="error-msg">Failed to load jobs. Is the server running?</div>';
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
    filteredJobs = jobs;

    if (currentFilter !== 'all') {
        if (currentFilter === 'Remote') {
            filteredJobs = jobs.filter(j => j.remote_type === 'Remote');
        } else {
            filteredJobs = jobs.filter(j => j.job_type === currentFilter);
        }
    }

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

function showJobDetails(jobId) {
    const job = jobs.find(j => j._id === jobId);
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
        const companyJobs = await jobsResp.json();

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

    // Check if we already have this job in our global 'jobs' array
    let job = jobs.find(j => j._id === jobId);

    if (!job) {
        // We need to fetch it or we can pass it, but let's fetch to be safe
        const response = await fetch(`/api/jobs?q=${encodeURIComponent(jobId)}`); // This search might be too broad
        // Better: we know it's in the company jobs we just fetched, but let's just use a simple fetch
        // Or simpler: the 'showCompanyDetailsByName' could store the 'companyJobs' somewhere
        const jobResults = await response.json();
        job = jobResults.find(j => j._id === jobId);
    }

    if (job) {
        showJobDetails(job._id);
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

    // Modal
    closeModal.onclick = () => {
        jobModal.style.display = "none";
        document.body.style.overflow = "auto";
    };

    companyClose.onclick = () => {
        companyModal.style.display = "none";
        document.body.style.overflow = "auto";
    };

    window.onclick = (event) => {
        if (event.target == jobModal) {
            jobModal.style.display = "none";
            document.body.style.overflow = "auto";
        }
        if (event.target == companyModal) {
            companyModal.style.display = "none";
            document.body.style.overflow = "auto";
        }
        if (event.target == authModal) {
            authModal.style.display = "none";
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

    authClose.onclick = () => {
        authModal.style.display = "none";
        document.body.style.overflow = "auto";
    };

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

async function handleLogin() {
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

async function handleRegister() {
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
                <div class="avatar">${(currentUser.full_name || currentUser.email)[0].toUpperCase()}</div>
                <div class="user-info">
                    <div class="user-name">${currentUser.full_name || currentUser.email}</div>
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

// Run
init();
