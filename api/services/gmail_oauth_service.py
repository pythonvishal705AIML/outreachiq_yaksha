import base64
import logging
from datetime import datetime, timedelta, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from django.conf import settings
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

logger = logging.getLogger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/userinfo.email",
]


class GmailOAuthService:
    """Sends emails via Gmail API using per-user OAuth tokens."""

    def __init__(self, user):
        self.user = user
        self._token = None
        self._load_token()

    def _load_token(self):
        from authentication.models import UserGmailToken
        if not self.user or not getattr(self.user, 'is_authenticated', False):
            return
        try:
            self._token = UserGmailToken.objects.get(user=self.user)
        except UserGmailToken.DoesNotExist:
            self._token = None

    def is_connected(self):
        return self._token is not None

    def _get_credentials(self):
        if not self._token:
            raise ValueError("Gmail not connected. User must connect their Gmail account first.")

        creds = Credentials(
            token=self._token.access_token or None,
            refresh_token=self._token.refresh_token,
            client_id=settings.GOOGLE_CLIENT_ID,
            client_secret=settings.GOOGLE_CLIENT_SECRET,
            token_uri="https://oauth2.googleapis.com/token",
            scopes=SCOPES,
        )

        if not creds.valid:
            creds.refresh(Request())
            self._token.access_token = creds.token
            if creds.expiry:
                expiry = creds.expiry
                if expiry.tzinfo is None:
                    expiry = expiry.replace(tzinfo=timezone.utc)
                self._token.token_expiry = expiry
            self._token.save(update_fields=["access_token", "token_expiry"])

        return creds

    def send_email(self, to_email: str, subject: str, body: str) -> dict:
        try:
            creds = self._get_credentials()
            service = build("gmail", "v1", credentials=creds)

            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = self._token.gmail_address
            msg["To"] = to_email
            mime_type = "html" if body.strip().startswith("<") else "plain"
            msg.attach(MIMEText(body, mime_type))

            raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
            service.users().messages().send(userId="me", body={"raw": raw}).execute()

            logger.info(f"GmailOAuthService: sent to {to_email} from {self._token.gmail_address}")
            return {"success": True, "sender": self._token.gmail_address}

        except Exception as e:
            logger.error(f"GmailOAuthService: error sending to {to_email}: {e}", exc_info=True)
            return {"success": False, "error": str(e)}

    def fetch_replies(self, since_days: int = 7) -> dict:
        """Fetch replies from Gmail INBOX via Gmail API and match to SentEmail records."""
        try:
            from api.models import SentEmail, EmailReply
            creds = self._get_credentials()
            service = build("gmail", "v1", credentials=creds)

            after_date = (datetime.now(timezone.utc) - timedelta(days=since_days)).strftime("%Y/%m/%d")
            query = f"in:inbox after:{after_date}"

            result = service.users().messages().list(userId="me", q=query, maxResults=200).execute()
            messages = result.get("messages", [])

            new_replies = 0
            errors = []

            sent_emails = {se.recipient_email: se for se in SentEmail.objects.filter(
                sent_at__gte=datetime.now(timezone.utc) - timedelta(days=since_days + 30)
            )}

            for msg_ref in messages:
                try:
                    msg = service.users().messages().get(
                        userId="me", id=msg_ref["id"], format="full"
                    ).execute()

                    headers = {h["name"].lower(): h["value"] for h in msg["payload"].get("headers", [])}
                    from_email = headers.get("from", "")
                    subject = headers.get("subject", "")
                    date_str = headers.get("date", "")

                    # Extract plain email address from "Name <email>" format
                    import re
                    match = re.search(r'<(.+?)>', from_email)
                    sender_addr = match.group(1) if match else from_email.strip()

                    sent_email = sent_emails.get(sender_addr)
                    if not sent_email:
                        continue

                    if EmailReply.objects.filter(gmail_message_id=msg_ref["id"]).exists():
                        continue

                    # Extract body text
                    body_text = ""
                    payload = msg["payload"]
                    if "parts" in payload:
                        for part in payload["parts"]:
                            if part["mimeType"] == "text/plain" and part.get("body", {}).get("data"):
                                body_text = base64.urlsafe_b64decode(part["body"]["data"]).decode("utf-8", errors="replace")
                                break
                    elif payload.get("body", {}).get("data"):
                        body_text = base64.urlsafe_b64decode(payload["body"]["data"]).decode("utf-8", errors="replace")

                    try:
                        received_at = datetime.strptime(date_str[:25].strip(), "%a, %d %b %Y %H:%M:%S")
                        received_at = received_at.replace(tzinfo=timezone.utc)
                    except Exception:
                        received_at = datetime.now(timezone.utc)

                    from api.services.gmail_reply_fetcher import GmailReplyFetcher
                    sentiment = GmailReplyFetcher()._analyze_sentiment(body_text)

                    EmailReply.objects.create(
                        sent_email=sent_email,
                        from_email=sender_addr,
                        from_name=from_email.split("<")[0].strip().strip('"'),
                        subject=subject,
                        body=body_text,
                        body_preview=body_text[:200],
                        received_at=received_at,
                        gmail_message_id=msg_ref["id"],
                        is_read=False,
                        sentiment=sentiment,
                    )
                    sent_email.status = "replied"
                    sent_email.save(update_fields=["status"])
                    new_replies += 1

                except Exception as e:
                    errors.append(str(e))

            return {"success": True, "new_replies": new_replies, "total_processed": len(messages), "errors": errors}

        except Exception as e:
            logger.error(f"GmailOAuthService.fetch_replies: {e}", exc_info=True)
            return {"success": False, "error": str(e)}

    def send_bulk(self, recipients: list, subject: str, body: str) -> dict:
        sent, failed = [], []
        try:
            creds = self._get_credentials()
            service = build("gmail", "v1", credentials=creds)
            mime_type = "html" if body.strip().startswith("<") else "plain"
        except Exception as e:
            return {"sent": [], "failed": [{"email": r, "error": str(e)} for r in recipients]}

        for email in recipients:
            try:
                msg = MIMEMultipart("alternative")
                msg["Subject"] = subject
                msg["From"] = self._token.gmail_address
                msg["To"] = email
                msg.attach(MIMEText(body, mime_type))
                raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
                service.users().messages().send(userId="me", body={"raw": raw}).execute()
                sent.append(email)
            except Exception as e:
                failed.append({"email": email, "error": str(e)})

        return {"sent": sent, "failed": failed}
