# Lead Selection & Campaign Creation Flow

## Overview
After collecting leads from Apollo, users can select a percentage of leads and create a campaign with those selected leads.

## Flow Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│  1. APOLLO LEAD SEARCH                                          │
│  POST /api/agent/v1/leads/search/people/                        │
│  ─────────────────────────────────────────────────────────────  │
│  • User describes target audience                               │
│  • Agent searches Apollo for matching leads                     │
│  • Returns: search_run_id + lead results                        │
│  • Stores search_run_id in session state                        │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│  2. DISPLAY LEAD RESULTS                                        │
│  ─────────────────────────────────────────────────────────────  │
│  • Shows top 5 leads with details                               │
│  • Displays total count (e.g., "Found 20 leads")                │
│  • Automatically shows selection panel                          │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│  3. LEAD SELECTION PANEL                                        │
│  ─────────────────────────────────────────────────────────────  │
│  User sees 4 options:                                           │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐          │
│  │ All leads│ │ Top 75%  │ │ Top 50%  │ │ Top 25%  │          │
│  │ 20 leads │ │ 15 leads │ │ 10 leads │ │ 5 leads  │          │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘          │
│                                                                  │
│  User clicks one option to proceed                              │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│  4. LEAD SELECTION API CALL                                     │
│  POST /api/agent/v1/leads/select/                               │
│  ─────────────────────────────────────────────────────────────  │
│  Body: {                                                         │
│    "session_id": "...",                                          │
│    "search_run_id": "...",  // from session state               │
│    "selection_percent": 100 | 75 | 50 | 25                      │
│  }                                                               │
│                                                                  │
│  Backend Actions:                                               │
│  • Selects X% of leads from search results                      │
│  • Creates lead_list in lead_lists_new table                    │
│  • Stores selected_lead_ids in session state                    │
│  • Returns: lead_list_id, selected_count                        │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│  5. CONFIRMATION MESSAGE                                        │
│  ─────────────────────────────────────────────────────────────  │
│  ✅ Selected 15 leads (75%) — lead list created                 │
│                                                                  │
│  Agent: "Great! Now let's build your campaign.                  │
│          What's the goal of this campaign?"                     │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│  6. CAMPAIGN CREATION                                           │
│  POST /api/agent/v1/campaigns/create/                           │
│  ─────────────────────────────────────────────────────────────  │
│  • User provides campaign details (goal, tone, etc.)            │
│  • Agent creates campaign linked to lead_list_id                │
│  • Generates email sequences                                    │
│  • Returns: campaign_id, email sequences                        │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│  7. CAMPAIGN SUMMARY & SEND OPTIONS                             │
│  ─────────────────────────────────────────────────────────────  │
│  Displays:                                                       │
│  • Campaign name and status                                     │
│  • Email sequence steps with preview                            │
│  • For each step:                                               │
│    ┌──────────────┐  ┌──────────────────────┐                  │
│    │ 📧 Send Test │  │ 🚀 Send to All Leads │                  │
│    └──────────────┘  └──────────────────────┘                  │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│  8. SEND CAMPAIGN TO SELECTED LEADS                             │
│  POST /api/agent/v1/campaigns/send-to-leads/                    │
│  ─────────────────────────────────────────────────────────────  │
│  Body: {                                                         │
│    "campaign_id": "...",                                         │
│    "session_id": "...",                                          │
│    "step_order": 1,                                              │
│    "test_mode": false                                            │
│  }                                                               │
│                                                                  │
│  Backend Actions:                                               │
│  • Retrieves selected_lead_ids from session state               │
│  • If not found, auto-runs LeadSelectionService                 │
│  • Sends personalized emails to all selected leads              │
│  • Returns: sent_count, failed_count                            │
└─────────────────────────────────────────────────────────────────┘
```

## Key Features

### 1. Session State Management
All critical IDs are stored in the session state:
- `search_run_id`: Links to Apollo search results
- `lead_list_id`: Links to created lead list
- `selected_lead_ids`: Array of selected lead IDs
- `selection_percent`: Percentage selected (100, 75, 50, 25)

### 2. Flexible Lead Selection
Users can choose:
- **100%**: All leads from search
- **75%**: Top 75% of leads
- **50%**: Top 50% of leads
- **25%**: Top 25% of leads

### 3. Automatic Lead Resolution
The send endpoint intelligently resolves leads:
1. First checks `selected_lead_ids` in session state
2. If not found, automatically runs `LeadSelectionService`
3. Falls back to `lead_list_id` if selection flow fails

### 4. Email Personalization
Email body supports template variables:
- `{{first_name}}`: Lead's first name
- `{{last_name}}`: Lead's last name

## UI Components

### Lead Results Display
```javascript
// Shows top 5 leads with:
- Full name
- Job title
- Company name
- Location
- "... and X more leads" if > 5
```

### Lead Selection Panel
```javascript
// Interactive button grid:
┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐
│ All leads│ │ Top 75%  │ │ Top 50%  │ │ Top 25%  │
│ 20 leads │ │ 15 leads │ │ 10 leads │ │ 5 leads  │
└──────────┘ └──────────┘ └──────────┘ └──────────┘

