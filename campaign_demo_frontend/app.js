// Configuration
// Version: 2.0 - Added user authentication and display
const API_BASE_URL = (window.CONFIG && window.CONFIG.API_BASE_URL) || 'http://localhost:8000/api/agent/v1';
const AUTH_BASE_URL = (window.CONFIG && window.CONFIG.AUTH_BASE_URL) || 'http://localhost:8000/api/auth';
const SERVER_BASE_URL = (window.CONFIG && window.CONFIG.SERVER_URL) || 'http://localhost:8000';

// Get the logged-in user's display name for email previews
function getCurrentUserName() {
    try {
        const user = JSON.parse(localStorage.getItem('user') || '{}');
        if (user.first_name || user.last_name) {
            return `${user.first_name || ''} ${user.last_name || ''}`.trim();
        }
        if (user.email) return user.email.split('@')[0];
    } catch (e) { }
    return 'Sender';
}

function getUserInitials() {
    try {
        const user = JSON.parse(localStorage.getItem('user') || '{}');
        const fullName = `${user.first_name || ''} ${user.last_name || ''}`.trim() || user.email || '';
        return fullName.split(' ').map(w => w[0]).join('').toUpperCase().slice(0, 2) || 'ME';
    } catch (e) { }
    return 'ME';
}
const DEFAULT_TENANT_ID = '12b2abd641734cce805b1544105042a7';  // Lopes account from database

// Authentication helpers
function getUser() {
    const userStr = localStorage.getItem('user');
    return userStr ? JSON.parse(userStr) : null;
}

function getAccountId() {
    const accountId = localStorage.getItem('account_id');
    if (accountId) return accountId;

    const user = getUser();
    if (user && user.organization && user.organization.id) {
        return user.organization.id;
    }
    if (user && user.account_id) {
        return user.account_id;
    }
    return DEFAULT_TENANT_ID;
}

// Headers helper — kept for call-site compatibility; the app has no login,
// so every request is just attributed to the single default account server-side.
function getAuthHeaders() {
    return { 'Content-Type': 'application/json' };
}

async function apiFetch(url, options = {}) {
    options.headers = { ...getAuthHeaders(), ...(options.headers || {}) };
    return fetch(url, options);
}

// Update user info in UI
function updateUserUI() {
    const user = getUser();
    console.log('Updating user UI with:', user);

    if (user) {
        const userNameEl = document.querySelector('.user-name');
        const userAvEl = document.querySelector('.user-av');
        const userPlanEl = document.querySelector('.user-plan');

        console.log('Found elements:', { userNameEl, userAvEl, userPlanEl });

        if (userNameEl) {
            userNameEl.textContent = user.full_name || user.email;
            console.log('Set user name to:', user.full_name || user.email);
        }

        if (userAvEl) {
            const initials = user.first_name && user.last_name
                ? `${user.first_name[0]}${user.last_name[0]}`.toUpperCase()
                : user.email[0].toUpperCase();
            userAvEl.textContent = initials;
            console.log('Set initials to:', initials);
        }

        if (userPlanEl && user.organization) {
            userPlanEl.textContent = user.organization.ghl_status || 'Active';
        } else if (userPlanEl) {
            userPlanEl.textContent = 'Active';
        }
    } else {
        console.log('No user found in localStorage');
    }
}

// ─── Gmail Sender Status (App Password) ─────────────────────────────────────

async function checkGmailStatus() {
    const pill = document.getElementById('gmailStatusPill');
    const label = document.getElementById('gmailStatusLabel');
    if (!pill || !label) return;

    try {
        const res = await apiFetch(`${AUTH_BASE_URL}/email-config/`, { headers: getAuthHeaders() });
        const data = await res.json();

        if (data.configured) {
            pill.className = 'gmail-pill gmail-connected';
            label.textContent = data.from_email;
            pill.title = `Sending from ${data.from_email}. Click Settings to change.`;
        } else {
            pill.className = 'gmail-pill gmail-disconnected';
            label.textContent = 'Set Sender Email';
            pill.title = 'Click Settings to configure your Gmail sender';
        }
        pill.onclick = openEmailSettings;
    } catch (e) {
        console.log('Gmail status check failed:', e);
    }
}

// ─── Email Settings (Gmail App Password: name, gmail, key) ─────────────────

async function openEmailSettings() {
    document.getElementById('emailSettingsModal').style.display = 'flex';

    try {
        const res = await apiFetch(`${AUTH_BASE_URL}/email-config/`, { headers: getAuthHeaders() });
        const data = await res.json();
        if (data.configured) {
            document.getElementById('cfgFromEmail').value = data.from_email || '';
            document.getElementById('cfgFromName').value  = data.from_name  || '';
            document.getElementById('cfgRemoveBtn').style.display = 'inline-flex';
        } else {
            document.getElementById('cfgRemoveBtn').style.display = 'none';
        }
    } catch (e) {
        console.log('Could not load email config', e);
    }
}

function closeEmailSettings() {
    document.getElementById('emailSettingsModal').style.display = 'none';
}

function showConfigStatus(msg, type) {
    const el = document.getElementById('smtpConfigStatus');
    if (!el) return;
    el.style.display = 'block';
    el.style.color = type === 'success' ? '#10b981' : '#ef4444';
    el.innerHTML = msg;
}

async function saveEmailConfig() {
    const fromEmail = document.getElementById('cfgFromEmail').value.trim();
    const appPassword = document.getElementById('cfgAppPassword').value.trim();
    const fromName = document.getElementById('cfgFromName').value.trim();

    if (!fromEmail || !appPassword) {
        showConfigStatus('Gmail address and App Password (key) are required.', 'error');
        return;
    }

    showConfigStatus('Verifying credentials…', 'success');
    try {
        const res = await apiFetch(`${AUTH_BASE_URL}/email-config/`, {
            method: 'POST',
            headers: getAuthHeaders(),
            body: JSON.stringify({ from_email: fromEmail, app_password: appPassword, from_name: fromName })
        });
        const data = await res.json();
        if (res.ok && data.success) {
            showConfigStatus(`Saved! Campaigns will now send from ${data.from_email}`, 'success');
            document.getElementById('cfgRemoveBtn').style.display = 'inline-flex';
            checkGmailStatus();
        } else {
            showConfigStatus(data.error || 'Failed to save.', 'error');
        }
    } catch (e) {
        showConfigStatus('Request failed. Is the server running?', 'error');
    }
}

async function removeEmailConfig() {
    if (!confirm('Remove your Gmail sender config?')) return;
    await apiFetch(`${AUTH_BASE_URL}/email-config/`, { method: 'DELETE', headers: getAuthHeaders() });
    document.getElementById('cfgRemoveBtn').style.display = 'none';
    document.getElementById('cfgFromEmail').value = '';
    document.getElementById('cfgAppPassword').value = '';
    document.getElementById('cfgFromName').value = '';
    showConfigStatus('Removed.', 'success');
    checkGmailStatus();
}

// Initialize the single-account UI state (no login required)
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
        updateUserUI();
        checkGmailStatus();
        handleGmailOAuthRedirect();
    });
} else {
    updateUserUI();
    checkGmailStatus();
    handleGmailOAuthRedirect();
}

