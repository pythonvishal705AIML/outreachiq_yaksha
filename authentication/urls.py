from django.urls import path
from django.views.decorators.csrf import csrf_exempt
from .views import MeView, HealthCheckView
from .gmail_views import (
    GmailConnectView, GmailCallbackView, GmailStatusView, GmailDisconnectView,
    EmailConfigView,
)

urlpatterns = [
    path('me/', csrf_exempt(MeView.as_view()), name='me'),
    path('health/', csrf_exempt(HealthCheckView.as_view()), name='health'),

    # Gmail OAuth
    path('gmail/connect/', csrf_exempt(GmailConnectView.as_view()), name='gmail_connect'),
    path('gmail/callback/', csrf_exempt(GmailCallbackView.as_view()), name='gmail_callback'),
    path('gmail/status/', csrf_exempt(GmailStatusView.as_view()), name='gmail_status'),
    path('gmail/disconnect/', csrf_exempt(GmailDisconnectView.as_view()), name='gmail_disconnect'),

    # Gmail App Password config (name + gmail + key)
    path('email-config/', csrf_exempt(EmailConfigView.as_view()), name='email_config'),
]
