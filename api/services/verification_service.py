import re
import logging
import dns.resolver

logger = logging.getLogger(__name__)

class VerificationService:
    @staticmethod
    def verify_email_dns(email):
        """
        Verifies an email address using DNS MX records via dnspython.
        Returns: (status, details)
        status: 'valid', 'invalid', 'unknown'
        """
        if not email or "@" not in email:
            return "invalid", "Invalid Syntax"
        
        try:
            domain = email.split("@")[1]
        except IndexError:
            return "invalid", "Invalid Syntax (No Domain)"

        # 1. Syntax Check (Regex)
        if not re.match(r"[^@]+@[^@]+\.[^@]+", email):
            return "invalid", "Invalid Syntax Regex"

        # 2. DNS MX Check using dnspython
        try:
            # Query the DNS System specifically for 'MX' (Mail Exchange) records
            records = dns.resolver.resolve(domain, 'MX')
            
            # If successful, we get a list of mail servers
            mx_servers = [record.exchange.to_text() for record in records]
            
            # 3. SMTP Handshake (Deep Verification)
            # Try the first MX server
            primary_mx = mx_servers[0]
            smtp_status, smtp_reason = VerificationService.verify_smtp_handshake(email, primary_mx)
            
            if smtp_status == "invalid":
                return "invalid", f"SMTP Rejected: {smtp_reason}"
            elif smtp_status == "valid":
                return "valid", f"Verified via SMTP ({primary_mx})"
            else:
                # If SMTP failed to connect/timeout (risky or unknown), fallback to DNS valid
                # User requested to hide the 'skipped' detail.
                return "valid", "MX Found"

        except dns.resolver.NoAnswer:
            # Domain exists, but has NO email servers configured
            return "invalid", "Domain exists but has NO MX records (NoAnswer)"
            
        except dns.resolver.NXDOMAIN:
            # The domain itself does not exist
            return "invalid", "Domain does not exist (NXDOMAIN)"
            
        except Exception as e:
            logger.error(f"DNS Check Failed: {e}")
            return "unknown", f"DNS Error: {str(e)}"

    @staticmethod
    def verify_smtp_handshake(email, mx_host):
        """
        Performs a basic SMTP handshake (HELO -> MAIL FROM -> RCPT TO).
        Returns: (status, reason)
        """
        import smtplib
        import socket
        
        try:
            # 1. Connect
            # Timeout is critical 
            server = smtplib.SMTP(mx_host, 25, timeout=5)
            server.set_debuglevel(0)
            
            # 2. HELO/EHLO
            server.helo('verification.test') # In prod, use real hostname
            
            # 3. MAIL FROM
            server.mail('check@verification.test')
            
            # 4. RCPT TO
            code, message = server.rcpt(email)
            server.quit()
            
            # 250 = Accepted
            if code == 250:
                return "valid", "Recipient accepted"
            # 550 = User unknown / Rejected
            elif code >= 500 and code < 600:
                return "invalid", f"Rejected ({code})"
            else:
                return "unknown", f"Unexpected code: {code}"
                
        except (socket.timeout, socket.error) as e:
            return "unknown", "Connection timed out/failed (Port 25 blocked?)"
        except Exception as e:
            return "unknown", str(e)