// After Google redirects back through the backend callback, it lands here
// with ?gmail_connected=1&gmail_address=... or ?gmail_error=... in the URL.
function handleGmailOAuthRedirect() {
    const params = new URLSearchParams(window.location.search);
    const connected = params.get('gmail_connected');
    const address = params.get('gmail_address');
    const error = params.get('gmail_error');

    if (connected) {
        alert(`Gmail connected: ${address}`);
        checkGmailStatus();
    } else if (error) {
        alert('Failed to connect Gmail: ' + error);
    } else {
        return;
    }

    params.delete('gmail_connected');
    params.delete('gmail_address');
    params.delete('gmail_error');
    const newSearch = params.toString();
    const newUrl = window.location.pathname + (newSearch ? `?${newSearch}` : '') + window.location.hash;
    window.history.replaceState({}, document.title, newUrl);
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

// Event listeners
startBtn.addEventListener('click', initializeConversation);
sendBtn.addEventListener('click', sendMessage);
messageInput.addEventListener('keypress', (e) => {
    if (e.key === 'Enter' && !isProcessing) {
        sendMessage();
    }
});

// Initialize conversation
async function initializeConversation() {
    if (isProcessing) return;

    isProcessing = true;
    updateStatus('Initializing conversation...', 'active');
    startBtn.disabled = true;

    try {
        // Create session
        const response = await apiFetch(`${API_BASE_URL}/conversation/init/`, {
            method: 'POST',
            headers: getAuthHeaders(),
            body: JSON.stringify({
                tenant_id: getAccountId(),
                text: ''
            })
        });

        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }

        const data = await response.json();
        sessionId = data.session_id;
        sessionStorage.setItem('currentSessionId', sessionId);

        // Hide start button, show input area
        startBtn.style.display = 'none';
        inputArea.style.display = 'flex';

        // Show welcome message
        addBotMessage("Hi! I'm your Campaign Assistant. I can help you create marketing campaigns. What would you like to do today?");

        updateStatus('Connected - Ready to chat', 'active');
        messageInput.focus();

    } catch (error) {
        console.error('Error initializing conversation:', error);

        // Show detailed error
        let errorMsg = 'Failed to connect. ';
        if (error.message.includes('Failed to fetch')) {
            errorMsg += 'Django server not running. Run: python manage.py runserver';
        } else if (error.message.includes('400')) {
            errorMsg += 'Missing tenant_id or invalid request.';
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

// New Campaign — reset state and start a fresh session
async function startNewCampaign() {
    if (isProcessing) return;

    // Reset all state variables
    sessionId = null;
    sessionStorage.removeItem('currentSessionId');
    isProcessing = false;

    // Clear chat and restore welcome block
    chatContainer.innerHTML = `
        <div class="welcome-block">
          <div class="welcome-hex">
            <svg width="40" height="40" viewBox="0 0 40 40" fill="none"><path d="M20 4L36 13V27L20 36L4 27V13L20 4Z" stroke="currentColor" stroke-width="1.5" opacity="0.3"/><path d="M20 8L33 15.5V25L20 32L7 25V15.5L20 8Z" stroke="currentColor" stroke-width="1.5" opacity="0.6"/><circle cx="20" cy="20" r="5" fill="currentColor" opacity="0.2"/><circle cx="20" cy="20" r="2.5" fill="currentColor"/></svg>
          </div>
          <div class="welcome-title">AI Campaign Builder</div>
          <div class="welcome-body">Generate fully-personalized outreach sequences for any audience. Powered by real-time lead intelligence and behavioral AI.</div>
          <div class="audience-chips">
            <span class="chip">Fintech CEOs</span>
            <span class="chip">SaaS Founders</span>
            <span class="chip">Healthcare VPs</span>
            <span class="chip">US Enterprise</span>
          </div>
        </div>
    `;

    // Reset input UI
    startBtn.style.display = 'block';
    inputArea.style.display = 'none';
    messageInput.value = '';
    messageInput.disabled = false;
    sendBtn.disabled = false;
    updateStatus('Ready to start', '');

    // Immediately start a new session
    await initializeConversation();
}

// Send message
async function sendMessage() {
    const message = messageInput.value.trim();

    if (!message || isProcessing || !sessionId) return;

    isProcessing = true;
    updateStatus('Sending...', 'active');

    // Add user message to chat
    addUserMessage(message);
    messageInput.value = '';
    messageInput.disabled = true;
    sendBtn.disabled = true;

    // Show typing indicator
    const typingId = showTypingIndicator();

    try {
        const response = await apiFetch(`${API_BASE_URL}/conversation/message/`, {
            method: 'POST',
            headers: getAuthHeaders(),
            body: JSON.stringify({
                session_id: sessionId,
                text: message
            })
        });

        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }

        const data = await response.json();

        // Remove typing indicator
        removeTypingIndicator(typingId);

        // Add bot response
        if (data.text) {
            addBotMessage(data.text);
        } else if (data.reply) {
            addBotMessage(data.reply);
        } else if (data.message) {
            addBotMessage(data.message);
        }

        // Check if campaign is complete and show details
        if (data.campaign_id && (data.sequence_list || data.campaign_created)) {
            addSystemMessage('✅ Campaign created successfully!');

            // If sequence_list is already in response, display it directly
            if (data.sequence_list) {
                displayCampaignSummary(data);
            } else if (data.campaign_id) {
                // Otherwise fetch campaign details
                await displayCampaignDetails(data.campaign_id);
            }

            updateStatus('Campaign completed!', 'active');
        } else {
            updateStatus('Ready to chat', 'active');
        }

    } catch (error) {
        console.error('Error sending message:', error);
        removeTypingIndicator(typingId);

        // Show detailed error message
        let errorMsg = '❌ Failed to send message. ';
        if (error.message.includes('Failed to fetch')) {
            errorMsg += 'Cannot connect to backend. Make sure Django is running on port 8000.';
        } else if (error.message.includes('403')) {
            errorMsg += 'Access forbidden. Check AGENT_RUNTIME_ENABLED setting.';
        } else if (error.message.includes('400')) {
            errorMsg += 'Bad request. Check API parameters.';
        } else {
            errorMsg += error.message;
        }

        addSystemMessage(errorMsg);
        updateStatus('Error occurred', 'error');
    } finally {
        isProcessing = false;
        messageInput.disabled = false;
        sendBtn.disabled = false;
        messageInput.focus();
    }
}

// Display campaign details with email sequences
async function displayCampaignDetails(campaignId) {
    updateStatus('Loading campaign details...', 'active');

    try {
        const response = await apiFetch(`${API_BASE_URL}/campaigns/sequences/`, {
            method: 'POST',
            headers: getAuthHeaders(),
            body: JSON.stringify({
                session_id: sessionId,
                campaign_id: campaignId
            })
        });

        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }

        const data = await response.json();

        // Display campaign summary and email sequences
        displayCampaignSummary(data);

        updateStatus('Campaign ready!', 'active');

    } catch (error) {
        console.error('Error fetching campaign details:', error);
        addSystemMessage('Campaign created but could not load details. Check Django admin to view.');
    }
}

// Display campaign summary with email sequences
function displayCampaignSummary(responseData) {
    // Handle both direct API response and nested sequence_list format
    let data = responseData;

    // If response has sequence_list.data, use that
    if (responseData.sequence_list && responseData.sequence_list.data) {
        data = responseData.sequence_list.data;
    } else if (responseData.data) {
        data = responseData.data;
    }

    const campaignId = data.campaign_id || responseData.campaign_id;
    const campaignStatus = data.campaign_status || responseData.campaign_status || 'draft';
    const steps = data.steps || [];

    let campaignName = 'Campaign';
    if (responseData.reply) {
        const nameMatch = responseData.reply.match(/Campaign '([^']+)'/);
        if (nameMatch) campaignName = nameMatch[1];
    }

    let html = `<div class="campaign-summary">
        <div class="campaign-hero">
          <div class="campaign-hero-left">
            <div class="campaign-hero-eyebrow">Campaign Ready</div>
            <div class="campaign-hero-name">${escapeHtml(campaignName)}</div>
            <div class="campaign-hero-meta">
              <span class="hero-badge status">${campaignStatus}</span>
              <span class="hero-badge">${steps.length} email step${steps.length !== 1 ? 's' : ''}</span>
              ${campaignId ? `<span class="hero-badge">ID: ${String(campaignId).slice(0, 8)}…</span>` : ''}
            </div>
          </div>
        </div>`;

    if (steps.length > 0) {
        html += '<div class="email-sequence-list">';
        steps.forEach((step, index) => {
            const email = step.email;
            if (!email) return;

            const delayDays = step.delay_days || 0;
            const delayTag = delayDays > 0
                ? `<span class="step-tag tag-delay">⏱ ${delayDays}d delay</span>`
                : `<span class="step-tag tag-immediate">⚡ Immediate</span>`;
            const condTag = `<span class="step-tag tag-condition">${formatCondition(step.step_condition)}</span>`;

            html += `
            <div class="email-step">
              <div class="step-head">
                <span class="step-label">STEP ${step.step_order || index + 1}</span>
                <div class="step-tags">${delayTag}${condTag}</div>
              </div>
              <div class="email-preview">
                <div class="email-field">
                  <span class="email-field-label">From</span>
                  <span class="email-field-val">${getCurrentUserName()}</span>
                </div>
                <div class="email-field">
                  <span class="email-field-label">To</span>
                  <span class="email-field-val">{{first_name}}</span>
                </div>
                <div class="email-field subject">
                  <span class="email-field-label">Subject</span>
                  <span class="email-subject-val">${escapeHtml(email.subject || 'No subject')}</span>
                </div>
                <div class="email-body-wrap">
                  ${formatEmailBody(email.body || 'No content')}
                </div>
                ${email.spam_status ? `
                <div class="email-footer">
                  <span class="spam-badge spam-${email.spam_status}">Spam check: ${email.spam_status}</span>
                </div>` : ''}
                <div class="email-actions">
                  <button class="email-action-btn edit-btn" onclick="openEditEmailModal('${email.id}', this)">
                    ✏️ Edit
                  </button>
                  <button class="email-action-btn test-btn" onclick="showSendEmailModal('${email.id}', ${step.step_order}, '${campaignId}', true)">
                    📧 Send Test
                  </button>
                </div>
              </div>
            </div>`;
        });
        html += '</div>';
    } else {
        html += `<div class="no-sequences"><p>Campaign created — email sequences pending.</p><p class="hint">The agent will ask for your campaign details to generate emails.</p></div>`;
    }

    // Campaign-level action buttons (only if steps exist)
    if (steps.length > 0) {
        html += `
        <div class="campaign-actions" style="display:flex; gap:12px; padding:16px 20px; border-top:1px solid rgba(255,255,255,0.08);">
          <button class="email-action-btn test-btn" style="flex:1; padding:12px; font-size:14px; border-radius:8px; cursor:pointer; border:1px solid #f59e0b; background:transparent; color:#f59e0b;"
                  onclick="showTestCampaignModal('${campaignId}', ${steps.length})">
            🧪 Test Run (Single Email)
          </button>
          <button class="email-action-btn send-btn" style="flex:1; padding:12px; font-size:14px; border-radius:8px; cursor:pointer; border:none; background:linear-gradient(135deg,#22c55e,#16a34a); color:#fff; font-weight:600;"
                  onclick="showRunCampaignModal('${campaignId}', ${steps.length})">
            🚀 Run Campaign (All Leads)
          </button>
        </div>`;
    }

    html += '</div>';

    const messageDiv = document.createElement('div');
    messageDiv.className = 'message bot';
    messageDiv.innerHTML = `
        <div class="msg-avatar bot-av">
            <svg width="14" height="14" viewBox="0 0 14 14" fill="none"><path d="M7 1L13 4.5V9.5L7 13L1 9.5V4.5L7 1Z" stroke="currentColor" stroke-width="1.3"/><circle cx="7" cy="7" r="2" fill="currentColor" opacity="0.5"/></svg>
        </div>
        <div class="msg-bubble" style="max-width:100%;padding:0;background:transparent;border:none;">${html}</div>
    `;
    chatContainer.appendChild(messageDiv);
    scrollToBottom();
}

