// App State
let jobs = [];
let filteredJobs = [];
let currentFilter = 'all';

// DOM Elements
const jobsGrid = document.getElementById('jobsGrid');
const jobSearch = document.getElementById('jobSearch');
const totalJobsCount = document.getElementById('totalJobsCount');
const companyCount = document.getElementById('companyCount');
const remoteCount = document.getElementById('remoteCount');
const resultsCount = document.getElementById('resultsCount');
const filterBtns = document.querySelectorAll('.filter-btn');
const jobModal = document.getElementById('jobModal');
const modalBody = document.getElementById('modalBody');
const closeModal = document.querySelector('.close-modal');

// Init
async function init() {
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
            <h3 class="job-title">${job.title}</h3>
            <div class="job-company">
                <i class="fas fa-building"></i> ${job.company}
            </div>
            <div class="job-location">
                <i class="fas fa-map-marker-alt"></i> ${job.location}
            </div>
            <div class="job-meta">
                <span class="tag blue">${job.job_type}</span>
                <span class="tag purple">${job.remote_type}</span>
                ${job.skills.slice(0, 3).map(skill => `<span class="tag">${skill}</span>`).join('')}
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
                <a href="${job.source_url}" target="_blank" class="tag blue">Apply Directly <i class="fas fa-external-link-alt"></i></a>
            </div>
        </div>
        <div class="jd-content">
            ${job.description || "No description provided."}
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
    };
}

function formatDate(dateStr) {
    if (!dateStr) return 'Just now';
    const date = new Date(dateStr);
    const now = new Date();
    const diffTime = Math.abs(now - date);
    const diffDays = Math.ceil(diffTime / (1000 * 60 * 60 * 24));
    
    if (diffDays <= 1) return 'New';
    if (diffDays > 30) return date.toLocaleDateString();
    return `${diffDays}d ago`;
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
