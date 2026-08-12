from django.urls import path
from django.views.decorators.csrf import csrf_exempt
from .views import (
    SignupView, LoginView, RefreshTokenView, LogoutView,
    MeView, ChangePasswordView, HealthCheckView
)
from .gmail_views import (
    GmailConnectView, GmailCallbackView, GmailStatusView, GmailDisconnectView,
    EmailConfigView,
)

urlpatterns = [
    path('signup/', csrf_exempt(SignupView.as_view()), name='signup'),
    path('login/', csrf_exempt(LoginView.as_view()), name='login'),
    path('refresh/', csrf_exempt(RefreshTokenView.as_view()), name='refresh_token'),
    path('logout/', csrf_exempt(LogoutView.as_view()), name='logout'),
    path('me/', csrf_exempt(MeView.as_view()), name='me'),
    path('change-password/', csrf_exempt(ChangePasswordView.as_view()), name='change_password'),
    path('health/', csrf_exempt(HealthCheckView.as_view()), name='health'),

    # Gmail OAuth
    path('gmail/connect/', csrf_exempt(GmailConnectView.as_view()), name='gmail_connect'),
    path('gmail/callback/', csrf_exempt(GmailCallbackView.as_view()), name='gmail_callback'),
    path('gmail/status/', csrf_exempt(GmailStatusView.as_view()), name='gmail_status'),
    path('gmail/disconnect/', csrf_exempt(GmailDisconnectView.as_view()), name='gmail_disconnect'),

    # Simple SMTP config (App Password)
    path('email-config/', csrf_exempt(EmailConfigView.as_view()), name='email_config'),
]