// Format step condition to human-readable label
function formatCondition(condition) {
    const map = {
        'always': '📬 Always send',
        'not_replied': '🔁 If not replied',
        'not_opened': '👁 If not opened',
        'replied': '✅ If replied'
    };
    return map[condition] || condition || 'Always send';
}

// Format email body - render HTML tags directly (API returns HTML content)
function formatEmailBody(body) {
    if (!body) return '<p><em>No content</em></p>';

    // If body already contains HTML tags, render it directly
    if (/<[a-z][\s\S]*>/i.test(body)) {
        // Sanitize: only allow safe tags
        const allowed = body
            .replace(/<script[\s\S]*?<\/script>/gi, '')
            .replace(/<style[\s\S]*?<\/style>/gi, '')
            .replace(/on\w+="[^"]*"/gi, '')
            .replace(/on\w+='[^']*'/gi, '');
        return `<div class="email-body-html">${allowed}</div>`;
    }

    // Plain text fallback: convert newlines to <br>
    let formatted = escapeHtml(body);
    formatted = formatted.replace(/\n\n/g, '</p><p>');
    formatted = formatted.replace(/\n/g, '<br>');
    return '<p>' + formatted + '</p>';
}

// Strip quoted/forwarded content from a reply body — keeps only the actual reply text.
function stripQuotedReply(body) {
    if (!body) return '';
    const lines = body.split('\n');
    const cutPatterns = [
        /^on .+wrote:\s*$/i,               // "On Mon, Apr 27... wrote:"
        /^-{3,}\s*(original message|forwarded message)/i,
        /^from:\s+\S/i,                    // Outlook-style "From: ..."
        /^_{5,}/,                          // long underline separators
    ];
    let cutAt = lines.length;
    for (let i = 0; i < lines.length; i++) {
        const line = lines[i].trim();
        // Stop at a quoted line block (3+ consecutive ">" lines counts as quoted)
        if (line.startsWith('>')) { cutAt = i; break; }
        if (cutPatterns.some(p => p.test(line))) { cutAt = i; break; }
    }
    return lines.slice(0, cutAt).join('\n').trim();
}

// UI Helper functions
function addUserMessage(text) {
    const messageDiv = document.createElement('div');
    messageDiv.className = 'message user';
    messageDiv.innerHTML = `
        <div class="msg-avatar user-av">${getUserInitials()}</div>
        <div class="msg-bubble">${escapeHtml(text)}</div>
    `;
    chatContainer.appendChild(messageDiv);
    scrollToBottom();
}

function addBotMessage(text) {
    const messageDiv = document.createElement('div');
    messageDiv.className = 'message bot';
    messageDiv.innerHTML = `
        <div class="msg-avatar bot-av">
            <svg width="14" height="14" viewBox="0 0 14 14" fill="none"><path d="M7 1L13 4.5V9.5L7 13L1 9.5V4.5L7 1Z" stroke="currentColor" stroke-width="1.3"/><circle cx="7" cy="7" r="2" fill="currentColor" opacity="0.5"/></svg>
        </div>
        <div class="msg-bubble">${formatBotMessage(text)}</div>
    `;
    chatContainer.appendChild(messageDiv);
    scrollToBottom();
}

function addSystemMessage(text) {
    const messageDiv = document.createElement('div');
    messageDiv.className = 'message system';
    messageDiv.innerHTML = `
        <div class="msg-bubble">${escapeHtml(text)}</div>
    `;
    chatContainer.appendChild(messageDiv);
    scrollToBottom();
}

function showTypingIndicator() {
    const typingId = 'typing-' + Date.now();
    const typingDiv = document.createElement('div');
    typingDiv.id = typingId;
    typingDiv.className = 'typing-indicator';
    typingDiv.innerHTML = `
        <div class="msg-avatar bot-av">
            <svg width="14" height="14" viewBox="0 0 14 14" fill="none"><path d="M7 1L13 4.5V9.5L7 13L1 9.5V4.5L7 1Z" stroke="currentColor" stroke-width="1.3"/><circle cx="7" cy="7" r="2" fill="currentColor" opacity="0.5"/></svg>
        </div>
        <div class="msg-bubble">
            <div class="typing-dots"><span></span><span></span><span></span></div>
        </div>
    `;
    chatContainer.appendChild(typingDiv);
    scrollToBottom();
    return typingId;
}

function removeTypingIndicator(typingId) {
    const typingDiv = document.getElementById(typingId);
    if (typingDiv) {
        typingDiv.remove();
    }
}

function updateStatus(text, type = '') {
    const statusText = document.getElementById('statusText');
    const statusBar = document.getElementById('statusBar');
    const agentLabel = document.getElementById('agentStatusLabel');
    if (statusText) statusText.textContent = text;
    if (statusBar) {
        statusBar.className = 'status-strip';
        if (type) statusBar.classList.add(type);
    }
    if (agentLabel) {
        agentLabel.innerHTML = `<span class="pulse-dot"></span> ${text}`;
    }
}

