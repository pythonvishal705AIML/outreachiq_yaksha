// Configuration file for the Campaign Demo Frontend
// Update these values based on your environment

const CONFIG = {
    // Backend API URL - update if your Django server runs on a different port
    API_BASE_URL: 'http://localhost:8000/api/agent/v1',
    
    // Default tenant ID - the single-user app's auto-created default account (see authentication/middleware.py)
    DEFAULT_TENANT_ID: '465aa02d1a7b5689b20572a0ea30dd9a',
    
    // Alternative configurations for different environments
    ENVIRONMENTS: {
        local: 'http://localhost:8000/api/agent/v1',
        staging: 'https://staging.squibb.ai/api/agent/v1',
        production: 'https://squibb.ai/api/agent/v1'
    },
    
    // Timeout settings (in milliseconds)
    REQUEST_TIMEOUT: 30000,  // 30 seconds
    
    // UI Settings
    TYPING_DELAY: 500,  // Delay before showing typing indicator
    AUTO_SCROLL: true,  // Auto-scroll to bottom on new messages
    
    // Debug mode - set to true to see console logs
    DEBUG: true
};

// Export for use in app.js
if (typeof module !== 'undefined' && module.exports) {
    module.exports = CONFIG;
}
