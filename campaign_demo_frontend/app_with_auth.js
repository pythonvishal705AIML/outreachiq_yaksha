/**
 * FIXES:
 * 1. updateUserUI() — plan_type -> ghl_status (plan_type doesn't exist in accounts table)
 * 2. getAccountId() — added fallback to user.account_id from stored user object
 */

// Configuration
const API_BASE_URL = (window.CONFIG && window.CONFIG.API_BASE_URL) || 'http://localhost:8000/api/agent/v1';
const AUTH_API_BASE = (window.CONFIG && window.CONFIG.AUTH_BASE_URL) || 'http://localhost:8000/api/auth';

// Get authentication token and account info
function getAuthToken() {
    return localStorage.getItem('access_token');
}

function getAccountId() {
    // Try localStorage first, then fall back to user object's account_id
    let id = localStorage.getItem('account_id') || localStorage.getItem('org_id') || localStorage.getItem('tenant_id');
    if (!id) {
        const user = getUser();
        if (user) {
            id = user.account_id || (user.organization && user.organization.id);
        }
    }
    return id;
}

function getUser() {
    const userStr = localStorage.getItem('user');
    return userStr ? JSON.parse(userStr) : null;
}

// Check if user is authenticated
function checkAuthentication() {
    const token = getAuthToken();
    if (!token) {
        window.location.href = 'login.html';
        return false;
    }
    return true;
}