function scrollToBottom() {
    const container = document.getElementById('chatContainer');
    if (container) container.scrollTop = container.scrollHeight;
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function formatBotMessage(text) {
    // Convert newlines to <br>
    let formatted = escapeHtml(text).replace(/\n/g, '<br>');

    // Make numbered lists more readable
    formatted = formatted.replace(/(\d+\.\s)/g, '<br>$1');

    // Make bullet points more readable
    formatted = formatted.replace(/([•\-]\s)/g, '<br>$1');

    return formatted;
}

// Initialize on load
document.addEventListener('DOMContentLoaded', () => {
    console.log('Campaign Demo Frontend loaded');
    updateStatus('Ready to start');
    checkBackendConnection();
    loadMyCampaigns();
});

// Check backend connection
async function checkBackendConnection() {
    const connectionStatus = document.getElementById('connectionStatus');
    const connLabel = document.getElementById('connLabel');

    try {
        const response = await apiFetch(`${API_BASE_URL}/conversation/init/`, {
            method: 'POST',
            headers: getAuthHeaders(),
            body: JSON.stringify({ tenant_id: 'connection-test', text: '' })
        });

        if (response.ok) {
            connectionStatus.className = 'conn-pill connected';
            if (connLabel) connLabel.textContent = 'Connected';
        } else {
            connectionStatus.className = 'conn-pill disconnected';
            if (connLabel) connLabel.textContent = 'Backend error';
        }
    } catch (error) {
        connectionStatus.className = 'conn-pill disconnected';
        if (connLabel) connLabel.textContent = 'Offline';
        console.error('Backend connection check failed:', error);
        setTimeout(() => {
            if (confirm('Backend server is not responding. Would you like to see troubleshooting steps?')) {
                window.open('TROUBLESHOOTING.md', '_blank');
            }
        }, 1000);
    }
}

// ─── Email Sending Functions ────────────────────────────────────────────────

// Check Gmail OAuth connection status
async function getGmailStatus() {
    try {
        const response = await fetch(AUTH_BASE_URL + '/gmail/status/', {
            headers: getAuthHeaders()
        });
        if (response.ok) {
            return await response.json();
        }
    } catch (e) { }
    return { connected: false };
}

// Show modal for email sending
async function showSendEmailModal(emailId, stepOrder, campaignId, isTestMode) {
    const existing = document.getElementById('emailSendModal');
    if (existing) existing.remove();

    const gmailStatus = await getGmailStatus();

    let bodyHtml;
    if (gmailStatus.connected) {
        bodyHtml = `
            <div class="gmail-connected-banner">
                <svg width="16" height="16" viewBox="0 0 16 16" fill="none"><circle cx="8" cy="8" r="7" stroke="#22c55e" stroke-width="1.5"/><path d="M5 8l2 2 4-4" stroke="#22c55e" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>
                Sending from <strong>${gmailStatus.gmail_address}</strong> (OAuth)
            </div>
            <div class="form-group test-email-field" style="display:${isTestMode ? 'block' : 'none'};">
                <label for="testEmail">Test Email Address</label>
                <input type="email" id="testEmail" placeholder="test@example.com" class="form-input" />
            </div>`;
    } else {
        // Show option to connect Gmail OR send via SMTP fallback
        bodyHtml = `
            <div class="gmail-not-connected">
                <p>Gmail OAuth not connected. Emails will be sent via SMTP fallback.</p>
                <button class="modal-btn" onclick="connectGmail()" style="margin-bottom: 10px;">Connect Gmail Account (Optional)</button>
            </div>
            <div class="form-group test-email-field" style="display:${isTestMode ? 'block' : 'none'};">
                <label for="testEmail">Test Email Address</label>
                <input type="email" id="testEmail" placeholder="test@example.com" class="form-input" />
            </div>`;
    }

    const modalHtml = `
    <div id="emailSendModal" class="email-modal" style="display:flex;">
        <div class="modal-content">
            <div class="modal-header">
                <h3 class="modal-title">${isTestMode ? '📧 Send Test Email' : '🚀 Send Campaign to All Leads'}</h3>
                <button class="modal-close" onclick="closeEmailSendModal()">&times;</button>
            </div>
            <div class="modal-body">${bodyHtml}</div>
            <div class="modal-footer">
                <button class="modal-btn cancel-btn" onclick="closeEmailSendModal()">Cancel</button>
                <button class="modal-btn send-btn" id="doSendBtn" onclick="doSendEmail()">Send</button>
            </div>
        </div>
    </div>`;

    document.body.insertAdjacentHTML('beforeend', modalHtml);

    // Store context on the modal element
    const modal = document.getElementById('emailSendModal');
    modal.dataset.emailId = emailId;
    modal.dataset.stepOrder = stepOrder;
    modal.dataset.campaignId = campaignId;
    modal.dataset.isTestMode = isTestMode;
}

function connectGmail() {
    fetch(AUTH_BASE_URL + '/gmail/connect/', { headers: getAuthHeaders() })
        .then(r => r.json())
        .then(data => {
            if (data && data.auth_url) {
                window.location.href = data.auth_url;
            } else if (data && data.error) {
                alert('Failed to connect Gmail: ' + data.error);
            }
        })
        .catch((err) => {
            console.error('Gmail connection error:', err);
            alert('Failed to start Gmail connection. Please try again.');
        });
}

function closeEmailSendModal() {
    const modal = document.getElementById('emailSendModal');
    if (modal) modal.remove();
}

async function doSendEmail() {
    const modal = document.getElementById('emailSendModal');
    const emailId = modal.dataset.emailId;
    const stepOrder = modal.dataset.stepOrder;
    const campaignId = modal.dataset.campaignId;
    const isTestMode = modal.dataset.isTestMode === 'true';

    const btn = document.getElementById('doSendBtn');
    btn.disabled = true;
    btn.textContent = 'Sending...';

    try {
        if (isTestMode) {
            const testEmail = document.getElementById('testEmail')?.value.trim();
            if (!testEmail) { alert('Please enter a test email address'); btn.disabled = false; btn.textContent = 'Send'; return; }
            await sendTestEmail(emailId, testEmail);
        } else {
            await sendToAllLeads(campaignId, stepOrder);
        }
        closeEmailSendModal();
    } catch (error) {
        alert('Failed to send: ' + error.message);
        btn.disabled = false;
        btn.textContent = 'Send';
    }
}

// Send test email via OAuth
async function sendTestEmail(emailId, recipientEmail) {
    updateStatus('Sending test email...', 'active');

    const response = await apiFetch(`${API_BASE_URL}/campaigns/send-email/`, {
        method: 'POST',
        headers: getAuthHeaders(),
        body: JSON.stringify({ email_id: emailId, recipient_email: recipientEmail })
    });

    const data = await response.json();
    if (response.ok && data.success) {
        addSystemMessage(`✅ Test email sent to ${recipientEmail} from ${data.sent_from || 'your Gmail'}`);
        updateStatus('Test email sent', 'active');
    } else {
        addSystemMessage(`❌ Failed to send test email: ${data.error}`);
        updateStatus('Send failed', 'error');
        throw new Error(data.error || 'Failed to send test email');
    }
}

// Send to all leads via OAuth (or SMTP fallback)
async function sendToAllLeads(campaignId, stepOrder) {
    // Show which sender will be used
    const gmailLabel = document.getElementById('gmailStatusLabel');
    const senderHint = gmailLabel && !gmailLabel.textContent.includes('Connect')
        ? `Sending from: ${gmailLabel.textContent}`
        : 'Sending from shared account (connect your Gmail to use your own address)';
    addSystemMessage(`ℹ️ ${senderHint}`);
    updateStatus('Sending campaign emails...', 'active');

    const response = await apiFetch(`${API_BASE_URL}/campaigns/send-to-leads/`, {
        method: 'POST',
        headers: getAuthHeaders(),
        body: JSON.stringify({ campaign_id: campaignId, step_order: stepOrder, test_mode: false, session_id: sessionId })
    });

    const data = await response.json();
    if (response.ok && data.success) {
        const sender = data.sent_from ? ` from ${data.sent_from}` : '';
        const message = `✅ Campaign emails sent${sender}!\nSent: ${data.sent_count} / ${data.total_leads} leads` +
            (data.failed_count > 0 ? `\nFailed: ${data.failed_count}` : '');
        addSystemMessage(message);
        updateStatus('Campaign sent', 'active');
    } else {
        addSystemMessage(`❌ Failed to send campaign: ${data.error}`);
        updateStatus('Send failed', 'error');
        throw new Error(data.error || 'Failed to send campaign');
    }
}


// ─── Run Campaign Modal (sends Step 1 to ALL leads, activates auto follow-ups) ───

async function showRunCampaignModal(campaignId, totalSteps) {
    const existing = document.getElementById('runCampaignModal');
    if (existing) existing.remove();

    const gmailStatus = await getGmailStatus();

    let senderInfo;
    if (gmailStatus.connected) {
        senderInfo = `<div class="gmail-connected-banner">
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none"><circle cx="8" cy="8" r="7" stroke="#22c55e" stroke-width="1.5"/><path d="M5 8l2 2 4-4" stroke="#22c55e" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>
            Sending from <strong>${gmailStatus.gmail_address}</strong> (OAuth)
        </div>`;
    } else {
        senderInfo = `<div class="gmail-not-connected">
            <p>Gmail OAuth not connected. Emails will be sent via SMTP fallback.</p>
            <button class="modal-btn" onclick="connectGmail()" style="margin-bottom: 10px;">Connect Gmail (Optional)</button>
        </div>`;
    }

    const modalHtml = `
    <div id="runCampaignModal" class="email-modal" style="display:flex;">
        <div class="modal-content">
            <div class="modal-header">
                <h3 class="modal-title">🚀 Run Campaign</h3>
                <button class="modal-close" onclick="document.getElementById('runCampaignModal').remove()">&times;</button>
            </div>
            <div class="modal-body">
                ${senderInfo}
                <div style="margin-top:12px; padding:12px; background:rgba(34,197,94,0.08); border-radius:8px; border:1px solid rgba(34,197,94,0.2);">
                    <p style="margin:0 0 8px 0; font-weight:600; color:#22c55e;">What will happen:</p>
                    <ul style="margin:0; padding-left:20px; color:rgba(255,255,255,0.8); font-size:13px; line-height:1.8;">
                        <li><strong>Step 1</strong> email will be sent to <strong>all leads</strong> right now</li>
                        <li>Steps 2–${totalSteps} will be sent <strong>automatically</strong> based on delay &amp; conditions</li>
                        <li>Campaign status will change to <strong>Active</strong></li>
                        <li>Leads who reply will be excluded from follow-ups</li>
                    </ul>
                </div>
            </div>
            <div class="modal-footer">
                <button class="modal-btn cancel-btn" onclick="document.getElementById('runCampaignModal').remove()">Cancel</button>
                <button class="modal-btn send-btn" id="runCampaignBtn" onclick="runCampaign('${campaignId}')">
                    🚀 Start Campaign
                </button>
            </div>
        </div>
    </div>`;

    document.body.insertAdjacentHTML('beforeend', modalHtml);
}

async function runCampaign(campaignId) {
    const btn = document.getElementById('runCampaignBtn');
    btn.disabled = true;
    btn.textContent = 'Starting...';

    try {
        await sendToAllLeads(campaignId, 1);
        addSystemMessage('🟢 Campaign is now ACTIVE. Follow-up emails will be sent automatically based on your delay & condition settings.');
        const runModal = document.getElementById('runCampaignModal');
        if (runModal) runModal.remove();
    } catch (error) {
        addSystemMessage(`❌ Failed to start campaign: ${error.message}`);
        btn.disabled = false;
        btn.textContent = '🚀 Start Campaign';
    }
}


// ─── Test Campaign Modal (sends ALL steps to a single test email) ───

async function showTestCampaignModal(campaignId, totalSteps) {
    const existing = document.getElementById('testCampaignModal');
    if (existing) existing.remove();

    const gmailStatus = await getGmailStatus();

    let senderInfo;
    if (gmailStatus.connected) {
        senderInfo = `<div class="gmail-connected-banner">
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none"><circle cx="8" cy="8" r="7" stroke="#22c55e" stroke-width="1.5"/><path d="M5 8l2 2 4-4" stroke="#22c55e" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>
            Sending from <strong>${gmailStatus.gmail_address}</strong> (OAuth)
        </div>`;
    } else {
        senderInfo = `<div class="gmail-not-connected">
            <p>Emails will be sent via SMTP fallback.</p>
        </div>`;
    }

    const modalHtml = `
    <div id="testCampaignModal" class="email-modal" style="display:flex;">
        <div class="modal-content">
            <div class="modal-header">
                <h3 class="modal-title">🧪 Test Run (Single Email)</h3>
                <button class="modal-close" onclick="document.getElementById('testCampaignModal').remove()">&times;</button>
            </div>
            <div class="modal-body">
                ${senderInfo}
                <div style="margin-top:12px; padding:12px; background:rgba(245,158,11,0.08); border-radius:8px; border:1px solid rgba(245,158,11,0.2);">
                    <p style="margin:0; font-size:13px; color:rgba(255,255,255,0.8);">
                        <strong>Step 1</strong> sends immediately. Steps 2–${totalSteps} send automatically after their configured delays — exactly like a real campaign run, but for one recipient only.
                        All <code style="background:rgba(255,255,255,0.1);padding:1px 4px;border-radius:3px;">{{first_name}}</code> and other placeholders will use the name you enter below.
                    </p>
                </div>
                <div class="form-group" style="margin-top:12px;">
                    <label for="testCampaignName" style="color:rgba(255,255,255,0.7); font-size:13px;">Recipient Name</label>
                    <input type="text" id="testCampaignName" placeholder="e.g. John Smith" class="form-input"
                           style="width:100%; padding:10px; margin-top:4px; background:rgba(255,255,255,0.05); border:1px solid rgba(255,255,255,0.15); border-radius:6px; color:#fff;" />
                </div>
                <div class="form-group" style="margin-top:8px;">
                    <label for="testCampaignEmail" style="color:rgba(255,255,255,0.7); font-size:13px;">Recipient Email</label>
                    <input type="email" id="testCampaignEmail" placeholder="john@company.com" class="form-input"
                           style="width:100%; padding:10px; margin-top:4px; background:rgba(255,255,255,0.05); border:1px solid rgba(255,255,255,0.15); border-radius:6px; color:#fff;" />
                </div>
            </div>
            <div class="modal-footer">
                <button class="modal-btn cancel-btn" onclick="document.getElementById('testCampaignModal').remove()">Cancel</button>
                <button class="modal-btn send-btn" id="testCampaignBtn" onclick="testCampaign('${campaignId}', ${totalSteps})">
                    🧪 Send Test Run
                </button>
            </div>
        </div>
    </div>`;

    document.body.insertAdjacentHTML('beforeend', modalHtml);
}

async function testCampaign(campaignId, totalSteps) {
    const recipientName = document.getElementById('testCampaignName')?.value.trim();
    const testEmail = document.getElementById('testCampaignEmail')?.value.trim();

    if (!testEmail) {
        alert('Please enter a recipient email address');
        return;
    }

    const btn = document.getElementById('testCampaignBtn');
    btn.disabled = true;
    btn.textContent = 'Sending Step 1...';

    try {
        updateStatus('Sending Step 1 now...', 'active');

        const response = await apiFetch(`${API_BASE_URL}/campaigns/send-to-leads/`, {
            method: 'POST',
            headers: getAuthHeaders(),
            body: JSON.stringify({
                campaign_id: campaignId,
                step_order: 1,
                test_mode: true,
                test_email: testEmail,
                recipient_name: recipientName || '',
                session_id: sessionId
            })
        });

        const data = await response.json();
        if (response.ok && data.success) {
            const displayName = recipientName ? `${recipientName} <${testEmail}>` : testEmail;
            addSystemMessage(
                `✅ Test run started for ${displayName}.\n` +
                `Step 1 sent immediately.` +
                (totalSteps > 1 ? ` Steps 2–${totalSteps} will be sent automatically after their configured delays.` : '')
            );
            updateStatus('Test run started', 'active');
            // Refresh My Campaigns panel so the test lead shows in stats
            if (typeof loadMyCampaigns === 'function') loadMyCampaigns();
        } else {
            addSystemMessage(`❌ Test run failed: ${data.error}`);
            updateStatus('Send failed', 'error');
            btn.disabled = false;
            btn.textContent = '🧪 Send Test Run';
            return;
        }
    } catch (error) {
        addSystemMessage(`❌ Test run failed: ${error.message}`);
        updateStatus('Send failed', 'error');
        btn.disabled = false;
        btn.textContent = '🧪 Send Test Run';
        return;
    }

    document.getElementById('testCampaignModal').remove();
}


// ─── Inbox Functions ────────────────────────────────────────────────────────

let currentInboxFilter = 'all';
let inboxRefreshInterval = null;
let currentInboxPage = 1;
const INBOX_PAGE_SIZE = 10;
let currentThreadData = null; // { lastReplyId, subject }

// Show inbox view
async function showInboxView() {
    // Hide chat panel, show inbox
    document.querySelector('.chat-panel').style.display = 'none';
    const infoPanel = document.querySelector('.info-panel');
    if (infoPanel) infoPanel.style.display = 'none';
    document.getElementById('inboxPanel').style.display = 'block';
    document.getElementById('profilePanel').style.display = 'none';

    // Update nav active state
    document.querySelectorAll('.nav-item').forEach(item => item.classList.remove('active'));
    document.querySelectorAll('.nav-item')[1].classList.add('active'); // Inbox is 2nd item

    // Auto-fetch replies in background (don't block inbox load)
    autoFetchReplies();

    // Load inbox
    loadInbox();

    // Start auto-refresh every 30 seconds
    if (inboxRefreshInterval) clearInterval(inboxRefreshInterval);
    inboxRefreshInterval = setInterval(loadInbox, 30000);
}

// Show campaign view
function showCampaignView() {
    // Show chat panel, hide inbox
    document.querySelector('.chat-panel').style.display = 'flex';
    const infoPanel = document.querySelector('.info-panel');
    if (infoPanel) infoPanel.style.display = 'block';
    document.getElementById('inboxPanel').style.display = 'none';
    document.getElementById('profilePanel').style.display = 'none';

    // Update nav active state
    document.querySelectorAll('.nav-item').forEach(item => item.classList.remove('active'));
    document.querySelectorAll('.nav-item')[0].classList.add('active'); // Campaigns is 1st item

    // Stop auto-refresh
    if (inboxRefreshInterval) {
        clearInterval(inboxRefreshInterval);
        inboxRefreshInterval = null;
    }
}

// Show profile view
function showProfileView() {
    document.querySelector('.chat-panel').style.display = 'none';
    const infoPanel = document.querySelector('.info-panel');
    if (infoPanel) infoPanel.style.display = 'none';
    document.getElementById('inboxPanel').style.display = 'none';
    document.getElementById('profilePanel').style.display = 'block';

    document.querySelectorAll('.nav-item').forEach(item => item.classList.remove('active'));
    document.querySelectorAll('.nav-item')[3].classList.add('active');

    // Populate user card from the default account
    apiFetch(`${AUTH_BASE_URL}/me/`, { headers: getAuthHeaders() })
        .then(r => r.json())
        .then(data => {
            const user = data && data.user;
            if (!user) return;
            const fullName = [user.first_name, user.last_name].filter(Boolean).join(' ') || user.email || '—';
            const initials = fullName.split(' ').map(w => w[0]).join('').toUpperCase().slice(0, 2) || '?';
            document.getElementById('profileAvatar').textContent = initials;
            document.getElementById('profileName').textContent = fullName;
            document.getElementById('profileEmailDisplay').textContent = user.email || '—';
        })
        .catch(() => {});

    loadCompanyProfile();
}

async function loadCompanyProfile() {
    try {
        const res = await apiFetch(`${API_BASE_URL}/business-profile/`, { headers: getAuthHeaders() });
        if (!res.ok) return;
        const d = await res.json();
        document.getElementById('ci_name').value = d.name || '';
        document.getElementById('ci_description').value = d.description || '';
        document.getElementById('ci_industry').value = d.industry || '';
        document.getElementById('ci_employee_count').value = d.employee_count || '';
        document.getElementById('ci_services').value = d.services || '';
        document.getElementById('ci_tone').value = d.tone_preferences || '';
        document.getElementById('ci_website').value = d.website || '';
    } catch (e) { }
}

async function saveCompanyProfile() {
    const btn = document.querySelector('.company-save-btn');
    const statusEl = document.getElementById('companyInfoStatus');
    btn.disabled = true;
    btn.textContent = 'Saving…';
    statusEl.textContent = '';
    statusEl.className = 'company-info-status';
    try {
        const res = await apiFetch(`${API_BASE_URL}/business-profile/`, {
            method: 'POST',
            headers: { ...getAuthHeaders(), 'Content-Type': 'application/json' },
            body: JSON.stringify({
                name: document.getElementById('ci_name').value.trim(),
                description: document.getElementById('ci_description').value.trim(),
                industry: document.getElementById('ci_industry').value.trim(),
                employee_count: document.getElementById('ci_employee_count').value.trim(),
                services: document.getElementById('ci_services').value.trim(),
                tone_preferences: document.getElementById('ci_tone').value.trim(),
                website: document.getElementById('ci_website').value.trim(),
            })
        });
        const d = await res.json();
        if (d.success) {
            statusEl.textContent = 'Saved';
            statusEl.classList.add('status-ok');
        } else {
            statusEl.textContent = d.error || 'Failed';
            statusEl.classList.add('status-err');
        }
    } catch (e) {
        statusEl.textContent = 'Error saving';
        statusEl.classList.add('status-err');
    } finally {
        btn.disabled = false;
        btn.textContent = 'Save';
        setTimeout(() => { statusEl.textContent = ''; statusEl.className = 'company-info-status'; }, 3000);
    }
}

// Load inbox emails (paginated)
async function loadInbox(page) {
    if (page !== undefined) currentInboxPage = page;
    const inboxList = document.getElementById('inboxList');

    try {
        const statusParam = currentInboxFilter !== 'all' ? `&status=${currentInboxFilter}` : '';
        const response = await apiFetch(`${API_BASE_URL}/inbox/?page=${currentInboxPage}&page_size=${INBOX_PAGE_SIZE}${statusParam}`, {
            headers: getAuthHeaders()
        });

        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }

        const data = await response.json();

        if (data.success && data.emails && data.emails.length > 0) {
            displayInboxEmails(data.emails, data.pagination);
            updateInboxBadge(data.emails.filter(e => e.has_unread_replies).length);
        } else {
            inboxList.innerHTML = `
                <div class="inbox-empty">
                    <svg width="48" height="48" viewBox="0 0 48 48" fill="none"><rect x="6" y="10" width="36" height="28" rx="2" stroke="currentColor" stroke-width="2" opacity="0.3"/><path d="M6 10l18 15 18-15" stroke="currentColor" stroke-width="2" opacity="0.5"/></svg>
                    <p>No emails yet</p>
                    <small>Sent emails will appear here</small>
                </div>
            `;
        }

    } catch (error) {
        console.error('Error loading inbox:', error);
        inboxList.innerHTML = `
            <div class="inbox-empty">
                <p>❌ Failed to load inbox</p>
                <small>${error.message}</small>
            </div>
        `;
    }
}

