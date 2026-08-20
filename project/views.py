import io
import json
import os

from django.core.management import call_command
from django.http import HttpResponse, JsonResponse
from django.conf import settings
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST


def js_config(request):
    server_url = getattr(settings, 'SERVER_URL', 'http://localhost:8000')
    config = {
        'SERVER_URL': server_url,
        'API_BASE_URL': f'{server_url}/api/agent/v1',
        'AUTH_BASE_URL': f'{server_url}/api/auth',
    }
    js = f'window.CONFIG = {json.dumps(config)};'
    return HttpResponse(js, content_type='application/javascript')


@csrf_exempt
@require_POST
def run_campaign_sequences(request):
    """
    Triggers the `send_campaign_sequences` management command over HTTP.

    Render's free tier has no free cron jobs, so this is meant to be called
    by a scheduled GitHub Actions workflow instead. Protected by a shared
    secret (CRON_SECRET env var) — if that var isn't set, the endpoint is
    disabled entirely.
    """
    expected = os.environ.get("CRON_SECRET")
    if not expected:
        return JsonResponse({"error": "CRON_SECRET is not configured"}, status=503)
    if request.headers.get("X-Cron-Secret") != expected:
        return JsonResponse({"error": "forbidden"}, status=403)

    out = io.StringIO()
    call_command("send_campaign_sequences", stdout=out, stderr=out)
    return JsonResponse({"output": out.getvalue()})
