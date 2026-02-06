// Authentication Utilities

const API_AUTH_BASE = '/api/auth';
let currentUser = null;

async function checkAuth() {
    const token = localStorage.getItem('token');
    if (!token) return null;

    try {
        const response = await fetch(`${API_AUTH_BASE}/me`, {
            headers: { 'Authorization': `Bearer ${token}` }
        });
        if (response.ok) {
            currentUser = await response.json();
            updateAuthUI();
            return currentUser;
        } else {
            localStorage.removeItem('token');
            return null;
        }
    } catch (error) {
        console.error('Auth check failed:', error);
        return null;
    }
}

function updateAuthUI() {
    const authSection = document.getElementById('auth-section');
    if (!authSection) return;

    if (currentUser) {
        authSection.innerHTML = `
            <div class="user-display">
                <div class="avatar">${(currentUser.full_name || currentUser.email || '?')[0].toUpperCase()}</div>
                <div class="user-info">
                    <div class="user-name">${currentUser.full_name || currentUser.email || 'User'}</div>
                    <div class="logout-link" onclick="logout()">Logout</div>
                </div>
            </div>
        `;
    } else {
        authSection.innerHTML = `<button class="btn-signin" onclick="window.location.href='/?login=true'">Sign In</button>`;
    }
}

function logout() {
    localStorage.removeItem('token');
    currentUser = null;
    window.location.href = '/';
}

// Make globally available
window.checkAuth = checkAuth;
window.updateAuthUI = updateAuthUI;
window.logout = logout;
window.getCurrentUser = () => currentUser;