// Display inbox emails with pagination
function displayInboxEmails(emails, pagination) {
    const inboxList = document.getElementById('inboxList');

    let html = '';
    emails.forEach(email => {
        const statusClass = email.status;
        const hasReply = email.reply_count > 0;
        const unread = email.has_unread_replies;

        html += `
            <div class="inbox-item ${unread ? 'unread' : ''}" onclick="openEmailThread('${email.id}')">
                <div class="inbox-item-header">
                    <div class="inbox-recipient">
                        <span class="recipient-name">${escapeHtml(email.recipient_name || email.recipient_email)}</span>
                        <span class="recipient-email">${escapeHtml(email.recipient_email)}</span>
                    </div>
                    <div class="inbox-meta">
                        <span class="inbox-status status-${statusClass}">${statusClass}</span>
                        <span class="inbox-time">${formatTimeAgo(email.sent_at)}</span>
                    </div>
                </div>
                <div class="inbox-subject">${escapeHtml(email.subject)}</div>
                <div class="inbox-preview">${escapeHtml(email.body_preview || email.body)}</div>
                ${hasReply ? `
                    <div class="inbox-replies-section">
                        <div class="inbox-reply-header">
                            <svg width="12" height="12" viewBox="0 0 12 12" fill="none"><path d="M1 6h8M5 2l4 4-4 4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>
                            ${email.reply_count} ${email.reply_count === 1 ? 'reply' : 'replies'}
                            ${unread ? '<span class="unread-dot"></span>' : ''}
                        </div>
                        ${email.replies && email.replies.length > 0 ? email.replies.map(reply => `
                            <div class="inbox-reply-item ${!reply.is_read ? 'unread-reply' : ''}">
                                <div class="reply-header">
                                    <span class="reply-from">${escapeHtml(reply.from_name || reply.from_email)}</span>
                                    <span class="reply-time">${formatTimeAgo(reply.received_at)}</span>
                                    <span class="reply-sentiment sentiment-${reply.sentiment || 'not_analyzed'}">${reply.sentiment ? reply.sentiment.replace('_', ' ') : 'Not analyzed'}</span>
                                </div>
                                <div class="reply-body">${escapeHtml(stripQuotedReply(reply.body_preview || reply.body))}</div>
                            </div>
                        `).join('') : ''}
                    </div>
                ` : ''}
            </div>
        `;
    });

    // ── Pagination controls ──────────────────────────────────────────────
    if (pagination && pagination.total_pages > 1) {
        const { page, total_pages, total, has_prev, has_next } = pagination;
        const startItem = (page - 1) * INBOX_PAGE_SIZE + 1;
        const endItem = Math.min(page * INBOX_PAGE_SIZE, total);

        // Build page buttons (show max 5 around current)
        let pageButtons = '';
        const startPage = Math.max(1, page - 2);
        const endPage = Math.min(total_pages, page + 2);

        if (startPage > 1) {
            pageButtons += `<button class="page-btn" onclick="loadInbox(1)">1</button>`;
            if (startPage > 2) pageButtons += `<span class="page-ellipsis">…</span>`;
        }
        for (let p = startPage; p <= endPage; p++) {
            pageButtons += `<button class="page-btn ${p === page ? 'active' : ''}" onclick="loadInbox(${p})">${p}</button>`;
        }
        if (endPage < total_pages) {
            if (endPage < total_pages - 1) pageButtons += `<span class="page-ellipsis">…</span>`;
            pageButtons += `<button class="page-btn" onclick="loadInbox(${total_pages})">${total_pages}</button>`;
        }

        html += `
            <div class="inbox-pagination">
                <span class="page-info">${startItem}–${endItem} of ${total}</span>
                <div class="page-controls">
                    <button class="page-nav-btn" onclick="loadInbox(${page - 1})" ${!has_prev ? 'disabled' : ''}>
                        <svg width="14" height="14" viewBox="0 0 14 14" fill="none"><path d="M9 3L5 7l4 4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>
                    </button>
                    ${pageButtons}
                    <button class="page-nav-btn" onclick="loadInbox(${page + 1})" ${!has_next ? 'disabled' : ''}>
                        <svg width="14" height="14" viewBox="0 0 14 14" fill="none"><path d="M5 3l4 4-4 4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>
                    </button>
                </div>
            </div>
        `;
    }

    inboxList.innerHTML = html;
}

