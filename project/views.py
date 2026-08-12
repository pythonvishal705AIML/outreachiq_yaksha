import json
from django.http import HttpResponse
from django.conf import settings


def js_config(request):
    server_url = getattr(settings, 'SERVER_URL', 'http://localhost:8000')
    config = {
        'SERVER_URL': server_url,
        'API_BASE_URL': f'{server_url}/api/agent/v1',
        'AUTH_BASE_URL': f'{server_url}/api/auth',
    }
    js = f'window.CONFIG = {json.dumps(config)};'
    return HttpResponse(js, content_type='application/javascript')
