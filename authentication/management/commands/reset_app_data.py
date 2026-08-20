"""
Management command to wipe all users and campaigns so you can start fresh.

Usage:
    python manage.py reset_app_data           # dry run (shows counts only)
    python manage.py reset_app_data --confirm  # actually deletes
"""

from django.core.management.base import BaseCommand
from django.db import connection


class Command(BaseCommand):
    help = "Delete all users, campaigns, and related data so you can register fresh."

    def add_arguments(self, parser):
        parser.add_argument(
            "--confirm",
            action="store_true",
            help="Actually perform the deletion. Without this flag, only counts are shown.",
        )
        parser.add_argument(
            "--keep-org",
            action="store_true",
            help="Keep the organisation row in the accounts table.",
        )

    def handle(self, *args, **options):
        confirm = options["confirm"]
        keep_org = options["keep_org"]

        # Import here so Django apps are ready
        from authentication.models import User, Organization, RefreshToken, LoginAttempt
        from api.models import Campaign, ConversationSession

        # ── count everything that will go ──────────────────────────────────────
        counts = {
            "Users":              User.objects.count(),
            "Refresh tokens":     RefreshToken.objects.count(),
            "Login attempts":     LoginAttempt.objects.count(),
            "Campaigns":          Campaign.objects.count(),
            "Conversation sessions": ConversationSession.objects.count(),
        }

        if not keep_org:
            counts["Organisations (accounts)"] = Organization.objects.count()

        # Also count cascade targets via raw SQL for visibility
        with connection.cursor() as cur:
            extras = {
                "Campaign steps":    "campaign_steps",
                "Campaign emails":   "campaign_emails",
                "Sent emails":       "sent_emails",
                "Email replies":     "email_replies",
                "ML conversations":  "ml_conversations",
                "Campaign lead statuses": "campaign_lead_status",
            }
            for label, table in extras.items():
                try:
                    cur.execute(f"SELECT COUNT(*) FROM `{table}`")
                    counts[label] = cur.fetchone()[0]
                except Exception:
                    pass  # table may not exist yet

        self.stdout.write("\n── Records that will be deleted ──────────────────────")
        for label, count in counts.items():
            self.stdout.write(f"  {label:<30} {count:>6}")
        self.stdout.write("──────────────────────────────────────────────────────\n")

        if not confirm:
            self.stdout.write(
                self.style.WARNING(
                    "DRY RUN — nothing deleted.\n"
                    "Re-run with --confirm to actually delete everything."
                )
            )
            return

        self.stdout.write(self.style.WARNING("Deleting…"))

        # ── delete campaigns first (avoids FK conflicts) ───────────────────────
        deleted_campaigns, _ = Campaign.objects.all().delete()
        self.stdout.write(f"  Campaigns deleted: {deleted_campaigns}")

        # ── delete conversation sessions ───────────────────────────────────────
        deleted_sessions, _ = ConversationSession.objects.all().delete()
        self.stdout.write(f"  Conversation sessions deleted: {deleted_sessions}")

        # ── delete users (cascades tokens, gmail tokens, sessions, etc.) ───────
        deleted_users, _ = User.objects.all().delete()
        self.stdout.write(f"  Users deleted: {deleted_users}")

        # ── delete login attempt log ───────────────────────────────────────────
        LoginAttempt.objects.all().delete()

        # ── optionally delete organisations ────────────────────────────────────
        if not keep_org:
            deleted_orgs, _ = Organization.objects.all().delete()
            self.stdout.write(f"  Organisations deleted: {deleted_orgs}")
        else:
            self.stdout.write("  Organisations kept (--keep-org was set).")

        self.stdout.write(
            self.style.SUCCESS(
                "\nDone. The app is empty — you can register a new account now."
            )
        )
