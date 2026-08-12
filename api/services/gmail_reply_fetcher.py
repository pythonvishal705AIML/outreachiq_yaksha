"""
Gmail Reply Fetcher Service
Fetches replies from Gmail inbox and matches them to sent campaign emails
"""

import logging
import imaplib
import email
from email.header import decode_header
from datetime import datetime, timedelta
from django.conf import settings
from api.models import SentEmail, EmailReply

logger = logging.getLogger(__name__)


class GmailReplyFetcher:
    """
    Fetches replies from Gmail using IMAP and matches them to sent emails.
    """

    def __init__(self, email_address: str = None, app_password: str = None):
        self.email_address = email_address or getattr(settings, "GMAIL_USER", "")
        self.app_password = app_password or getattr(settings, "GMAIL_APP_PASSWORD", "")
        self.imap_server = "imap.gmail.com"
        self.imap_port = 993

    def fetch_replies(self, since_days: int = 7) -> dict:
        """
        Fetch replies from Gmail inbox for the last N days.
        
        Args:
            since_days: Number of days to look back for replies
            
        Returns:
            dict with success status, new_replies count, and errors
        """
        if not self.email_address or not self.app_password:
            return {
                "success": False,
                "error": "Gmail credentials not configured. Set GMAIL_USER and GMAIL_APP_PASSWORD in .env"
            }

        try:
            # Connect to Gmail IMAP
            mail = imaplib.IMAP4_SSL(self.imap_server, self.imap_port)
            mail.login(self.email_address, self.app_password)
            
            # Select inbox
            mail.select("INBOX")
            
            # Calculate date for search
            since_date = (datetime.now() - timedelta(days=since_days)).strftime("%d-%b-%Y")
            
            # Search for emails since date
            status, messages = mail.search(None, f'(SINCE {since_date})')
            
            if status != "OK":
                return {"success": False, "error": "Failed to search inbox"}
            
            email_ids = messages[0].split()
            new_replies = 0
            errors = []
            
            logger.info(f"GmailReplyFetcher: Found {len(email_ids)} emails to process")
            
            # Process each email
            for email_id in email_ids:
                try:
                    # Fetch email
                    status, msg_data = mail.fetch(email_id, "(RFC822)")
                    
                    if status != "OK":
                        continue
                    
                    # Parse email
                    raw_email = msg_data[0][1]
                    email_message = email.message_from_bytes(raw_email)
                    
                    # Extract email details
                    from_email = self._extract_email(email_message.get("From", ""))
                    from_name = self._extract_name(email_message.get("From", ""))
                    subject = self._decode_header(email_message.get("Subject", ""))
                    date_str = email_message.get("Date", "")
                    
                    # Get email body
                    body = self._get_email_body(email_message)
                    
                    # Check if this is a reply to a sent email
                    sent_email = self._find_matching_sent_email(from_email, subject)

                    # Use Message-ID header as unique key to prevent duplicates
                    imap_message_id = email_message.get("Message-ID", "").strip()

                    if sent_email:
                        # Check if reply already exists by Message-ID (unique per email)
                        already_exists = (
                            imap_message_id and
                            EmailReply.objects.filter(metadata__imap_message_id=imap_message_id).exists()
                        ) or (
                            not imap_message_id and
                            EmailReply.objects.filter(
                                from_email=from_email,
                                body=body,
                            ).exists()
                        )

                        if not already_exists:
                            # Create new reply
                            reply = EmailReply.objects.create(
                                sent_email=sent_email,
                                from_email=from_email,
                                from_name=from_name,
                                subject=subject,
                                body=body,
                                is_read=False,
                                sentiment=self._analyze_sentiment(body),
                                metadata={"imap_message_id": imap_message_id} if imap_message_id else {},
                            )
                            
                            # Update sent email status
                            if sent_email.status != 'replied':
                                sent_email.status = 'replied'
                                sent_email.replied_at = reply.received_at
                                sent_email.save()
                            
                            new_replies += 1
                            logger.info(f"GmailReplyFetcher: New reply from {from_email}")
                
                except Exception as e:
                    logger.error(f"GmailReplyFetcher: Error processing email {email_id}: {e}")
                    errors.append(str(e))
            
            # Close connection
            mail.close()
            mail.logout()
            
            return {
                "success": True,
                "new_replies": new_replies,
                "total_processed": len(email_ids),
                "errors": errors
            }
            
        except imaplib.IMAP4.error as e:
            logger.error(f"GmailReplyFetcher: IMAP error: {e}")
            return {
                "success": False,
                "error": f"Gmail IMAP error: {str(e)}. Check your App Password."
            }
        except Exception as e:
            logger.error(f"GmailReplyFetcher: Error: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e)
            }

    def _extract_email(self, from_field: str) -> str:
        """Extract email address from 'From' field."""
        if "<" in from_field and ">" in from_field:
            return from_field.split("<")[1].split(">")[0].strip()
        return from_field.strip()

    def _extract_name(self, from_field: str) -> str:
        """Extract name from 'From' field."""
        if "<" in from_field:
            return from_field.split("<")[0].strip().strip('"')
        return ""

    def _decode_header(self, header: str) -> str:
        """Decode email header."""
        if not header:
            return ""
        
        decoded_parts = decode_header(header)
        decoded_string = ""
        
        for part, encoding in decoded_parts:
            if isinstance(part, bytes):
                decoded_string += part.decode(encoding or "utf-8", errors="ignore")
            else:
                decoded_string += part
        
        return decoded_string

    def _get_email_body(self, email_message) -> str:
        """Extract email body (plain text preferred)."""
        body = ""
        
        if email_message.is_multipart():
            for part in email_message.walk():
                content_type = part.get_content_type()
                content_disposition = str(part.get("Content-Disposition"))
                
                # Skip attachments
                if "attachment" in content_disposition:
                    continue
                
                # Get plain text
                if content_type == "text/plain":
                    try:
                        body = part.get_payload(decode=True).decode(errors="ignore")
                        break
                    except:
                        pass
                
                # Fallback to HTML
                if not body and content_type == "text/html":
                    try:
                        body = part.get_payload(decode=True).decode(errors="ignore")
                    except:
                        pass
        else:
            try:
                body = email_message.get_payload(decode=True).decode(errors="ignore")
            except:
                body = str(email_message.get_payload())
        
        return body.strip()

    def _find_matching_sent_email(self, from_email: str, subject: str) -> SentEmail:
        """
        Find the sent email that this reply is responding to.
        Matches by recipient email and subject line.
        """
        # Remove "Re:", "RE:", "Fwd:" etc. from subject
        clean_subject = subject
        for prefix in ["Re:", "RE:", "re:", "Fwd:", "FWD:", "fwd:"]:
            clean_subject = clean_subject.replace(prefix, "").strip()
        
        # Try exact match first
        sent_email = SentEmail.objects.filter(
            recipient_email__iexact=from_email,
            subject__icontains=clean_subject
        ).order_by('-sent_at').first()
        
        if sent_email:
            return sent_email
        
        # Try matching just by recipient email (most recent)
        sent_email = SentEmail.objects.filter(
            recipient_email__iexact=from_email
        ).order_by('-sent_at').first()
        
        return sent_email

    def _analyze_sentiment(self, body: str) -> str:
        """
        Simple sentiment analysis based on keywords.
        Returns: positive, negative, neutral, interested, not_interested
        """
        body_lower = body.lower()
        
        # Interested keywords
        interested_keywords = [
            "interested", "schedule", "call", "meeting", "demo", "learn more",
            "tell me more", "sounds good", "yes", "absolutely", "definitely",
            "would love", "let's talk", "when can we"
        ]
        
        # Not interested keywords
        not_interested_keywords = [
            "not interested", "no thank", "unsubscribe", "remove me",
            "stop", "don't contact", "not at this time", "pass"
        ]
        
        # Positive keywords
        positive_keywords = [
            "great", "excellent", "perfect", "awesome", "fantastic",
            "thank you", "thanks", "appreciate"
        ]
        
        # Negative keywords
        negative_keywords = [
            "disappointed", "unhappy", "frustrated", "angry", "terrible",
            "awful", "bad", "poor"
        ]
        
        # Check for interested
        if any(keyword in body_lower for keyword in interested_keywords):
            return "interested"
        
        # Check for not interested
        if any(keyword in body_lower for keyword in not_interested_keywords):
            return "not_interested"
        
        # Check for positive
        if any(keyword in body_lower for keyword in positive_keywords):
            return "positive"
        
        # Check for negative
        if any(keyword in body_lower for keyword in negative_keywords):
            return "negative"
        
        return "neutral"
