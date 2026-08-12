from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="AgentConversationSession",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("session_id", models.CharField(max_length=255, unique=True)),
                ("tenant_id", models.CharField(max_length=255)),
                ("metadata", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={"db_table": "agent_conversation_sessions"},
        ),
        migrations.CreateModel(
            name="AgentConversationEvent",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("turn_id", models.CharField(max_length=64)),
                ("seq_no", models.BigIntegerField(default=0)),
                ("event_type", models.CharField(max_length=80)),
                ("actor", models.CharField(max_length=30)),
                ("payload_json", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "session",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="events",
                        to="agent_runtime.agentconversationsession",
                    ),
                ),
            ],
            options={"db_table": "agent_conversation_events"},
        ),
        migrations.CreateModel(
            name="AgentConversationState",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("state_json", models.JSONField(blank=True, default=dict)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "session",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="state_row",
                        to="agent_runtime.agentconversationsession",
                    ),
                ),
            ],
            options={"db_table": "agent_conversation_states"},
        ),
        migrations.CreateModel(
            name="AgentSourceExecutionAudit",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("provider", models.CharField(max_length=80)),
                ("request_payload", models.JSONField(blank=True, default=dict)),
                ("response_count", models.IntegerField(default=0)),
                ("status", models.CharField(default="completed", max_length=20)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "session",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="source_audits",
                        to="agent_runtime.agentconversationsession",
                    ),
                ),
            ],
            options={"db_table": "agent_source_execution_audits"},
        ),
        migrations.AddIndex(
            model_name="agentconversationevent",
            index=models.Index(fields=["turn_id", "seq_no"], name="agent_runtime_turn_seq_idx"),
        ),
        migrations.AddIndex(
            model_name="agentconversationevent",
            index=models.Index(fields=["event_type"], name="agent_runtime_event_type_idx"),
        ),
    ]
