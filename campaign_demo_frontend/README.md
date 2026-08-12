# Campaign Creation Demo Frontend

A standalone chatbot-style interface for demonstrating the campaign creation flow.

## Features

- 💬 ChatGPT-like conversational interface
- 🎨 Modern, responsive design
- 🚀 Real-time interaction with backend API
- ✨ Smooth animations and typing indicators
- 📱 Mobile-friendly

## Setup Instructions

### 1. Start Django Backend

```bash
python manage.py runserver
```

The backend should start on `http://localhost:8000`

### 2. Frontend is Already Running

Your frontend is already running on port 8080!
Access it at: `http://localhost:8080`

### 3. Test Connection (Optional)

Open `http://localhost:8080/test_backend.html` and click "Test Connection"

### 4. API Configuration (Already Done!)

The API is already configured to use:
```javascript
const API_BASE_URL = 'http://localhost:8000/api/agent/v1';
```

CORS settings have been added to Django settings.py

### 2. Serve the Frontend

You have several options to run this frontend:

#### Option A: Using Python's built-in server
```bash
cd campaign_demo_frontend
python -m http.server 8080
```
Then open: http://localhost:8080

#### Option B: Using Node.js http-server
```bash
npm install -g http-server
cd campaign_demo_frontend
http-server -p 8080
```

#### Option C: Using VS Code Live Server
1. Install "Live Server" extension in VS Code
2. Right-click on `index.html`
3. Select "Open with Live Server"

#### Option D: Direct file access
Simply open `index.html` in your browser (may have CORS issues)

### 3. Enable CORS on Backend

Add CORS middleware to your Django settings if not already configured:

```python
# In project/settings.py

INSTALLED_APPS = [
    ...
    'corsheaders',
]

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    ...
]

# Allow frontend origin
CORS_ALLOWED_ORIGINS = [
    "http://localhost:8080",
    "http://127.0.0.1:8080",
]

# Or for development, allow all:
CORS_ALLOW_ALL_ORIGINS = True
```

Install django-cors-headers if needed:
```bash
pip install django-cors-headers
```

## Usage Flow

1. Click "Start New Campaign" button
2. The system initializes a conversation
3. Chat with the bot to create your campaign:
   - Provide campaign name
   - Describe target audience
   - Set campaign goals
   - Configure settings
4. The bot guides you through each step
5. Campaign is created when all information is collected

## API Endpoints Used

- `POST /agent/conversation/init/` - Initialize conversation
- `POST /agent/conversation/message/` - Send messages
- `GET /agent/conversation/stream/` - Stream responses (optional)

## File Structure

```
campaign_demo_frontend/
├── index.html          # Main HTML structure
├── styles.css          # All styling and animations
├── app.js             # JavaScript logic and API calls
└── README.md          # This file
```

## Customization

### Change Colors
Edit the gradient colors in `styles.css`:
```css
background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
```

### Modify Messages
Update welcome message in `index.html`:
```html
<div class="welcome-message">
    <p>Your custom welcome message here</p>
</div>
```

### Add Features
- Extend `app.js` to add new functionality
- Add new message types in the UI helper functions
- Implement streaming responses using the stream endpoint

## Troubleshooting

### CORS Errors
- Ensure CORS is properly configured on backend
- Check that API_BASE_URL matches your backend URL

### Connection Failed
- Verify backend is running
- Check network tab in browser DevTools
- Ensure API endpoints are accessible

### Messages Not Appearing
- Check browser console for errors
- Verify API response format matches expected structure
- Test API endpoints directly with Postman first

## Production Deployment

For production:
1. Update API_BASE_URL to production URL
2. Build and minify assets
3. Serve through proper web server (Nginx, Apache)
4. Enable HTTPS
5. Configure proper CORS settings
6. Add authentication if needed

## Browser Support

- Chrome/Edge (latest)
- Firefox (latest)
- Safari (latest)
- Mobile browsers (iOS Safari, Chrome Mobile)