// Logout function
function logout() {
    const refreshToken = localStorage.getItem('refresh_token');
    
    if (refreshToken) {
        fetch(`${AUTH_API_BASE}/logout/`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${getAuthToken()}`
            },
            body: JSON.stringify({ refresh_token: refreshToken })
        }).catch(err => console.error('Logout error:', err));
    }
    
    localStorage.removeItem('access_token');
    localStorage.removeItem('refresh_token');
    localStorage.removeItem('user');
    localStorage.removeItem('account_id');
    localStorage.removeItem('org_id');
    localStorage.removeItem('tenant_id');
    
    window.location.href = 'login.html';
}

// Refresh access token
async function refreshAccessToken() {
    const refreshToken = localStorage.getItem('refresh_token');
    if (!refreshToken) {
        logout();
        return null;
    }
    
    try {
        const response = await fetch(`${AUTH_API_BASE}/refresh/`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ refresh_token: refreshToken })
        });
        
        if (!response.ok) {
            logout();
            return null;
        }
        
        const data = await response.json();
        localStorage.setItem('access_token', data.access_token);
        return data.access_token;
    } catch (error) {
        console.error('Token refresh error:', error);
        logout();
        return null;
    }
}

// Make authenticated API request
async function authenticatedFetch(url, options = {}) {
    let token = getAuthToken();
    
    options.headers = {
        ...options.headers,
        'Authorization': `Bearer ${token}`,
        'Content-Type': 'application/json'
    };
    
    let response = await fetch(url, options);
    
    if (response.status === 401) {
        token = await refreshAccessToken();
        if (token) {
            options.headers['Authorization'] = `Bearer ${token}`;
            response = await fetch(url, options);
        }
    }
    
    return response;
}

// Update user info in UI
function updateUserUI() {
    const user = getUser();
    if (user) {
        const userNameEl = document.querySelector('.user-name');
        const userAvEl = document.querySelector('.user-av');
        const userPlanEl = document.querySelector('.user-plan');
        
        if (userNameEl) {
            userNameEl.textContent = user.full_name || user.email;
        }
        
        if (userAvEl) {
            const initials = user.first_name && user.last_name 
                ? `${user.first_name[0]}${user.last_name[0]}`.toUpperCase()
                : user.email[0].toUpperCase();
            userAvEl.textContent = initials;
        }
        
        // FIX: plan_type doesn't exist in accounts table; use ghl_status
        if (userPlanEl && user.organization) {
            userPlanEl.textContent = user.organization.ghl_status || 'Active';
        }
    }
}

// State management
let sessionId = null;
let isProcessing = false;

// DOM elements
const chatContainer = document.getElementById('chatContainer');
const messageInput = document.getElementById('messageInput');
const sendBtn = document.getElementById('sendBtn');
const startBtn = document.getElementById('startBtn');
const inputArea = document.getElementById('inputArea');
const statusBar = document.getElementById('statusBar');
const statusText = document.getElementById('statusText');

// Check authentication on page load
if (!checkAuthentication()) {
    // Will redirect to login
} else {
    updateUserUI();
    
    const sidebarFooter = document.querySelector('.sidebar-footer');
    if (sidebarFooter) {
        const logoutBtn = document.createElement('button');
        logoutBtn.className = 'logout-btn';
        logoutBtn.innerHTML = `
            <svg width="15" height="15" viewBox="0 0 15 15" fill="none">
                <path d="M5.5 13.5h-3a1 1 0 0 1-1-1v-10a1 1 0 0 1 1-1h3M10.5 10.5l3-3-3-3M13.5 7.5h-8" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"/>
            </svg>
            Logout
        `;
        logoutBtn.onclick = logout;
        sidebarFooter.appendChild(logoutBtn);
    }
}

// Event listeners
if (startBtn) {
    startBtn.addEventListener('click', initializeConversation);
}

if (sendBtn) {
    sendBtn.addEventListener('click', sendMessage);
}

if (messageInput) {
    messageInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter' && !isProcessing) {
            sendMessage();
        }
    });
}

// Initialize conversation
async function initializeConversation() {
    if (isProcessing) return;
    
    const accountId = getAccountId();
    if (!accountId) {
        addSystemMessage('❌ No account ID found. Please log in again.');
        logout();
        return;
    }
    
    isProcessing = true;
    updateStatus('Initializing conversation...', 'active');
    startBtn.disabled = true;

    try {
        const response = await authenticatedFetch(`${API_BASE_URL}/conversation/init/`, {
            method: 'POST',
            body: JSON.stringify({
                tenant_id: accountId,
                org_id: accountId,
                account_id: accountId,
                text: ''
            })
        });

        if (!response.ok) {
            const errorData = await response.json();
            throw new Error(errorData.error || `HTTP error! status: ${response.status}`);
        }

        const data = await response.json();
        sessionId = data.session_id;

        startBtn.style.display = 'none';
        inputArea.style.display = 'flex';

        addBotMessage("Hi! I'm your Campaign Assistant. I can help you create marketing campaigns. What would you like to do today?");

        updateStatus('Connected - Ready to chat', 'active');
        messageInput.focus();

    } catch (error) {
        console.error('Error initializing conversation:', error);
        
        let errorMsg = 'Failed to connect. ';
        if (error.message.includes('Failed to fetch')) {
            errorMsg += 'Django server not running. Run: python manage.py runserver';
        } else if (error.message.includes('401')) {
            errorMsg += 'Authentication failed. Please log in again.';
            setTimeout(logout, 2000);
        } else {
            errorMsg += error.message;
        }
        
        updateStatus(errorMsg, 'error');
        addSystemMessage('❌ ' + errorMsg);
        startBtn.disabled = false;
    } finally {
        isProcessing = false;
    }
}

// Send message
async function sendMessage() {
    const message = messageInput.value.trim();
    
    if (!message || isProcessing || !sessionId) return;

    isProcessing = true;
    updateStatus('Sending...', 'active');
    
    addUserMessage(message);
    messageInput.value = '';
    messageInput.disabled = true;
    sendBtn.disabled = true;

    try {
        const response = await authenticatedFetch(`${API_BASE_URL}/conversation/turn/`, {
            method: 'POST',
            body: JSON.stringify({
                session_id: sessionId,
                text: message
            })
        });

        if (!response.ok) {
            const errorData = await response.json();
            throw new Error(errorData.error || 'Failed to send message');
        }

        const data = await response.json();
        
        if (data.response) {
            addBotMessage(data.response);
        }
        
        updateStatus('Ready', 'active');

    } catch (error) {
        console.error('Error sending message:', error);
        
        if (error.message.includes('401')) {
            addSystemMessage('❌ Session expired. Please log in again.');
            setTimeout(logout, 2000);
        } else {
            addSystemMessage('❌ Failed to send message: ' + error.message);
        }
        
        updateStatus('Error', 'error');
    } finally {
        isProcessing = false;
        messageInput.disabled = false;
        sendBtn.disabled = false;
        messageInput.focus();
    }
}

// UI Helper Functions
function addUserMessage(text) {
    const msgDiv = document.createElement('div');
    msgDiv.className = 'message user-message';
    msgDiv.innerHTML = `
        <div class="msg-content">
            <div class="msg-text">${escapeHtml(text)}</div>
        </div>
        <div class="msg-avatar user-av">You</div>
    `;
    chatContainer.appendChild(msgDiv);
    scrollToBottom();
}

function addBotMessage(text) {
    const msgDiv = document.createElement('div');
    msgDiv.className = 'message bot-message';
    msgDiv.innerHTML = `
        <div class="msg-avatar bot-av">AI</div>
        <div class="msg-content">
            <div class="msg-text">${escapeHtml(text)}</div>
        </div>
    `;
    chatContainer.appendChild(msgDiv);
    scrollToBottom();
}

function addSystemMessage(text) {
    const msgDiv = document.createElement('div');
    msgDiv.className = 'message system-message';
    msgDiv.innerHTML = `<div class="msg-text">${escapeHtml(text)}</div>`;
    chatContainer.appendChild(msgDiv);
    scrollToBottom();
}

function updateStatus(text, state) {
    if (statusText) {
        statusText.textContent = text;
    }
    if (statusBar) {
        statusBar.className = 'status-strip';
        if (state) {
            statusBar.classList.add(`status-${state}`);
        }
    }
}

function scrollToBottom() {
    if (chatContainer) {
        chatContainer.scrollTop = chatContainer.scrollHeight;
    }
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// Add logout button styles
const style = document.createElement('style');
style.textContent = `
    .logout-btn {
        width: 100%;
        margin-top: 12px;
        padding: 12px;
        background: rgba(239, 68, 68, 0.1);
        border: 1px solid rgba(239, 68, 68, 0.2);
        border-radius: 12px;
        color: #fca5a5;
        font-size: 14px;
        font-weight: 500;
        cursor: pointer;
        display: flex;
        align-items: center;
        justify-content: center;
        gap: 8px;
        transition: all 0.2s ease;
        font-family: 'DM Sans', sans-serif;
    }
    
    .logout-btn:hover {
        background: rgba(239, 68, 68, 0.15);
        border-color: rgba(239, 68, 68, 0.3);
    }
`;
document.head.appendChild(style);