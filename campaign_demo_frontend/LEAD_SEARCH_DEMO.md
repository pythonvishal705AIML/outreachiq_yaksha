# 🔍 Lead Search Demo Guide

## Automatic Lead Search Flow

The frontend now automatically triggers lead search when the backend indicates it's ready!

## How It Works

### 1. User Provides Search Criteria

User types something like:
```
"Find CEOs in fintech from USA"
```

### 2. Backend Extracts Parameters

The backend (LeadSearchAgent) extracts:
- Title: CEO
- Industry: fintech
- Location: USA

### 3. Backend Returns next_action

Response includes:
```json
{
  "text": "I captured your lead search parameters...",
  "slots": {
    "title": "CEO",
    "industry": "fintech", 
    "location": "USA"
  },
  "next_action": {
    "type": "call_api",
    "endpoint": "/api/agent/v1/leads/search/people/"
  }
}
```

### 4. Frontend Auto-Triggers Search

When frontend sees `next_action.endpoint === '/api/agent/v1/leads/search/people/'`:
- Automatically calls the people search API
- Shows "🔍 Searching for leads..." message
- Displays results in a nice card format

### 5. Results Displayed

Shows:
- Total count of leads found
- Top 5 leads with:
  - Name
  - Title
  - Company
  - Location
- Search run ID for tracking

## Example Conversation Flow

```
User: "I want to create a campaign"
Bot: "Great! Let's start. What leads do you want to target?"

User: "Find CEOs in fintech from USA"
Bot: "I captured your lead search parameters. You can run people search now."
System: "🔍 Searching for leads based on your criteria..."
Bot: [Shows lead results card with 5 leads]
Bot: "Great! I found these leads for you. Would you like to create a campaign with these leads?"

User: "Yes, create a campaign"
Bot: [Continues with campaign creation flow]
```

## Testing the Flow

### Quick Test
1. Open: http://localhost:8080/
2. Click "Start New Campaign"
3. Type: "Find CEOs in fintech from USA"
4. Watch the automatic lead search trigger!

### Full Test with Backend
1. Ensure Django is running: `python manage.py runserver`
2. Open: http://localhost:8080/test_backend.html
3. Click "Test Connection" - should test all 3 steps:
   - Session init ✅
   - Message send ✅
   - Lead search ✅

## API Endpoints Used

### 1. Conversation Init
```
POST /api/agent/v1/conversation/init/
Body: { "tenant_id": "demo-tenant-001", "text": "" }
```

### 2. Send Message
```
POST /api/agent/v1/conversation/message/
Body: { "session_id": "...", "text": "Find CEOs in fintech from USA" }
```

### 3. Lead Search (Auto-triggered)
```
POST /api/agent/v1/leads/search/people/
Body: {
  "session_id": "...",
  "params": { "title": "CEO", "industry": "fintech", "location": "USA" },
  "page": 1,
  "per_page": 10
}
```

## Customization

### Change Number of Leads Displayed
Edit `app.js`:
```javascript
people.slice(0, 5).forEach((person, index) => {
  // Change 5 to any number
```

### Change Lead Card Styling
Edit `styles.css`:
```css
.lead-item {
  /* Customize colors, spacing, etc. */
}
```

### Add More Lead Fields
Edit `displayLeadResults()` in `app.js`:
```javascript
${person.email ? `<div>📧 ${person.email}</div>` : ''}
${person.phone ? `<div>📱 ${person.phone}</div>` : ''}
```

## Troubleshooting

### Leads Not Showing?
- Check browser console (F12) for errors
- Verify backend returns `next_action` in response
- Check that `params` or `slots` are present

### Search Fails?
- Ensure session_id is valid
- Check Django logs for errors
- Verify Apollo/ZoomInfo credentials are configured

### Wrong Results?
- Check the extracted parameters in bot response
- Verify backend parameter extraction is working
- Test the search endpoint directly in Postman

## Next Steps

After leads are displayed, the flow continues to:
1. Lead selection (select % or specific leads)
2. Campaign creation
3. Campaign approval
4. Sequence generation

All these can be automated similarly by detecting `next_action` in responses!
