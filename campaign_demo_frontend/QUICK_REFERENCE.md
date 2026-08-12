# 🚀 Quick Reference Card

## Start Demo in 3 Steps

```bash
# 1. Start Django
python manage.py runserver

# 2. Open Browser
http://localhost:8080/

# 3. Click "Start New Campaign"
```

## Example Messages to Try

```
"Find CEOs in fintech from USA"
"Search for CTOs in healthcare from California"
"I need VPs of Sales in SaaS companies"
"Find executives in technology from New York"
```

## What Happens Automatically

1. ✅ Session created
2. ✅ Parameters extracted (title, industry, location)
3. ✅ Lead search triggered automatically
4. ✅ Results displayed in cards
5. ✅ Ready for campaign creation

## URLs

| Page | URL |
|------|-----|
| Main Demo | http://localhost:8080/ |
| Connection Test | http://localhost:8080/test_backend.html |
| Status Page | http://localhost:8080/status.html |

## API Endpoints

| Endpoint | Purpose |
|----------|---------|
| `/conversation/init/` | Create session |
| `/conversation/message/` | Send message |
| `/leads/search/people/` | Search leads (auto) |

## Troubleshooting

| Problem | Solution |
|---------|----------|
| Backend not responding | `python manage.py runserver` |
| CORS error | Restart Django after settings change |
| No leads found | Try broader criteria |
| Search not triggering | Check browser console (F12) |

## Demo Flow (30 seconds)

```
1. Click "Start New Campaign"
2. Type: "Find CEOs in fintech from USA"
3. Watch automatic search
4. See lead results
5. Type: "Yes, create campaign"
6. Done! ✅
```

## Key Features to Show

- 💬 Conversational interface
- 🔍 Automatic lead search
- 📊 Beautiful results display
- ⚡ Real-time updates
- 🎯 Smart parameter extraction

## Files Structure

```
campaign_demo_frontend/
├── index.html              # Main interface
├── app.js                  # Logic + API calls
├── styles.css              # Styling
├── test_backend.html       # Testing tool
├── DEMO_SCRIPT.md          # Full demo guide
└── QUICK_REFERENCE.md      # This file
```

## Configuration

```javascript
// app.js
const API_BASE_URL = 'http://localhost:8000/api/agent/v1';
const DEFAULT_TENANT_ID = 'demo-tenant-001';
```

## Support Files

- `README.md` - Full documentation
- `QUICK_START.md` - Setup guide
- `LEAD_SEARCH_DEMO.md` - Search feature details
- `DEMO_SCRIPT.md` - Presentation script
- `SETUP_COMPLETE.md` - Setup summary

---

**Need Help?** Check browser console (F12) or Django logs!