// Filter inbox
function filterInbox(filter) {
    currentInboxFilter = filter;
    currentInboxPage = 1;  // Reset to page 1 on filter change

    // Update button states
    document.querySelectorAll('.filter-btn').forEach(btn => btn.classList.remove('active'));
    event.target.classList.add('active');

    // Reload inbox with filter
    loadInbox();
}

// Open email thread
async function openEmailThread(sentEmailId) {
    const modal = document.getElementById('emailThreadModal');
    const threadBody = document.getElementById('threadBody');

    modal.style.display = 'flex';
    threadBody.innerHTML = '<div class="thread-loading">Loading thread...</div>';

    try {
        const response = await apiFetch(`${API_BASE_URL}/inbox/thread/${sentEmailId}/`, {
            headers: getAuthHeaders()
        });

        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }

        const data = await response.json();

        if (data.success && data.thread) {
            displayEmailThread(data.thread);
        } else {
            threadBody.innerHTML = '<div class="thread-error">Failed to load thread</div>';
        }

    } catch (error) {
        console.error('Error loading thread:', error);
        threadBody.innerHTML = `<div class="thread-error">❌ ${error.message}</div>`;
    }
}

// Display email thread
function displayEmailThread(thread) {
    const threadBody = document.getElementById('threadBody');
    const sentEmail = thread.sent_email;
    const replies = thread.replies || [];

    // Track the last received reply so the footer Reply button knows what to reply to
    const lastReply = replies.length > 0 ? replies[replies.length - 1] : null;
    currentThreadData = lastReply
        ? { lastReplyId: lastReply.id, subject: sentEmail.subject }
        : null;

    // Show/hide footer Reply button based on whether there are replies to respond to
    const replyBtn = document.getElementById('threadReplyBtn');
    if (replyBtn) replyBtn.style.display = lastReply ? 'inline-flex' : 'none';

    let html = `
        <div class="thread-message sent">
            <div class="thread-msg-header">
                <div class="thread-from">
                    <strong>You</strong>
                    <span class="thread-email">${escapeHtml(sentEmail.sent_from)}</span>
                </div>
                <div class="thread-time">${formatDateTime(sentEmail.sent_at)}</div>
            </div>
            <div class="thread-subject">${escapeHtml(sentEmail.subject)}</div>
            <div class="thread-msg-body">${formatEmailBody(sentEmail.body)}</div>
            <div class="thread-status">Status: ${sentEmail.status}</div>
        </div>
    `;

    replies.forEach((reply, idx) => {
        const sentimentClass = reply.sentiment || 'neutral';
        const isLast = idx === replies.length - 1;
        html += `
            <div class="thread-message received">
                <div class="thread-msg-header">
                    <div class="thread-from">
                        <strong>${escapeHtml(reply.from_name || reply.from_email)}</strong>
                        <span class="thread-email">${escapeHtml(reply.from_email)}</span>
                    </div>
                    <div class="thread-time">${formatDateTime(reply.received_at)}</div>
                </div>
                <div class="thread-subject">${escapeHtml(reply.subject)}</div>
                <div class="thread-msg-body">${escapeHtml(stripQuotedReply(reply.body))}</div>
                <div class="thread-message-footer">
                    <div class="thread-sentiment sentiment-${sentimentClass}">
                        Sentiment: ${reply.sentiment || 'Not analyzed'}
                    </div>
                    ${isLast ? `<button class="thread-quick-reply-btn" onclick="showReplyForm('${reply.id}', '${escapeHtml(sentEmail.subject)}')">↩ Reply</button>` : ''}
                </div>
            </div>
        `;
    });

    threadBody.innerHTML = html;
}

