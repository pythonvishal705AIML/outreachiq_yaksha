# api/services/ai_insights_service.py
import uuid
import logging
from django.db.models import Avg, Count, Q
from ..models import MLGeneration, MLSpamAnalysis, MLCampaignContext, MLConversation

logger = logging.getLogger(__name__)

class AIInsightsService:
    """
    Service class that handles all DB queries and aggregations
    for the AI Insights page. No HTTP/request logic here.
    """

    @staticmethod
    def get_insights(org_id=None, user_id=None):
        if org_id:
            try:
                uuid.UUID(str(org_id))
            except ValueError:
                raise ValueError(f"Invalid org_id: {org_id}")

        # ── Base querysets ──
        gen_qs = MLGeneration.objects.all()
        spam_qs = MLSpamAnalysis.objects.all()
        ctx_qs = MLCampaignContext.objects.all()
        conv_qs = MLConversation.objects.all()

        # ── Scope to account (org) — prevents global data leak ──
        if org_id:
            gen_qs = gen_qs.filter(campaign__org_id=org_id)
            spam_qs = spam_qs.filter(email__step__campaign__org_id=org_id)
            ctx_qs = ctx_qs.filter(campaign__org_id=org_id)
            conv_qs = conv_qs.filter(campaign__org_id=org_id)
        elif user_id:
            # No account linked yet — fall back to campaigns created by this user
            gen_qs = gen_qs.filter(campaign__created_by=user_id)
            spam_qs = spam_qs.filter(email__step__campaign__created_by=user_id)
            ctx_qs = ctx_qs.filter(campaign__created_by=user_id)
            conv_qs = conv_qs.filter(campaign__created_by=user_id)

        # ── Aggregated metrics ──
        generation_counts = gen_qs.aggregate(
            total_campaigns_generated=Count("id", filter=Q(type="campaign")),
            total_emails_generated=Count("id", filter=Q(type="email")),
        )

        avg_spam = spam_qs.aggregate(average_spam_score=Avg("normalized_score"))
        avg_completeness = ctx_qs.aggregate(average_context_completeness=Avg("completeness_score"))
        total_conversations = conv_qs.count()

        metrics = {
            "total_campaigns_generated": generation_counts["total_campaigns_generated"] or 0,
            "total_emails_generated": generation_counts["total_emails_generated"] or 0,
            "average_spam_score": (
                round(avg_spam["average_spam_score"], 2)
                if avg_spam["average_spam_score"] is not None else None
            ),
            "average_context_completeness": (
                round(avg_completeness["average_context_completeness"], 2)
                if avg_completeness["average_context_completeness"] is not None else None
            ),
            "total_ai_conversations": total_conversations,
        }

        # ── Recent generations (last 10) ──
        recent_gens = gen_qs.select_related("campaign").order_by("-created_at")[:10]
        recent_generations = [
            {
                "id": str(g.id),
                "campaign_id": str(g.campaign_id),
                "campaign_name": g.campaign.name if g.campaign else None,
                "type": g.type,
                "model_version": g.model_version,
                "created_at": g.created_at.isoformat() if g.created_at else None,
            }
            for g in recent_gens
        ]

        # ── Spam risk factors (last 20) ──
        recent_spam = spam_qs.select_related("email").order_by("-created_at")[:20]
        spam_risk_factors = [
            {
                "id": str(s.id),
                "email_id": str(s.email_id),
                "provider": s.provider,
                "normalized_score": s.normalized_score,
                "risk_factors": s.risk_factors,
                "created_at": s.created_at.isoformat() if s.created_at else None,
            }
            for s in recent_spam
        ]

        # ── Conversation stage distribution ──
        stage_distribution = dict(
            conv_qs.values_list("current_stage")
            .annotate(count=Count("id"))
            .values_list("current_stage", "count")
        )

        return {
            "metrics": metrics,
            "recent_generations": recent_generations,
            "spam_risk_factors": spam_risk_factors,
            "conversation_stage_distribution": stage_distribution,
        }
