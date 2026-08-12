# 🔧 Troubleshooting Guide

## Error: "Failed to send message. Please try again."

This error means the frontend cannot communicate with the backend. Follow these steps:

### Step 1: Check Django Server

```bash
# Start Django server
python manage.py runserver
```

You should see:
```
Starting development server at http://127.0.0.1:8000/
Quit the server with CTRL-BREAK.
```

### Step 2: Test Backend Directly

Open in browser:
```
http://localhost:8000/admin/
```

If you see Django admin login page → Backend is running ✅
If you see "can't reach this page" → Backend is NOT running ❌

### Step 3: Use Debug Console

Open: http://localhost:8080/debug.html

Click buttons in order:
1. "Check Config" - Should show configuration
2. "Test Backend" - Should show backend reachable
3. "Test Init" - Should create session
4. "Test Message" - Should send message
5. "Test Full Flow" - Should complete entire flow

### Step 4: Check Browser Console

1. Press F12 to open DevTools
2. Go to "Console" tab
3. Look for errors (red text)

Common errors:

#### "Failed to fetch"
- Django server not running
- Wrong API URL
- Network issue

**Fix:** Start Django server

#### "CORS policy"
- CORS not configured
- Wrong origin

**Fix:** Check project/settings.py has:
```python
CORS_ALLOWED_ORIGINS = [
    'http://localhost:8080',
    'http://127.0.0.1:8080',
]
```

#### "403 Forbidden"
- AGENT_RUNTIME_ENABLED = False
- Tenant not in allowlist

**Fix:** Check project/settings.py has:
```python
AGENT_RUNTIME_ENABLED = True
AGENT_RUNTIME_TENANT_ALLOWLIST = []  # Empty = allow all
```

#### "400 Bad Request"
- Missing tenant_id
- Invalid request format

**Fix:** Check app.js has correct format

### Step 5: Check Django Logs

Look at the terminal where Django is running.

**Good logs:**
```
[16/Apr/2026 22:48:26] "POST /api/agent/v1/conversation/init/ HTTP/1.1" 201
[16/Apr/2026 22:48:27] "POST /api/agent/v1/conversation/message/ HTTP/1.1" 200
```

**Bad logs:**
```
[16/Apr/2026 22:48:26] "POST /api/agent/v1/conversation/init/ HTTP/1.1" 400
[16/Apr/2026 22:48:27] "POST /api/agent/v1/conversation/message/ HTTP/1.1" 403
```

### Step 6: Test with Postman

If frontend fails, test backend directly:

**Test 1: Init**
```
POST http://localhost:8000/api/agent/v1/conversation/init/
Headers: Content-Type: application/json
Body: {
  "tenant_id": "demo-tenant-001",
  "text": ""
}
```

Expected: 201 Created with session_id

**Test 2: Message**
```
POST http://localhost:8000/api/agent/v1/conversation/message/
Headers: Content-Type: application/json
Body: {
  "session_id": "<session_id_from_step_1>",
  "text": "Hello"
}
```

Expected: 200 OK with reply

### Step 7: Check Database

```bash
python manage.py shell
```

```python
from api.models import ConversationSession
print(ConversationSession.objects.count())
# Should show number of sessions
```

If error → Database not connected

### Step 8: Restart Everything

```bash
# 1. Stop Django (Ctrl+C)
# 2. Stop frontend server (Ctrl+C)
# 3. Restart Django
python manage.py runserver

# 4. Restart frontend (in new terminal)
cd campaign_demo_frontend
python -m http.server 8080

# 5. Clear browser cache (Ctrl+Shift+Delete)
# 6. Refresh page (Ctrl+F5)
```

## Common Issues & Solutions

### Issue: "tenant_id is required"

**Cause:** Frontend not sending tenant_id

**Fix:** Check app.js line ~15:
```javascript
const DEFAULT_TENANT_ID = 'demo-tenant-001';
```

### Issue: "session not found"

**Cause:** Session expired or invalid

**Fix:** Click "Start New Campaign" again

### Issue: "agent runtime is not enabled"

**Cause:** AGENT_RUNTIME_ENABLED = False

**Fix:** In project/settings.py:
```python
AGENT_RUNTIME_ENABLED = True
```

### Issue: No response from bot

**Cause:** Backend processing error

**Fix:** Check Django logs for errors

### Issue: CORS error in console

**Cause:** CORS not configured

**Fix:** 
1. Install: `pip install django-cors-headers`
2. Add to settings.py INSTALLED_APPS: `'corsheaders'`
3. Add to MIDDLEWARE: `'corsheaders.middleware.CorsMiddleware'`
4. Add: `CORS_ALLOWED_ORIGINS = ['http://localhost:8080']`
5. Restart Django

## Quick Diagnostic Commands

```bash
# Check if Django is running
curl http://localhost:8000/admin/

# Check if frontend is running
curl http://localhost:8080/

# Test init endpoint
curl -X POST http://localhost:8000/api/agent/v1/conversation/init/ \
  -H "Content-Type: application/json" \
  -d '{"tenant_id":"demo-tenant-001","text":""}'

# Check Django processes
ps aux | grep manage.py

# Check port 8000
netstat -ano | findstr :8000

# Check port 8080
netstat -ano | findstr :8080
```

## Still Not Working?

1. Open debug.html: http://localhost:8080/debug.html
2. Run "Test Full Flow"
3. Copy all output
4. Check Django terminal for errors
5. Check browser console (F12)
6. Review error messages

## Contact Support

If still stuck, provide:
- Browser console errors (F12)
- Django terminal logs
- Debug console output
- Steps to reproduce
- Operating system
- Python version
- Django version
