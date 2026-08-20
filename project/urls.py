# backend/urls.py
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.views.generic import RedirectView
from django.views.static import serve
from project.views import js_config, run_campaign_sequences

urlpatterns = [
    path('', RedirectView.as_view(url='/campaign_demo_frontend/index.html')),
    path('js-config/', js_config),
    path('internal/run-sequences/', run_campaign_sequences),
    path("admin/", admin.site.urls),
    path("api/auth/", include("authentication.urls")),
    path("api/", include("api.urls")),
    path("api/agent/v1/", include("agent_runtime.api.urls")),
    
    # Serve campaign demo frontend
    path("campaign_demo_frontend/<path:path>", serve, {
        'document_root': settings.BASE_DIR / 'campaign_demo_frontend',
    }),
    path("campaign_demo_frontend/", RedirectView.as_view(url='/campaign_demo_frontend/index.html')),
]

# Serve static files in development
if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)