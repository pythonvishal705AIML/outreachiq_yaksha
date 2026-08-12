# 🚀 Quick Start Guide

## Step 1: Start Django Backend

Open a terminal and run:

```bash
python manage.py runserver
```

You should see:
```
Starting development server at http://127.0.0.1:8000/
```

## Step 2: Frontend is Already Running

Your frontend is already running on port 8080!

## Step 3: Test Backend Connection

Open in your browser:
```
http://localhost:8080/test_backend.html
```

Click "Test Connection" button. If you see ✅ success messages, you're ready!

## Step 4: Use the Demo

Open the main demo:
```
http://localhost:8080/
```

Click "Start New Campaign" and start chatting!

## Troubleshooting

### ❌ Connection Failed

**If Django is not running:**
```bash
# In project root directory
python manage.py runserver
```

**If you see CORS errors:**
The settings.py has been updated with:
```python
CORS_ALLOWED_ORIGINS = [
    'http://localhost:8080',
    'http://127.0.0.1:8080',
    ...
]
```

Restart Django server after any settings changes.

**If port 8000 is busy:**
```bash
# Run on different port
python manage.py runserver 8001

# Then update app.js:
const API_BASE_URL = 'http://localhost:8001/api/agent/v1';
```

### 🔍 Check Django Server Status

In browser, visit:
```
http://localhost:8000/api/agent/v1/conversation/init/
```

You should see a JSON response (even if it's an error, it means server is running).

### 📝 View Browser Console

Press F12 in browser and check Console tab for detailed error messages.

## API Endpoints Being Used

- `POST /api/agent/v1/conversation/init/` - Start conversation
- `POST /api/agent/v1/conversation/message/` - Send messages
- `GET /api/agent/v1/conversation/stream/` - Stream responses (optional)

## Demo Flow

1. User clicks "Start New Campaign"
2. System initializes conversation
3. Bot asks for campaign details
4. User provides information through chat
5. Bot guides through each step
6. Campaign is created when complete

## Need Help?

1. Check `test_backend.html` for connection diagnostics
2. Check Django server logs in terminal
3. Check browser console (F12) for frontend errors
4. Verify all endpoints in Postman first
