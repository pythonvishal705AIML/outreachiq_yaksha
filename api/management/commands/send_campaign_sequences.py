"""
Management Command: send_campaign_sequences
============================================
Runs via cron to auto-send follow-up emails in active campaigns.

Usage:
    python manage.py send_campaign_sequences          # normal run
    python manage.py send_campaign_sequences --dry-run # preview only, no emails sent

Cron setup (every 30 minutes):
    */30 * * * * cd /path/to/squibb && python manage.py send_campaign_sequences >> /var/log/squibb_sequences.log 2>&1
"""

import logging
import time
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone
from django.db import transaction
from django.db.models import F

from api.models import (
    Campaign, CampaignStep, CampaignEmail, CampaignLeadStatus,
    SentEmail, Lead
)

logger = logging.getLogger(__name__)

# Simple file-based lock to prevent overlapping runs
LOCK_TIMEOUT_MINUTES = 60


class Command(BaseCommand):
    help = "Send scheduled follow-up emails for active campaigns"

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Preview what would be sent without actually sending',
        )
        parser.add_argument(
            '--campaign-id',
            type=str,
            help='Process a specific campaign only',
        )
        parser.add_argument(
            '--delay-between-emails',
            type=float,
            default=1.0,
            help='Seconds to wait between individual email sends (rate limiting)',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        campaign_id = options.get('campaign_id')
        delay = options['delay_between_emails']

        if dry_run:
            self.stdout.write(self.style.WARNING("=== DRY RUN MODE — no emails will be sent ==="))

        # ── Acquire Lock ──
        if not self._acquire_lock():
            self.stdout.write(self.style.WARNING("Another instance is already running. Exiting."))
            return

        try:
            self._run(dry_run, campaign_id, delay)
        finally:
            self._release_lock()

    def _run(self, dry_run, campaign_id, delay):
        now = timezone.now()
        self.stdout.write(f"\n[{now.isoformat()}] Starting campaign sequence check...")

        # ── 1. Get active campaigns ──
        campaigns = Campaign.objects.filter(status='active')
        if campaign_id:
            campaigns = campaigns.filter(id=campaign_id)

        if not campaigns.exists():
            self.stdout.write("No active campaigns found.")
            return

        total_sent = 0
        total_skipped = 0
        total_errors = 0

        for campaign in campaigns:
            sent, skipped, errors = self._process_campaign(campaign, now, dry_run, delay)
            total_sent += sent
            total_skipped += skipped
            total_errors += errors

        self.stdout.write(self.style.SUCCESS(
            f"\nDone. Sent: {total_sent} | Skipped: {total_skipped} | Errors: {total_errors}"
        ))

    def _process_campaign(self, campaign, now, dry_run, delay):
        """Process one campaign: check all enrolled leads for pending follow-ups."""
        self.stdout.write(f"\n── Campaign: {campaign.name} ({campaign.id}) ──")

        # Get all steps ordered
        steps = list(CampaignStep.objects.filter(campaign=campaign).order_by('step_order'))
        if not steps:
            self.stdout.write("  No steps defined. Skipping.")
            return 0, 0, 0

        max_step = steps[-1].step_order
        step_map = {s.step_order: s for s in steps}

        # Build email lookup: step_order -> CampaignEmail
        email_map = {}
        for step in steps:
            try:
                email_map[step.step_order] = step.email  # OneToOne reverse
            except CampaignEmail.DoesNotExist:
                self.stdout.write(self.style.WARNING(f"  Step {step.step_order} has no email template. Skipping step."))

        # Get leads that still need emails (not completed/replied/bounced/unsubscribed)
        lead_statuses = CampaignLeadStatus.objects.filter(
            campaign=campaign,
            status__in=['pending', 'in_sequence']
        ).select_related('lead')

        if not lead_statuses.exists():
            self.stdout.write("  No leads pending in sequence.")
            return 0, 0, 0

        # Load the Gmail sender for this campaign's owner
        sender_service, sender_email = self._get_sender(campaign)
        if not sender_service:
            self.stdout.write(self.style.ERROR("  No email sender configured. Skipping campaign."))
            return 0, 0, 0

        # Load user for template replacement
        user = self._get_campaign_user(campaign)

        sent = 0
        skipped = 0
        errors = 0

        for ls in lead_statuses:
            next_step_order = ls.last_step_sent + 1

            # All steps done?
            if next_step_order > max_step:
                ls.status = 'completed'
                ls.save(update_fields=['status', 'updated_at'])
                skipped += 1
                continue

            next_step = step_map.get(next_step_order)
            if not next_step:
                skipped += 1
                continue

            campaign_email = email_map.get(next_step_order)
            if not campaign_email:
                skipped += 1
                continue

            # ── Check delay_days ──
            if ls.last_sent_at:
                eligible_at = ls.last_sent_at + timedelta(days=next_step.delay_days)
                if now < eligible_at:
                    skipped += 1
                    continue  # Too early
            else:
                # First step (pending), send immediately if step_order == 1
                if next_step_order != 1:
                    skipped += 1
                    continue

            # ── Check step_condition ──
            if not self._check_condition(next_step.condition, ls, campaign):
                skipped += 1
                continue

            # ── Ready to send ──
            lead = ls.lead
            if not lead.email:
                skipped += 1
                continue

            # Replace placeholders per lead
            subject = campaign_email.subject or ""
            body = campaign_email.body or ""

            if user:
                from api.services.template_replacer import TemplateReplacer
                replaced = TemplateReplacer.replace_email_content(subject, body, user, lead)
                subject = replaced['subject']
                body = replaced['body']

            lead_name = f"{lead.first_name or ''} {lead.last_name or ''}".strip()

            if dry_run:
                self.stdout.write(f"  [DRY] Would send Step {next_step_order} to {lead.email} ({lead_name})")
                sent += 1
                continue

            # ── Send ──
            try:
                result = sender_service.send_email(lead.email, subject, body)

                if result.get('success'):
                    # Record in SentEmail
                    sent_record = SentEmail.objects.create(
                        campaign_id=str(campaign.id),
                        step_order=next_step_order,
                        recipient_email=lead.email,
                        recipient_name=lead_name,
                        subject=subject,
                        body=body,
                        sent_from=sender_email,
                        status='sent',
                    )

                    # Update lead status
                    ls.last_step_sent = next_step_order
                    ls.last_sent_at = now
                    ls.last_sent_email = sent_record
                    ls.status = 'completed' if next_step_order >= max_step else 'in_sequence'
                    ls.save(update_fields=['last_step_sent', 'last_sent_at', 'last_sent_email', 'status', 'updated_at'])

                    self.stdout.write(self.style.SUCCESS(f"  ✓ Step {next_step_order} → {lead.email}"))
                    sent += 1

                    # Rate limiting
                    time.sleep(delay)
                else:
                    error_msg = result.get('error', 'Unknown error')
                    self.stdout.write(self.style.ERROR(f"  ✗ Step {next_step_order} → {lead.email}: {error_msg}"))
                    errors += 1

                    # If bounced, mark lead
                    if 'bounce' in error_msg.lower() or 'invalid' in error_msg.lower():
                        ls.status = 'bounced'
                        ls.save(update_fields=['status', 'updated_at'])

            except Exception as e:
                self.stdout.write(self.style.ERROR(f"  ✗ Step {next_step_order} → {lead.email}: {e}"))
                logger.error(f"send_campaign_sequences error: {e}", exc_info=True)
                errors += 1

        # Check if campaign is fully completed
        remaining = CampaignLeadStatus.objects.filter(
            campaign=campaign,
            status__in=['pending', 'in_sequence']
        ).count()
        if remaining == 0:
            campaign.status = 'completed'
            campaign.save(update_fields=['status', 'updated_at'])
            self.stdout.write(f"  Campaign marked as completed (all leads done).")

        return sent, skipped, errors

    def _check_condition(self, condition, lead_status, campaign):
        """
        Evaluate the step_condition against the lead's status.
        Returns True if the condition is met (should send).
        """
        if condition == 'always':
            return True

        # Check if lead has replied to ANY email in this campaign
        has_replied = SentEmail.objects.filter(
            campaign_id=str(campaign.id),
            recipient_email=lead_status.lead.email,
            status='replied'
        ).exists()

        if condition == 'not_replied':
            return not has_replied

        if condition == 'replied':
            return has_replied

        # Check open status
        has_opened = SentEmail.objects.filter(
            campaign_id=str(campaign.id),
            recipient_email=lead_status.lead.email,
            status='opened'
        ).exists()

        if condition == 'not_opened':
            return not has_opened

        if condition == 'opened':
            return has_opened

        # Unknown condition — default to send
        return True

    def _get_sender(self, campaign):
        """
        Get the email sender service for a campaign.
        Tries the creator's connected Gmail OAuth account first, then their
        Gmail App Password config, then falls back to the shared system SMTP account.
        Returns (service_instance, sender_email) or (None, None).
        """
        user = None
        if campaign.created_by:
            try:
                from django.contrib.auth import get_user_model
                User = get_user_model()
                user = User.objects.get(id=campaign.created_by)
            except Exception as e:
                logger.warning(f"Could not resolve campaign creator for {campaign.id}: {e}")

        # Try OAuth (per-user Gmail)
        if user:
            try:
                from api.services.gmail_oauth_service import GmailOAuthService
                oauth = GmailOAuthService(user)
                if oauth.is_connected():
                    return oauth, oauth._token.gmail_address
            except Exception as e:
                logger.warning(f"OAuth sender setup failed for campaign {campaign.id}: {e}")

        # Try the creator's own Gmail App Password config
        if user:
            try:
                from authentication.models import UserEmailConfig
                from api.services.gmail_service import GmailService
                cfg = UserEmailConfig.objects.get(user=user)
                return GmailService(
                    sender_email=cfg.from_email,
                    app_password=cfg.app_password,
                    smtp_host=cfg.smtp_host,
                    smtp_port=cfg.smtp_port,
                    from_name=cfg.from_name,
                ), cfg.from_email
            except Exception as e:
                logger.warning(f"App Password sender setup failed for campaign {campaign.id}: {e}")

        # Fallback to the shared system SMTP account
        try:
            from api.services.gmail_service import GmailService
            from django.conf import settings
            smtp_email = getattr(settings, 'GMAIL_USER', '')
            if smtp_email:
                return GmailService(), smtp_email
        except Exception as e:
            logger.warning(f"SMTP sender setup failed: {e}")

        return None, None

    def _get_campaign_user(self, campaign):
        """Get the User who created this campaign (for template replacement)."""
        if campaign.created_by:
            try:
                from django.contrib.auth import get_user_model
                User = get_user_model()
                return User.objects.get(id=campaign.created_by)
            except Exception:
                pass
        return None

    # ── Simple DB-based lock ──

    def _acquire_lock(self):
        """Use a simple DB row as a lock. Returns True if acquired."""
        from django.db import connection
        threshold = timezone.now() - timedelta(minutes=LOCK_TIMEOUT_MINUTES)
        id_col = "SERIAL PRIMARY KEY" if connection.vendor == "postgresql" else "INT PRIMARY KEY"
        upsert = (
            "INSERT INTO campaign_scheduler_lock (id) VALUES (1) ON CONFLICT (id) DO NOTHING"
            if connection.vendor == "postgresql"
            else "INSERT IGNORE INTO campaign_scheduler_lock (id) VALUES (1)"
        )
        try:
            with connection.cursor() as cursor:
                # Create lock table if not exists
                cursor.execute(f"""
                    CREATE TABLE IF NOT EXISTS campaign_scheduler_lock (
                        id {id_col} DEFAULT 1,
                        is_running BOOLEAN DEFAULT FALSE,
                        started_at TIMESTAMP NULL
                    )
                """)
                cursor.execute(upsert)

                # Try to acquire
                cursor.execute("""
                    UPDATE campaign_scheduler_lock
                    SET is_running = TRUE, started_at = %s
                    WHERE id = 1 AND (is_running = FALSE OR started_at < %s)
                """, [timezone.now(), threshold])

                return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"Lock acquire failed: {e}")
            return True  # If lock table fails, proceed anyway

    def _release_lock(self):
        """Release the lock."""
        try:
            from django.db import connection
            with connection.cursor() as cursor:
                cursor.execute("UPDATE campaign_scheduler_lock SET is_running = FALSE WHERE id = 1")
        except Exception as e:
            logger.error(f"Lock release failed: {e}")