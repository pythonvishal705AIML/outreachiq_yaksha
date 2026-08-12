"""
Migration: Populate created_by for existing campaigns with NULL values.

This migration attempts to assign campaigns to users based on:
1. Session state user_id (if campaign_id is in session state)
2. First active user in the organization (fallback)
"""

from django.db import migrations


def populate_created_by(apps, schema_editor):
    """Populate created_by for campaigns that have NULL values."""
    Campaign = apps.get_model('api', 'Campaign')
    ConversationSession = apps.get_model('api', 'ConversationSession')
    User = apps.get_model('authentication', 'User')
    
    campaigns_without_user = Campaign.objects.filter(created_by__isnull=True)
    updated_count = 0
    
    print(f"\nFound {campaigns_without_user.count()} campaigns with NULL created_by")
    
    for campaign in campaigns_without_user:
        user_id = None
        
        # Strategy 1: Find session with this campaign_id in state
        sessions = ConversationSession.objects.filter(
            state__campaign_id=str(campaign.id)
        )
        
        for session in sessions:
            state = session.state or {}
            session_user_id = state.get('user_id')
            if session_user_id:
                # Verify user exists and belongs to same org
                try:
                    user = User.objects.get(id=session_user_id, is_active=True)
                    if str(user.account_id) == str(campaign.org_id_id):
                        user_id = session_user_id
                        print(f"  Campaign {campaign.name[:30]} -> User from session: {user.email}")
                        break
                except User.DoesNotExist:
                    pass
        
        # Strategy 2: Assign to first active user in the organization (fallback)
        if not user_id:
            try:
                user = User.objects.filter(
                    account_id=campaign.org_id_id,
                    is_active=True
                ).first()
                
                if user:
                    user_id = user.id
                    print(f"  Campaign {campaign.name[:30]} -> First org user: {user.email}")
            except Exception as e:
                print(f"  Campaign {campaign.name[:30]} -> Could not assign user: {e}")
        
        # Update campaign if we found a user
        if user_id:
            campaign.created_by = user_id
            campaign.save(update_fields=['created_by'])
            updated_count += 1
    
    print(f"\nUpdated {updated_count} campaigns with created_by field")


def reverse_populate(apps, schema_editor):
    """Reverse migration - set created_by back to NULL."""
    # We don't reverse this migration as it would lose data
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0007_campaignleadstatus_campaign_active_status'),
        ('authentication', '0001_initial'),  # Ensure User model exists
    ]

    operations = [
        migrations.RunPython(populate_created_by, reverse_populate),
    ]
