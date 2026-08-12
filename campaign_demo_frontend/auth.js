/**
 * FIXES:
 * 1. handleLogin/handleSignup — added fallback to user.account_id when organization is null
 */

const AUTH_API_BASE = (window.CONFIG && window.CONFIG.AUTH_BASE_URL) || 'http://localhost:8000/api/auth';

// Check if user is already logged in
function checkAuth() {
    const token = localStorage.getItem('access_token');
    if (token && window.location.pathname.includes('login.html')) {
        window.location.href = 'index.html';
    }
}

// Login Form Handler
if (document.getElementById('loginForm')) {
    document.getElementById('loginForm').addEventListener('submit', async (e) => {
        e.preventDefault();
        
        const email = document.getElementById('email').value;
        const password = document.getElementById('password').value;
        
        await handleLogin(email, password);
    });
}

// Signup Form Handler
if (document.getElementById('signupForm')) {
    document.getElementById('signupForm').addEventListener('submit', async (e) => {
        e.preventDefault();
        
        const firstName = document.getElementById('firstName').value;
        const lastName = document.getElementById('lastName').value;
        const email = document.getElementById('email').value;
        const companyName = document.getElementById('companyName').value;
        const password = document.getElementById('password').value;
        const passwordConfirm = document.getElementById('passwordConfirm').value;
        
        if (password !== passwordConfirm) {
            showError('Passwords do not match');
            return;
        }
        
        await handleSignup({
            email,
            password,
            password_confirm: passwordConfirm,
            first_name: firstName,
            last_name: lastName,
            organization_name: companyName
        });
    });
}

// FIX: helper to store account IDs with fallback
function storeAccountIds(user) {
    if (user.organization && user.organization.id) {
        localStorage.setItem('account_id', user.organization.id);
        localStorage.setItem('org_id', user.organization.id);
        localStorage.setItem('tenant_id', user.organization.id);
    } else if (user.account_id) {
        localStorage.setItem('account_id', user.account_id);
        localStorage.setItem('org_id', user.account_id);
        localStorage.setItem('tenant_id', user.account_id);
    }
}

// Handle Login
async function handleLogin(email, password) {
    const btn = document.getElementById('loginBtn');
    const btnText = document.getElementById('loginBtnText');
    const btnLoader = document.getElementById('loginBtnLoader');
    
    try {
        btn.disabled = true;
        btnText.style.display = 'none';
        btnLoader.style.display = 'inline-block';
        hideMessages();
        
        const response = await fetch(`${AUTH_API_BASE}/login/`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ email, password })
        });
        
        const data = await response.json();
        
        if (!response.ok) {
            throw new Error(data.message || data.error || 'Login failed');
        }
        
        localStorage.setItem('access_token', data.tokens.access_token);
        localStorage.setItem('refresh_token', data.tokens.refresh_token);
        localStorage.setItem('user', JSON.stringify(data.user));
        
        storeAccountIds(data.user);
        
        showSuccess('Login successful! Redirecting...');
        
        // Set flag to allow access after login
        sessionStorage.setItem('just_logged_in', 'true');
        
        setTimeout(() => {
            window.location.href = 'index.html';
        }, 1000);
        
    } catch (error) {
        console.error('Login error:', error);
        showError(error.message || 'Login failed. Please check your credentials.');
        
        btn.disabled = false;
        btnText.style.display = 'inline';
        btnLoader.style.display = 'none';
    }
}

// Handle Signup
async function handleSignup(userData) {
    const btn = document.getElementById('signupBtn');
    const btnText = document.getElementById('signupBtnText');
    const btnLoader = document.getElementById('signupBtnLoader');
    
    try {
        btn.disabled = true;
        btnText.style.display = 'none';
        btnLoader.style.display = 'inline-block';
        hideMessages();
        
        const response = await fetch(`${AUTH_API_BASE}/signup/`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(userData)
        });
        
        const data = await response.json();
        
        if (!response.ok) {
            if (data.details) {
                const errors = Object.values(data.details).flat().join(', ');
                throw new Error(errors);
            }
            throw new Error(data.message || data.error || 'Signup failed');
        }
        
        localStorage.setItem('access_token', data.tokens.access_token);
        localStorage.setItem('refresh_token', data.tokens.refresh_token);
        localStorage.setItem('user', JSON.stringify(data.user));
        
        storeAccountIds(data.user);
        
        showSuccess('Account created successfully! Redirecting...');
        
        // Set flag to allow access after signup
        sessionStorage.setItem('just_logged_in', 'true');
        
        setTimeout(() => {
            window.location.href = 'index.html';
        }, 1500);
        
    } catch (error) {
        console.error('Signup error:', error);
        showError(error.message || 'Signup failed. Please try again.');
        
        btn.disabled = false;
        btnText.style.display = 'inline';
        btnLoader.style.display = 'none';
    }
}

// Show error message
function showError(message) {
    const errorDiv = document.getElementById('errorMessage');
    if (errorDiv) {
        errorDiv.textContent = message;
        errorDiv.style.display = 'block';
        
        setTimeout(() => {
            errorDiv.style.display = 'none';
        }, 5000);
    }
}

// Show success message
function showSuccess(message) {
    const successDiv = document.getElementById('successMessage');
    if (successDiv) {
        successDiv.textContent = message;
        successDiv.style.display = 'block';
    }
}

// Hide all messages
function hideMessages() {
    const errorDiv = document.getElementById('errorMessage');
    const successDiv = document.getElementById('successMessage');
    if (errorDiv) errorDiv.style.display = 'none';
    if (successDiv) successDiv.style.display = 'none';
}

// Check auth on page load
checkAuth();