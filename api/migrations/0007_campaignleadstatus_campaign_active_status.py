"""
Migration: Add CampaignLeadStatus model and update Campaign status choices
"""

from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0006_sentemail_alter_campaign_lead_list_id_emailreply'),
    ]

    operations = [
        # 1. Update Campaign status choices (add active, paused, completed)
        migrations.AlterField(
            model_name='campaign',
            name='status',
            field=models.CharField(
                choices=[
                    ('draft', 'Draft'),
                    ('ai_clarifying', 'AI Clarifying'),
                    ('ai_ready', 'AI Ready'),
                    ('ai_generated', 'AI Generated'),
                    ('user_editing', 'User Editing'),
                    ('spam_pending', 'Spam Pending'),
                    ('spam_failed', 'Spam Failed'),
                    ('approved', 'Approved'),
                    ('active', 'Active'),
                    ('paused', 'Paused'),
                    ('completed', 'Completed'),
                    ('blocked', 'Blocked'),
                ],
                default='draft',
                max_length=20,
            ),
        ),

        # 2. Create CampaignLeadStatus table
        migrations.CreateModel(
            name='CampaignLeadStatus',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('last_step_sent', models.IntegerField(default=0)),
                ('last_sent_at', models.DateTimeField(blank=True, null=True)),
                ('status', models.CharField(
                    choices=[
                        ('pending', 'Pending'),
                        ('in_sequence', 'In Sequence'),
                        ('completed', 'Completed'),
                        ('replied', 'Replied'),
                        ('bounced', 'Bounced'),
                        ('unsubscribed', 'Unsubscribed'),
                    ],
                    default='pending',
                    max_length=20,
                )),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('campaign', models.ForeignKey(
                    db_column='campaign_id',
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='lead_statuses',
                    to='api.campaign',
                )),
                ('lead', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='campaign_statuses',
                    to='api.lead',
                )),
                ('last_sent_email', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    to='api.sentemail',
                )),
            ],
            options={
                'db_table': 'campaign_lead_status',
                'ordering': ['-updated_at'],
                'unique_together': {('campaign', 'lead')},
            },
        ),
    ]