// Close thread modal
function closeThreadModal() {
    document.getElementById('emailThreadModal').style.display = 'none';
    cancelReply();
    currentThreadData = null;
    loadInbox();
}

// Show reply compose area inside thread modal
function showReplyForm(replyId, subject) {
    // Allow call from footer button (uses currentThreadData) or inline reply button
    const id = replyId || (currentThreadData && currentThreadData.lastReplyId);
    const subj = subject || (currentThreadData && currentThreadData.subject) || '';
    if (!id) return;

    currentThreadData = { lastReplyId: id, subject: subj };

    document.getElementById('threadFooterBtns').style.display = 'none';
    const compose = document.getElementById('threadReplyCompose');
    compose.style.display = 'flex';
    document.getElementById('threadReplySubject').value = `Re: ${subj}`;
    document.getElementById('threadReplyBody').value = '';
    document.getElementById('threadReplyBody').focus();
}

function cancelReply() {
    document.getElementById('threadReplyCompose').style.display = 'none';
    document.getElementById('threadFooterBtns').style.display = 'flex';
}

async function sendReplyToReply() {
    if (!currentThreadData || !currentThreadData.lastReplyId) return;

    const body = document.getElementById('threadReplyBody').value.trim();
    const subject = document.getElementById('threadReplySubject').value.trim();

    if (!body) {
        showNotification('Please write a reply before sending.', 'warning');
        return;
    }

    const sendBtn = document.querySelector('#threadReplyCompose .send-reply-btn');
    sendBtn.disabled = true;
    sendBtn.textContent = 'Sending...';

    try {
        const response = await apiFetch(`${API_BASE_URL}/inbox/send-reply/`, {
            method: 'POST',
            headers: { ...getAuthHeaders(), 'Content-Type': 'application/json' },
            body: JSON.stringify({
                reply_id: currentThreadData.lastReplyId,
                body,
                subject,
            }),
        });

        const data = await response.json();

        if (data.success) {
            showNotification(`Reply sent to ${data.sent_to}`, 'success');
            cancelReply();
            loadInbox();
        } else {
            showNotification(data.error || 'Failed to send reply', 'error');
        }
    } catch (err) {
        console.error('Send reply failed:', err);
        showNotification('Failed to send reply. Check your email configuration.', 'error');
    } finally {
        sendBtn.disabled = false;
        sendBtn.textContent = 'Send Reply';
    }
}

// Update inbox badge
function updateInboxBadge(count) {
    const badge = document.getElementById('inboxBadge');
    if (count > 0) {
        badge.textContent = count;
        badge.style.display = 'inline-block';
    } else {
        badge.style.display = 'none';
    }
}

