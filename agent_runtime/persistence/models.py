from django.db import models


class AgentConversationSession(models.Model):
    session_id = models.CharField(max_length=255, unique=True)
    tenant_id = models.CharField(max_length=255)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "agent_conversation_sessions"


class AgentConversationEvent(models.Model):
    session = models.ForeignKey(
        AgentConversationSession,
        related_name="events",
        on_delete=models.CASCADE,
    )
    turn_id = models.CharField(max_length=64)
    seq_no = models.BigIntegerField(default=0)
    event_type = models.CharField(max_length=80)
    actor = models.CharField(max_length=30)
    payload_json = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "agent_conversation_events"
        indexes = [
            models.Index(fields=["turn_id", "seq_no"]),
            models.Index(fields=["event_type"]),
        ]


class AgentConversationState(models.Model):
    session = models.OneToOneField(
        AgentConversationSession,
        related_name="state_row",
        on_delete=models.CASCADE,
    )
    state_json = models.JSONField(default=dict, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "agent_conversation_states"
