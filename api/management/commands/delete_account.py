"""
Management command to permanently delete a user account and all related data.

Usage:
    python manage.py delete_account --email user@example.com
    python manage.py delete_account --email user@example.com --confirm
"""

from django.core.management.base import BaseCommand, CommandError
from django.db import connection


class Command(BaseCommand):
    help = "Permanently delete a user account and all related DB data."

    def add_arguments(self, parser):
        parser.add_argument(
            "--email",
            type=str,
            required=True,
            help="Email address of the account to delete.",
        )
        parser.add_argument(
            "--confirm",
            action="store_true",
            help="Skip the confirmation prompt and delete immediately.",
        )

    def handle(self, *args, **options):
        email = options["email"].strip().lower()

        # ── 1. Resolve user ──────────────────────────────────────────────────
        from authentication.models import User

        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            raise CommandError(f"No user found with email: {email}")

        user_id = str(user.id)
        account_id = user.account_id

        self.stdout.write(f"\nUser      : {email}")
        self.stdout.write(f"User ID   : {user_id}")
        self.stdout.write(f"Account ID: {account_id}\n")

        # ── 2. Confirm ───────────────────────────────────────────────────────
        if not options["confirm"]:
            answer = input(
                "This will permanently delete the account and ALL related data. "
                "Type 'yes' to continue: "
            )
            if answer.strip().lower() != "yes":
                self.stdout.write(self.style.WARNING("Aborted."))
                return

        from api.models import (
            Campaign,
            CampaignContext,
            CampaignEmail,
            CampaignLeadStatus,
            CampaignStep,
            EmailReply,
            MLCampaignContext,
            MLConversation,
            MLGeneration,
            MLSpamAnalysis,
            SentEmail,
            SpamValidationResult,
            AISession,
        )
        from authentication.models import (
            LoginAttempt,
            RefreshToken,
            UserEmailConfig,
            UserGmailToken,
        )

        totals = {}

        def _del(label, qs):
            count, _ = qs.delete()
            totals[label] = count
            if count:
                self.stdout.write(f"  Deleted {label}: {count}")

        # ── 3. Campaign cascade ──────────────────────────────────────────────
        campaign_ids = list(
            Campaign.objects.filter(org_id=account_id).values_list("id", flat=True)
        )
        sent_email_ids = list(
            SentEmail.objects.filter(
                campaign_id__in=[str(c) for c in campaign_ids]
            ).values_list("id", flat=True)
        )
        step_ids = list(
            CampaignStep.objects.filter(
                campaign_id__in=campaign_ids
            ).values_list("id", flat=True)
        )
        email_ids = list(
            CampaignEmail.objects.filter(
                step_id__in=step_ids
            ).values_list("id", flat=True)
        )

        _del("EmailReplies",          EmailReply.objects.filter(sent_email_id__in=sent_email_ids))
        _del("CampaignLeadStatuses",  CampaignLeadStatus.objects.filter(campaign_id__in=campaign_ids))
        _del("SentEmails",            SentEmail.objects.filter(campaign_id__in=[str(c) for c in campaign_ids]))
        _del("MLSpamAnalyses",        MLSpamAnalysis.objects.filter(email_id__in=email_ids))
        _del("SpamValidationResults", SpamValidationResult.objects.filter(email_id__in=email_ids))
        _del("CampaignEmails",        CampaignEmail.objects.filter(step_id__in=step_ids))
        _del("MLGenerations",         MLGeneration.objects.filter(campaign_id__in=campaign_ids))
        _del("CampaignSteps",         CampaignStep.objects.filter(campaign_id__in=campaign_ids))
        _del("MLConversations",       MLConversation.objects.filter(campaign_id__in=campaign_ids))
        _del("MLCampaignContexts",    MLCampaignContext.objects.filter(campaign_id__in=campaign_ids))
        _del("AISessions",            AISession.objects.filter(campaign_id__in=campaign_ids))
        _del("CampaignContexts",      CampaignContext.objects.filter(campaign_id__in=campaign_ids))
        _del("Campaigns",             Campaign.objects.filter(org_id=account_id))

        # ── 4. Auth & config records ─────────────────────────────────────────
        _del("RefreshTokens",   RefreshToken.objects.filter(user=user))
        _del("LoginAttempts",   LoginAttempt.objects.filter(email=email))
        _del("UserGmailTokens", UserGmailToken.objects.filter(user=user))
        _del("UserEmailConfigs",UserEmailConfig.objects.filter(user=user))

        # ── 5. User + Account (raw SQL to skip unmigrated activity tables) ───
        with connection.cursor() as cur:
            cur.execute("DELETE FROM auth_users WHERE email = %s", [email])
            totals["User"] = cur.rowcount
            self.stdout.write(f"  Deleted User (auth_users): {cur.rowcount}")

            if account_id:
                cur.execute("DELETE FROM accounts WHERE id = %s", [account_id])
                totals["Account"] = cur.rowcount
                self.stdout.write(f"  Deleted Account (accounts): {cur.rowcount}")

        # ── 6. Summary ───────────────────────────────────────────────────────
        total_rows = sum(totals.values())
        self.stdout.write(
            self.style.SUCCESS(
                f"\nDone. {total_rows} total rows deleted for '{email}'."
            )
        )
