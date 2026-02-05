// App State
let jobs = [];
let filteredJobs = [];
let currentFilter = 'all';
let currentSearchQuery = '';
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
        <div class="job-card glass-card" onclick="showJobDetails('${job._id}')">
            <div class="job-header">
                <div class="company-logo-type">${job.company[0]}</div>
                <div class="job-posted">${formatDate(job.posted_date)}</div>
            </div>
            <h3 class="job-title">${highlightText(job.title, currentSearchQuery)}</h3>
            <div class="job-company">
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
    `).join('');
}

function showJobDetails(jobId) {
    const job = jobs.find(j => j._id === jobId);
    if (!job) return;

    modalBody.innerHTML = `
        <div class="modal-header">
            <div class="job-company">${job.company}</div>
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

    window.onclick = (event) => {
        if (event.target == jobModal) {
            jobModal.style.display = "none";
            document.body.style.overflow = "auto";
        }
        if (event.target == authModal) {
            authModal.style.display = "none";
            document.body.style.overflow = "auto";
        }
    };

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
