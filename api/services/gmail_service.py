import smtplib
import logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from django.conf import settings

logger = logging.getLogger(__name__)


class GmailService:
    """Sends emails via SMTP using an App Password (Gmail, Outlook, or any provider)."""

    def __init__(self, sender_email: str = None, app_password: str = None,
                 smtp_host: str = None, smtp_port: int = None, from_name: str = None):
        self.sender_email = sender_email or getattr(settings, "GMAIL_USER", "")
        self.app_password = app_password or getattr(settings, "GMAIL_APP_PASSWORD", "")
        self.smtp_host = smtp_host or "smtp.gmail.com"
        self.smtp_port = smtp_port or 465
        self.from_name = from_name or ""

    def send_email(self, to_email: str, subject: str, body: str) -> dict:
        if not self.sender_email or not self.app_password:
            return {"success": False, "error": "Email credentials not configured."}

        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = f"{self.from_name} <{self.sender_email}>" if self.from_name else self.sender_email
            msg["To"] = to_email
            mime_type = "html" if body.strip().startswith("<") else "plain"
            msg.attach(MIMEText(body, mime_type))

            # Port 587 uses STARTTLS; all other ports (e.g. 465) use SSL
            if self.smtp_port == 587:
                server = smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=15)
                server.ehlo()
                server.starttls()
                server.ehlo()
            else:
                server = smtplib.SMTP_SSL(self.smtp_host, self.smtp_port, timeout=15)
            server.login(self.sender_email, self.app_password)
            server.sendmail(self.sender_email, to_email, msg.as_string())
            server.quit()

            logger.info(f"GmailService: sent to {to_email} | subject: {subject}")
            return {"success": True, "sender": self.sender_email}

        except smtplib.SMTPAuthenticationError:
            logger.error("GmailService: authentication failed")
            return {"success": False, "error": "Authentication failed. Check your email and App Password."}
        except Exception as e:
            logger.error(f"GmailService: error: {e}", exc_info=True)
            return {"success": False, "error": str(e)}

    def send_bulk(self, recipients: list, subject: str, body: str) -> dict:
        sent, failed = [], []
        for email in recipients:
            result = self.send_email(email, subject, body)
            if result.get("success"):
                sent.append(email)
            else:
                failed.append({"email": email, "error": result.get("error")})
        return {"sent": sent, "failed": failed}