// Features:
- Hover effects
- Selected state (blue highlight)
- Disabled state after selection
- Loading state ("Selecting...")
```

### Campaign Summary
```javascript
// Displays:
- Campaign name and status badge
- Number of email steps
- Campaign ID (truncated)
- Email preview for each step
- Send test / Send to all buttons
```

## API Endpoints

### 1. Search Leads
```
POST /api/agent/v1/leads/search/people/
Body: { session_id, params, page, per_page }
Response: { people[], search_run_id, pagination }
```

### 2. Select Leads
```
POST /api/agent/v1/leads/select/
Body: { session_id, search_run_id, selection_percent }
Response: { lead_list_id, selected_count, selection_percent }
```

### 3. Create Campaign
```
POST /api/agent/v1/campaigns/create/
Body: { session_id, campaign_name, creation_mode }
Response: { campaign_id, campaign_name, status }
```

### 4. Send to Leads
```
POST /api/agent/v1/campaigns/send-to-leads/
Body: { campaign_id, session_id, step_order, test_mode }
Response: { sent_count, failed_count, total_leads }
```

## Error Handling

### No Search Run
```javascript
if (!lastSearchRunId) {
  addSystemMessage('❌ No search run found. Please search for leads first.');
}
```

### Selection Failed
```javascript
catch (err) {
  addSystemMessage(`❌ Lead selection failed: ${err.message}`);
  // Re-enable buttons for retry
}
```

### No Leads Found
```javascript
if (!leads || leads.length === 0) {
  return Response({
    "error": "No leads found for this campaign. Make sure leads are linked..."
  });
}
```

## Testing the Flow

1. Start conversation: Click "Launch Campaign Builder"
2. Describe audience: "Find CEOs in fintech companies in San Francisco"
3. View results: See lead cards with details
4. Select leads: Click "Top 50%" (or any percentage)
5. Confirm: See "✅ Selected X leads" message
6. Build campaign: Answer agent's questions about campaign goal
7. Review: See campaign summary with email sequences
8. Send: Click "🚀 Send to All Leads"
9. Verify: Check inbox for sent emails

## Database Schema

### lead_lists_new
```sql
id (char 36, PK)
name (varchar)
org_id (varchar)
search_run_id (varchar, FK to search_runs)
created_at (timestamp)
```

### Session State (JSON)
```json
{
  "search_run_id": "uuid",
  "lead_list_id": "uuid",
  "selected_lead_ids": ["id1", "id2", ...],
  "selection_percent": 75,
  "campaign_id": "uuid"
}
```

## Future Enhancements

1. **Custom Selection**: Allow users to manually select specific leads
2. **Lead Scoring**: Show quality scores for each lead
3. **Filters**: Add filters by title, company size, location
4. **Preview**: Show which leads will be selected before confirming
5. **Batch Operations**: Select leads from multiple searches