// Format time ago
function formatTimeAgo(isoString) {
    const date = new Date(isoString);
    const now = new Date();
    const seconds = Math.floor((now - date) / 1000);

    if (seconds < 60) return 'Just now';
    if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
    if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`;
    if (seconds < 604800) return `${Math.floor(seconds / 86400)}d ago`;

    return date.toLocaleDateString();
}

// Format date time
function formatDateTime(isoString) {
    const date = new Date(isoString);
    return date.toLocaleString('en-US', {
        month: 'short',
        day: 'numeric',
        year: 'numeric',
        hour: 'numeric',
        minute: '2-digit',
        hour12: true
    });
}


// ─── Fetch Gmail Replies Functions ─────────────────────────────────────────

function showFetchRepliesModal() {
    const modal = document.getElementById('fetchRepliesModal');
    if (modal) modal.style.display = 'flex';
}

function closeFetchRepliesModal() {
    const modal = document.getElementById('fetchRepliesModal');
    if (modal) modal.style.display = 'none';
}

async function fetchGmailReplies() {
    const sinceDays = parseInt(document.getElementById('fetchSinceDays').value || '7');

    const fetchBtn = document.querySelector('#fetchRepliesModal .send-btn');
    const originalText = fetchBtn.textContent;
    fetchBtn.disabled = true;
    fetchBtn.textContent = 'Fetching...';

    try {
        updateStatus('Fetching replies from Gmail...', 'active');

        const response = await apiFetch(`${API_BASE_URL}/inbox/fetch-replies/`, {
            method: 'POST',
            headers: getAuthHeaders(),
            body: JSON.stringify({ since_days: sinceDays })
        });

        const data = await response.json();

        if (response.ok && data.success) {
            closeFetchRepliesModal();
            const message = data.new_replies > 0
                ? `✅ Fetched ${data.new_replies} new ${data.new_replies === 1 ? 'reply' : 'replies'}!`
                : '✅ No new replies found';
            addSystemMessage(message);
            updateStatus('Replies fetched', 'active');
            loadInbox();
        } else {
            throw new Error(data.error || 'Failed to fetch replies');
        }

    } catch (error) {
        console.error('Fetch replies error:', error);
        alert(`Failed to fetch replies: ${error.message}`);
        updateStatus('Fetch failed', 'error');
    } finally {
        fetchBtn.disabled = false;
        fetchBtn.textContent = originalText;
    }
}

// ─── Emails Sent Stat ────────────────────────────────────────────────────────

async function loadMyCampaigns() {
    const countEl = document.getElementById('emailsSentCount');
    if (!countEl) return;

    try {
        const res = await apiFetch(`${API_BASE_URL}/campaigns/list/`, {
            headers: getAuthHeaders()
        });
        if (!res.ok) return;

        const data = await res.json();
        if (!data.success) return;

        const campaigns = data.campaigns || [];
        const totalSent = campaigns.reduce((sum, c) => sum + ((c.stats || {}).total_sent || 0), 0);
        countEl.textContent = totalSent;
    } catch (e) {
        console.error('Load emails sent stat error:', e);
    }
}

// ─── Email Edit Functions ────────────────────────────────────────────────────

function htmlToPlainText(html) {
    // Convert block-level tags to newlines before stripping
    let text = html
        .replace(/<\/p>/gi, '\n')
        .replace(/<br\s*\/?>/gi, '\n')
        .replace(/<\/div>/gi, '\n')
        .replace(/<p[^>]*>/gi, '')
        .replace(/<div[^>]*>/gi, '')
        .replace(/<[^>]+>/g, '');
    // Decode HTML entities
    const tmp = document.createElement('div');
    tmp.innerHTML = text;
    text = tmp.textContent || tmp.innerText || '';
    // Collapse 3+ consecutive newlines to 2
    return text.replace(/\n{3,}/g, '\n\n').trim();
}

function plainTextToHtml(text) {
    // Split on double newline for paragraphs, single newline for <br>
    const paragraphs = text.split(/\n\n+/);
    return paragraphs
        .map(p => `<p>${escapeHtml(p).replace(/\n/g, '<br>')}</p>`)
        .join('');
}

function openEditEmailModal(emailId, triggerBtn) {
    const step = triggerBtn.closest('.email-step');
    const subjectEl = step.querySelector('.email-subject-val');
    const bodyEl = step.querySelector('.email-body-html');

    const currentSubject = subjectEl ? subjectEl.textContent : '';
    // Convert stored HTML to readable plain text for the textarea
    const currentBodyPlain = bodyEl ? htmlToPlainText(bodyEl.innerHTML) : '';

    const existing = document.getElementById('editEmailModal');
    if (existing) existing.remove();

    const modal = document.createElement('div');
    modal.id = 'editEmailModal';
    modal.className = 'email-modal';
    modal.style.display = 'flex';
    modal.dataset.emailId = emailId;

    modal.innerHTML = `
        <div class="modal-content" style="max-width:600px;width:90%;">
            <div class="modal-header">
                <h3 class="modal-title">✏️ Edit Email</h3>
                <button class="modal-close" onclick="closeEditEmailModal()">&times;</button>
            </div>
            <div class="modal-body">
                <div class="form-group">
                    <label>Subject</label>
                    <input type="text" id="editSubjectInput" class="form-input" value="${escapeHtml(currentSubject)}" />
                </div>
                <div class="form-group">
                    <label>Body</label>
                    <textarea id="editBodyInput" class="form-input" rows="12" style="resize:vertical;font-family:var(--font-body);font-size:13px;line-height:1.6;white-space:pre-wrap;">${escapeHtml(currentBodyPlain)}</textarea>
                </div>
                <div id="editEmailStatus" style="display:none;font-size:13px;margin-top:8px;"></div>
            </div>
            <div class="modal-footer">
                <button class="modal-btn cancel-btn" onclick="closeEditEmailModal()">Cancel</button>
                <button class="modal-btn send-btn" id="saveEditBtn" onclick="saveEditEmail()">Save Changes</button>
            </div>
        </div>`;

    document.body.appendChild(modal);
}

function closeEditEmailModal() {
    const modal = document.getElementById('editEmailModal');
    if (modal) modal.remove();
}

async function saveEditEmail() {
    const modal = document.getElementById('editEmailModal');
    const emailId = modal.dataset.emailId;
    const subject = document.getElementById('editSubjectInput').value.trim();
    const plainText = document.getElementById('editBodyInput').value;
    // Convert plain text back to HTML for storage
    const bodyHtml = plainTextToHtml(plainText);
    const statusEl = document.getElementById('editEmailStatus');
    const saveBtn = document.getElementById('saveEditBtn');

    saveBtn.disabled = true;
    saveBtn.textContent = 'Saving…';
    statusEl.style.display = 'none';

    try {
        const res = await apiFetch(`${API_BASE_URL}/emails/update/`, {
            method: 'POST',
            headers: getAuthHeaders(),
            body: JSON.stringify({ email_id: emailId, subject, body: bodyHtml })
        });
        const data = await res.json();

        if (res.ok && data.success) {
            // Update the displayed values in the chat without re-rendering
            document.querySelectorAll('.email-step').forEach(stepEl => {
                const editBtn = stepEl.querySelector(`button[onclick*="'${emailId}'"]`);
                if (!editBtn) return;
                const subjectVal = stepEl.querySelector('.email-subject-val');
                const bodyWrap = stepEl.querySelector('.email-body-wrap');
                if (subjectVal) subjectVal.textContent = subject;
                if (bodyWrap) bodyWrap.innerHTML = `<div class="email-body-html">${bodyHtml}</div>`;
            });
            closeEditEmailModal();
            addSystemMessage('✅ Email updated. Changes will be used when sending.');
        } else {
            statusEl.style.display = 'block';
            statusEl.style.color = 'var(--red)';
            statusEl.textContent = data.error || 'Failed to save changes.';
            saveBtn.disabled = false;
            saveBtn.textContent = 'Save Changes';
        }
    } catch (e) {
        statusEl.style.display = 'block';
        statusEl.style.color = 'var(--red)';
        statusEl.textContent = 'Request failed. Is the server running?';
        saveBtn.disabled = false;
        saveBtn.textContent = 'Save Changes';
    }
}

// Auto-fetch replies using OAuth (no credentials needed)
let lastFetchTime = null;

async function autoFetchReplies() {
    if (lastFetchTime && (Date.now() - lastFetchTime) < 2 * 60 * 1000) return;

    try {
        const response = await apiFetch(`${API_BASE_URL}/inbox/fetch-replies/`, {
            method: 'POST',
            headers: getAuthHeaders(),
            body: JSON.stringify({ since_days: 1 })
        });
        const data = await response.json();
        if (response.ok && data.success && data.new_replies > 0) {
            loadInbox();
            updateInboxBadge(data.new_replies);
        }
        lastFetchTime = Date.now();
    } catch (error) {
        console.error('Auto-fetch error:', error);
    }
}

// ─── Show uploaded leads in chat after redirect from lead-upload.html ──────

function formatUploadedLeadsMessage(result) {
    const imported = result.imported || 0;
    const updated = result.updated || 0;
    const skipped = result.skipped || 0;
    const total = imported + updated;
    const listPart = result.lead_list_name ? ` to "${result.lead_list_name}"` : '';

    const lines = [];
    lines.push(
        `Uploaded ${total} lead${total === 1 ? '' : 's'}${listPart} — ${imported} new, ${updated} updated` +
        (skipped ? `, ${skipped} skipped` : '') + '.'
    );

    const leads = result.leads || [];
    if (leads.length) {
        lines.push('');
        leads.forEach(l => {
            const name = [l.first_name, l.last_name].filter(Boolean).join(' ') || l.email;
            const extra = [l.title, l.company_name].filter(Boolean).join(' at ');
            lines.push(`• ${name} (${l.email})${extra ? ` — ${extra}` : ''}`);
        });
        if (result.leads_truncated) {
            lines.push(`…and ${total - leads.length} more.`);
        }
    }

    lines.push('');
    lines.push('You can now ask me to create a campaign for these leads.');

    return lines.join('\n');
}

async function showUploadedLeadsIfAny() {
    const raw = sessionStorage.getItem('leadUploadResult');
    if (!raw) return;
    sessionStorage.removeItem('leadUploadResult');

    let result;
    try {
        result = JSON.parse(raw);
    } catch (e) {
        return;
    }

    const existingSessionId = sessionStorage.getItem('currentSessionId');
    if (existingSessionId) {
        // Resume the chat the upload was linked to — don't start a new one,
        // or the campaign created next would lose the lead_list_id link.
        sessionId = existingSessionId;
        startBtn.style.display = 'none';
        inputArea.style.display = 'flex';
        updateStatus('Connected - Ready to chat', 'active');
    } else if (startBtn.style.display !== 'none') {
        await initializeConversation();
    }
    addBotMessage(formatUploadedLeadsMessage(result));
}

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', showUploadedLeadsIfAny);
} else {
    showUploadedLeadsIfAny();
}