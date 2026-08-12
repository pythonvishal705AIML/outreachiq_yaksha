import logging

from django.conf import settings
from django.core import signing
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build

logger = logging.getLogger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/userinfo.email",
]

_STATE_SALT = "gmail-oauth-state"
_STATE_MAX_AGE = 600  # 10 minutes


def _build_flow():
    return Flow.from_client_config(
        {
            "web": {
                "client_id": settings.GOOGLE_CLIENT_ID,
                "client_secret": settings.GOOGLE_CLIENT_SECRET,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": [settings.GOOGLE_REDIRECT_URI],
            }
        },
        scopes=SCOPES,
        redirect_uri=settings.GOOGLE_REDIRECT_URI,
    )


@method_decorator(csrf_exempt, name='dispatch')
class GmailConnectView(APIView):
    """Returns the Google OAuth authorization URL for the user to visit."""

    def get(self, request):
        if not request.user or not request.user.is_authenticated:
            return Response({"error": "Authentication required"}, status=status.HTTP_401_UNAUTHORIZED)
        # Embed a signed user ID in state to survive the unauthenticated callback
        state = signing.dumps(str(request.user.id), salt=_STATE_SALT)
        flow = _build_flow()
        auth_url, _ = flow.authorization_url(
            access_type="offline",
            include_granted_scopes="true",
            prompt="consent",
            state=state,
        )
        return Response({"auth_url": auth_url})


@method_decorator(csrf_exempt, name='dispatch')
class GmailCallbackView(APIView):
    """Handles the OAuth callback, exchanges code for tokens, and saves them."""

    def get(self, request):
        code = request.query_params.get("code")
        state = request.query_params.get("state")

        if not code:
            return Response({"error": "Missing code parameter"}, status=status.HTTP_400_BAD_REQUEST)
        if not state:
            return Response({"error": "Missing state parameter"}, status=status.HTTP_400_BAD_REQUEST)

        # Verify state and recover the user who initiated the flow
        try:
            user_id = signing.loads(state, salt=_STATE_SALT, max_age=_STATE_MAX_AGE)
        except signing.BadSignature:
            return Response({"error": "Invalid or expired state"}, status=status.HTTP_400_BAD_REQUEST)

        from authentication.models import User, UserGmailToken
        try:
            user = User.objects.get(id=user_id, is_active=True)
        except User.DoesNotExist:
            return Response({"error": "User not found"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            flow = _build_flow()
            flow.fetch_token(code=code)
            credentials = flow.credentials

            oauth2_service = build("oauth2", "v2", credentials=credentials)
            user_info = oauth2_service.userinfo().get().execute()
            gmail_address = user_info.get("email")

            if not gmail_address:
                return Response({"error": "Could not retrieve Gmail address"}, status=status.HTTP_400_BAD_REQUEST)

            UserGmailToken.objects.update_or_create(
                user=user,
                defaults={
                    "gmail_address": gmail_address,
                    "refresh_token": credentials.refresh_token or "",
                    "access_token": credentials.token or "",
                    "token_expiry": credentials.expiry,
                },
            )

            logger.info(f"GmailCallbackView: connected {gmail_address} for user {user.email}")
            return Response({
                "success": True,
                "gmail_address": gmail_address,
                "message": "Gmail connected successfully",
            })

        except Exception as e:
            logger.error(f"GmailCallbackView: error: {e}", exc_info=True)
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


@method_decorator(csrf_exempt, name='dispatch')
class GmailStatusView(APIView):
    """Returns whether the current user has connected their Gmail."""

    def get(self, request):
        if not request.user or not request.user.is_authenticated:
            return Response({"error": "Authentication required"}, status=status.HTTP_401_UNAUTHORIZED)
        from authentication.models import UserGmailToken
        try:
            token = UserGmailToken.objects.get(user=request.user)
            return Response({"connected": True, "gmail_address": token.gmail_address})
        except UserGmailToken.DoesNotExist:
            return Response({"connected": False})


@method_decorator(csrf_exempt, name='dispatch')
class GmailDisconnectView(APIView):
    """Removes the user's stored Gmail OAuth token."""

    def delete(self, request):
        if not request.user or not request.user.is_authenticated:
            return Response({"error": "Authentication required"}, status=status.HTTP_401_UNAUTHORIZED)
        from authentication.models import UserGmailToken
        deleted, _ = UserGmailToken.objects.filter(user=request.user).delete()
        if deleted:
            return Response({"success": True, "message": "Gmail disconnected"})
        return Response({"error": "Gmail was not connected"}, status=status.HTTP_404_NOT_FOUND)


# ─── Simple SMTP Config (App Password) ──────────────────────────────────────

@method_decorator(csrf_exempt, name='dispatch')
class EmailConfigView(APIView):
    """Save / get / delete the user's personal SMTP email config (App Password)."""

    def _get_user(self, request):
        """Return the authenticated user or None, checking both JWT middleware and Django auth."""
        user_id = getattr(request, 'user_id', None)
        if user_id:
            return request.user
        user = getattr(request, 'user', None)
        if user and getattr(user, 'is_authenticated', False):
            return user
        logger.warning(f"EmailConfigView: unauthenticated request — user_id={user_id} user={user}")
        return None

    def get(self, request):
        user = self._get_user(request)
        if not user:
            return Response({"error": "Authentication required"}, status=status.HTTP_401_UNAUTHORIZED)
        from authentication.models import UserEmailConfig
        try:
            cfg = UserEmailConfig.objects.get(user=user)
            return Response({
                "configured": True,
                "from_email": cfg.from_email,
                "from_name": cfg.from_name,
                "smtp_host": cfg.smtp_host,
                "smtp_port": cfg.smtp_port,
            })
        except UserEmailConfig.DoesNotExist:
            return Response({"configured": False})

    def post(self, request):
        """Save or update SMTP config. Sends a test email to verify credentials."""
        user = self._get_user(request)
        if not user:
            return Response({"error": "Authentication required"}, status=status.HTTP_401_UNAUTHORIZED)

        from_email = request.data.get("from_email", "").strip()
        app_password = request.data.get("app_password", "").strip()
        from_name = request.data.get("from_name", "").strip()
        smtp_host = request.data.get("smtp_host", "smtp.gmail.com").strip()
        smtp_port = int(request.data.get("smtp_port", 465))

        if not from_email or not app_password:
            return Response({"error": "from_email and app_password are required"}, status=status.HTTP_400_BAD_REQUEST)

        # Verify credentials by sending a test email to the user themselves
        import smtplib
        from email.mime.text import MIMEText
        try:
            msg = MIMEText("Your email is configured correctly in OutreachIQ.")
            msg["Subject"] = "OutreachIQ — Email config verified"
            msg["From"] = f"{from_name} <{from_email}>" if from_name else from_email
            msg["To"] = from_email
            # Port 587 uses STARTTLS; all other ports (e.g. 465) use SSL
            if smtp_port == 587:
                server = smtplib.SMTP(smtp_host, smtp_port, timeout=15)
                server.ehlo()
                server.starttls()
                server.ehlo()
            else:
                server = smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=15)
            server.login(from_email, app_password)
            server.sendmail(from_email, from_email, msg.as_string())
            server.quit()
        except smtplib.SMTPAuthenticationError:
            return Response({"error": "Authentication failed. Check your email and App Password."}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({"error": f"Could not connect: {e}"}, status=status.HTTP_400_BAD_REQUEST)

        from authentication.models import UserEmailConfig
        UserEmailConfig.objects.update_or_create(
            user=user,
            defaults={
                "from_email": from_email,
                "from_name": from_name,
                "smtp_host": smtp_host,
                "smtp_port": smtp_port,
                "app_password": app_password,
            }
        )
        logger.info(f"EmailConfigView: saved config for {user.email} → {from_email}")
        return Response({"success": True, "from_email": from_email, "message": "Email configured. Verification email sent."})

    def delete(self, request):
        user = self._get_user(request)
        if not user:
            return Response({"error": "Authentication required"}, status=status.HTTP_401_UNAUTHORIZED)
        from authentication.models import UserEmailConfig
        deleted, _ = UserEmailConfig.objects.filter(user=user).delete()
        if deleted:
            return Response({"success": True})
        return Response({"error": "No config found"}, status=status.HTTP_404_NOT_FOUND)
