# api/models.py
from django.db import models
import uuid
from .models_warehouse import LeadHistory, SearchHistory

class ConversationSession(models.Model):
    tenant_id = models.CharField(max_length=255, null=False)
    session_id = models.CharField(max_length=255, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    state = models.JSONField(default=dict)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "conversation_session"

    def __str__(self):
        return f"{self.session_id} ({self.tenant_id})"


class ConversationMessage(models.Model):
    session = models.ForeignKey(
        ConversationSession,
        related_name="messages",
        on_delete=models.CASCADE
    )
    role = models.CharField(max_length=20)  # “user” or “assistant”
    text = models.TextField()
    metadata = models.JSONField(default=dict, blank=True) # Snapshots (e.g., search params)
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "conversation_message"

    def __str__(self):
        return f"{self.role}: {self.text[:50]}"


class BusinessProfile(models.Model):
    # Mapping to char(32) UUIDs
    id = models.CharField(primary_key=True, max_length=32)
    account_id = models.CharField(max_length=32, unique=True, null=False)
    
    # Text Fields
    name = models.TextField(blank=True, null=True)
    industry = models.TextField(blank=True, null=True)
    sub_industry = models.TextField(blank=True, null=True)
    description = models.TextField(blank=True, null=True)
    
    # Brand & Business Context
    brand_voice = models.TextField(blank=True, null=True)
    business_model = models.TextField(blank=True, null=True)
    hq_country = models.TextField(blank=True, null=True)
    website = models.TextField(blank=True, null=True)
    timezone = models.TextField(blank=True, null=True)
    # logo_url = models.TextField(blank=True, null=True)
    
    # Metrics
    employee_count = models.TextField(blank=True, null=True)
    revenue_range = models.TextField(blank=True, null=True)
    
    # JSON Fields
    operating_regions = models.JSONField(default=list, blank=True, null=True)
    tone_preferences = models.JSONField(default=dict, blank=True, null=True)
    services = models.JSONField(default=list, blank=True, null=True)
    
    # Contact Info
    phone = models.CharField(max_length=20, blank=True, null=True)
    address = models.TextField(blank=True, null=True)
    hqcity = models.CharField(max_length=100, blank=True, null=True)
    hqstate = models.CharField(max_length=100, blank=True, null=True)
    hqcountry = models.CharField(max_length=10, blank=True, null=True)
    # postal_code = models.CharField(max_length=20, blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "business_profiles"
        managed = False 

    def __str__(self):
        return f"Profile {self.name} ({self.account_id})"


# LEAD MANAGEMENT MODELS

class Company(models.Model):
    id = models.CharField(primary_key=True, max_length=36, default=uuid.uuid4)
    third_party_org_id = models.CharField(max_length=36, null=True, blank=True)
    name = models.CharField(max_length=300, null=True, blank=True)
    domain = models.CharField(max_length=255, null=True, blank=True)
    industry = models.CharField(max_length=150, null=True, blank=True)
    
    # Ranges
    employees_min = models.IntegerField(null=True, blank=True)
    employees_max = models.IntegerField(null=True, blank=True)
    revenue_min_usd = models.BigIntegerField(null=True, blank=True)
    revenue_max_usd = models.BigIntegerField(null=True, blank=True)
    
    # Location
    hq_city = models.CharField(max_length=150, null=True, blank=True)
    hq_region = models.CharField(max_length=150, null=True, blank=True)
    hq_country = models.CharField(max_length=255, null=True, blank=True)
    
    website = models.URLField(max_length=500, null=True, blank=True)
    linkedin_url = models.URLField(max_length=500, null=True, blank=True)
    technologies = models.JSONField(default=list, blank=True, null=True)
    source_meta = models.JSONField(default=dict, blank=True, null=True)
    
    first_seen_at = models.DateTimeField(null=True, blank=True)
    last_seen_at = models.DateTimeField(null=True, blank=True)
    
    is_archived = models.BooleanField(default=False)
    archived_at = models.DateTimeField(null=True, blank=True)
    deleted_at = models.DateTimeField(null=True, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "companies"

    def __str__(self):
        return self.name or self.domain or str(self.id)


class SearchRun(models.Model):
    search_id = models.CharField(primary_key=True, max_length=36, default=uuid.uuid4)
    org_id = models.CharField(max_length=36, null=True, blank=True)
    user_id = models.CharField(max_length=36, null=True, blank=True)
    saved_search_id = models.CharField(max_length=36, null=True, blank=True) # Link to SavedSearch source
    icp_params = models.JSONField(default=dict, blank=True)
    query_text = models.TextField(null=True, blank=True)
    filters_json = models.JSONField(default=dict, blank=True)
    source_used = models.JSONField(default=list, blank=True)
    lead_count = models.IntegerField(default=0)
    status = models.CharField(max_length=20, default='completed') # queued, processing, completed, failed
    created_at = models.DateTimeField(auto_now_add=True)
    leads = models.ManyToManyField("Lead", through="SearchRunLead", related_name="search_runs", blank=True)

    class Meta:
        db_table = "search_runs"

    def __str__(self):
        return f"Run {self.search_id} ({self.lead_count} leads)"


class SavedSearch(models.Model):
    saved_id = models.CharField(primary_key=True, max_length=36, default=uuid.uuid4)
    org_id = models.CharField(max_length=36, null=True, blank=True)
    user_id = models.CharField(max_length=36, null=True, blank=True)
    name = models.CharField(max_length=255)
    description = models.TextField(null=True, blank=True)
    filters_json = models.JSONField(default=dict, blank=True)
    last_run = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "saved_searches"

    def __str__(self):
        return self.name


class LeadList(models.Model):
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "lead_lists"

    def __str__(self):
        return self.name

LeadListNew = LeadList

class Lead(models.Model):
    # Core Info
    third_party_org_id = models.CharField(max_length=36, null=True, blank=True, db_index=True) #  ID of the lead from the source (e.g., LinkedIn ID, Apollo ID, etc.)
    first_name = models.CharField(max_length=100, blank=True, null=True)
    last_name = models.CharField(max_length=100, blank=True, null=True)
    person_full_name = models.CharField(max_length=300, null=True, blank=True)
    
    email = models.EmailField(unique=True, null=True) # Unique identifier for deduplication
    phone = models.CharField(max_length=50, blank=True, null=True)
    linkedin_url = models.URLField(blank=True, null=True)
    other_social_urls = models.JSONField(default=dict, blank=True, null=True)
    
    title = models.CharField(max_length=255, blank=True, null=True, db_index=True)
    person_seniority = models.CharField(max_length=80, null=True, blank=True)
    person_department = models.CharField(max_length=150, null=True, blank=True)
    
    # Company Info
    company = models.ForeignKey(Company, on_delete=models.SET_NULL, null=True, blank=True, related_name="leads")
    company_name = models.CharField(max_length=255, blank=True, null=True, db_index=True)
    company_domain = models.CharField(max_length=255, null=True, blank=True)
    industry = models.CharField(max_length=100, blank=True, null=True, db_index=True)
    location = models.CharField(max_length=255, blank=True, null=True, db_index=True)

    # Denormalized Company Data (Snapshot)
    company_employees_min = models.IntegerField(null=True, blank=True)
    company_employees_max = models.IntegerField(null=True, blank=True)
    company_revenue_min_usd = models.BigIntegerField(null=True, blank=True)
    company_revenue_max_usd = models.BigIntegerField(null=True, blank=True)
    company_hq_city = models.CharField(max_length=150, null=True, blank=True)
    company_hq_region = models.CharField(max_length=150, null=True, blank=True)
    company_hq_country = models.CharField(max_length=255, null=True, blank=True)

    # Discovery Context
    primary_source = models.CharField(max_length=80, null=True, blank=True)
    source_meta = models.JSONField(default=dict, blank=True, null=True)
    first_seen_at = models.DateTimeField(null=True, blank=True)
    last_seen_at = models.DateTimeField(null=True, blank=True)
    last_search_run_id = models.CharField(max_length=36, null=True, blank=True, db_index=True)
    
    # Metadata
    channel = models.CharField(max_length=40, null=True, blank=True)
    
    # Verification (E6)
    verification_status = models.CharField(max_length=20, null=True, blank=True) # valid, invalid, risky, unknown
    deliverability_score = models.IntegerField(null=True, blank=True) # 0-100
    verification_reason = models.CharField(max_length=100, null=True, blank=True)
    verification_last_checked_at = models.DateTimeField(null=True, blank=True)

    # Scoring (M2/E7)
    score = models.IntegerField(null=True, db_index=True) # Composite Score (0-100)
    score_last_computed_at = models.DateTimeField(null=True, blank=True)
    score_components = models.JSONField(default=dict, blank=True) # Breakdown (fit, quality, etc)
    
    # Legacy Scoring (Keep for now)
    quality_score = models.IntegerField(null=True) # Lead Quality Score (0-100)
    icp_fit_score = models.IntegerField(null=True) # ICP Fit Score (0-100)
    score_breakdown = models.JSONField(default=dict, blank=True) # Detailed breakdown of score components

    # Enrichment Status Flags
    is_revealed = models.BooleanField(default=False)
    
    # Import (E8)
    import_status = models.CharField(max_length=20, null=True, blank=True) # not_imported, imported
    import_destination = models.CharField(max_length=80, null=True, blank=True)
    imported_contact_id = models.CharField(max_length=255, null=True, blank=True)
    imported_at = models.DateTimeField(null=True, blank=True)
    import_last_error = models.CharField(max_length=500, null=True, blank=True)

    # Dedupe (E11)
    dedupe_state = models.CharField(max_length=20, null=True, blank=True) # original, primary, duplicate
    dedupe_group_id = models.CharField(max_length=36, null=True, blank=True)
    primary_lead_id = models.CharField(max_length=36, null=True, blank=True)
    dedupe_score = models.IntegerField(null=True, blank=True)

    # Ownership & LCM
    owner_user_id = models.CharField(max_length=36, null=True, blank=True)
    tags_json = models.JSONField(default=list, blank=True, null=True) # Simple array of strings
    
    is_archived = models.BooleanField(default=False)
    archived_at = models.DateTimeField(null=True, blank=True)
    deleted_at = models.DateTimeField(null=True, blank=True)
    
    # Relationships
    lead_list = models.ForeignKey(LeadList, on_delete=models.SET_NULL, null=True, related_name="leads")
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "leads"

    def __str__(self):
        return f"{self.first_name} {self.last_name} ({self.email})"



class LeadNote(models.Model):
    lead = models.ForeignKey(Lead, on_delete=models.CASCADE, related_name="notes")
    body = models.TextField()
    org_id = models.CharField(max_length=36, null=True, blank=True)
    is_deleted = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    author_user_id = models.CharField(max_length=36, null=True, blank=True)

    class Meta:
        db_table = "lead_notes"

class LeadTag(models.Model):
    lead = models.ForeignKey(Lead, on_delete=models.CASCADE, related_name="tags")
    name = models.CharField(max_length=50)

    class Meta:
        db_table = "lead_tags"

class LeadEvent(models.Model):
    lead = models.ForeignKey(Lead, on_delete=models.CASCADE, related_name="events")
    org_id = models.CharField(max_length=36, null=True, blank=True)
    event_type = models.CharField(max_length=100) 
    metadata = models.JSONField(default=dict)
    actor_user_id = models.CharField(max_length=36, null=True, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "lead_events"


class SearchRunLead(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    search_run = models.ForeignKey(
        "SearchRun",
        on_delete=models.CASCADE,
        related_name="search_leads"
    )
    lead = models.ForeignKey(
        "Lead",
        on_delete=models.CASCADE,
        related_name="search_run_leads"
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "search_run_leads"
        unique_together = ("search_run", "lead")


class BulkJob(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    org_id = models.CharField(max_length=36)
    user_id = models.CharField(max_length=36)

    job_type = models.CharField(
        max_length=30,
        choices=[
            ("verify", "Verify"),
            ("score", "Score"),
            ("import", "Import"),
            ("dedupe", "Dedupe"),
        ]
    )

    status = models.CharField(
        max_length=20,
        choices=[
            ("queued", "Queued"),
            ("running", "Running"),
            ("completed", "Completed"),
            ("failed", "Failed"),
        ],
        default="queued"
    )

    total_items = models.IntegerField(default=0)
    completed_items = models.IntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "bulk_jobs"



class VerificationJob(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    lead = models.ForeignKey(
        "Lead",
        on_delete=models.CASCADE,
        related_name="verification_jobs"
    )

    provider = models.CharField(max_length=100)

    status = models.CharField(
        max_length=20,
        choices=[
            ("pending", "Pending"),
            ("completed", "Completed"),
            ("failed", "Failed"),
        ]
    )

    result = models.CharField(
        max_length=20,
        choices=[
            ("valid", "Valid"),
            ("risky", "Risky"),
            ("invalid", "Invalid"),
        ],
        null=True,
        blank=True
    )

    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "verification_jobs"


class LeadDuplicate(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    original_lead = models.ForeignKey(
        "Lead",
        on_delete=models.CASCADE,
        related_name="duplicate_children"
    )
    duplicate_lead = models.ForeignKey(
        "Lead",
        on_delete=models.CASCADE,
        related_name="duplicate_parent"
    )

    confidence_score = models.FloatField()

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "lead_duplicates"
        unique_together = ("original_lead", "duplicate_lead")



class PeopleSearch(models.Model):
    session = models.ForeignKey(ConversationSession, null=True, on_delete=models.SET_NULL)
    params = models.JSONField(default=dict)
    results = models.JSONField(default=dict, blank=True)
    leads = models.ManyToManyField(Lead, related_name='searches', blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "people_searches"
    
    def __str__(self):
        return f"Search {self.id} ({len(self.leads.all())} leads)"



class Account(models.Model):
    id = models.CharField(primary_key=True, max_length=255)
    name = models.CharField(max_length=255, null=True, blank=True)
    class Meta:
        db_table = "accounts"
        managed = False

class Campaign(models.Model):

    STATUS_CHOICES = [
        ("draft", "Draft"),
        ("ai_clarifying", "AI Clarifying"),
        ("ai_ready", "AI Ready"),
        ("ai_generated", "AI Generated"),
        ("user_editing", "User Editing"),
        ("spam_pending", "Spam Pending"),
        ("spam_failed", "Spam Failed"),
        ("approved", "Approved"),
        ("active", "Active"),          # Sequence is running (auto follow-ups enabled)
        ("paused", "Paused"),          # Sequence paused by user
        ("completed", "Completed"),    # All steps sent to all leads
        ("blocked", "Blocked"),
    ]

    CREATION_MODE_CHOICES = [
        ("manual", "Manual"),
        ("ai", "AI"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    org_id = models.ForeignKey(
        Account,
        on_delete=models.CASCADE,
        db_column="org_id"
    )

    # lead_list_id = models.ForeignKey(
    #     LeadListNew,
    #     on_delete=models.CASCADE,
    #     db_column="lead_list_id"
    # )
    lead_list_id = models.CharField(max_length=255,blank=True,null=True)
    name = models.CharField(max_length=255)

    creation_mode = models.CharField(
        max_length=10,
        choices=CREATION_MODE_CHOICES
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="draft"
    )

    created_by = models.UUIDField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "campaigns"

    def __str__(self):
        return self.name


class CampaignContext(models.Model):

    STATUS_CHOICES = [
        ("incomplete", "Incomplete"),
        ("complete", "Complete"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    campaign = models.OneToOneField(
        Campaign,
        on_delete=models.CASCADE,
        db_column="campaign_id",
        related_name="context"
    )

    context_json = models.JSONField(default=dict)

    completeness_score = models.FloatField(null=True, blank=True)

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="incomplete"
    )

    last_updated = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "campaign_contexts"


class CampaignStep(models.Model):

    CONDITION_CHOICES = [
        ("always", "Always"),
        ("replied", "Replied"),
        ("not_replied", "Not Replied"),
        ("opened", "Opened"),
        ("not_opened", "Not Opened"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    campaign = models.ForeignKey(
        Campaign,
        on_delete=models.CASCADE,
        related_name="steps",
        db_column="campaign_id"
    )

    step_order = models.IntegerField()

    delay_days = models.IntegerField()

    condition = models.CharField(
        max_length=20,
        choices=CONDITION_CHOICES,
        default="always"
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "campaign_steps"
        ordering = ["step_order"]



class CampaignEmail(models.Model):

    ORIGIN_CHOICES = [
        ("manual", "Manual"),
        ("ai", "AI"),
    ]

    SPAM_STATUS_CHOICES = [
        ("pending", "Pending"),
        ("passed", "Passed"),
        ("failed", "Failed"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    step = models.OneToOneField(
        CampaignStep,
        on_delete=models.CASCADE,
        related_name="email",
        db_column="step_id"
    )

    subject = models.TextField(null=True, blank=True)
    body = models.TextField(null=True, blank=True)

    variables = models.JSONField(default=dict)

    origin = models.CharField(
        max_length=10,
        choices=ORIGIN_CHOICES,
        default="manual"
    )

    spam_status = models.CharField(
        max_length=10,
        choices=SPAM_STATUS_CHOICES,
        default="pending"
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "campaign_emails"


class SpamValidationResult(models.Model):

    RESULT_CHOICES = [
        ("pass", "Pass"),
        ("fail", "Fail"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    email = models.ForeignKey(
        CampaignEmail,
        on_delete=models.CASCADE,
        related_name="spam_results",
        db_column="email_id"
    )

    provider = models.CharField(max_length=100)

    spam_score = models.FloatField()
    threshold = models.FloatField()

    result = models.CharField(
        max_length=10,
        choices=RESULT_CHOICES
    )

    raw_response = models.JSONField(default=dict)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "spam_validation_results"


class AISession(models.Model):

    STATUS_CHOICES = [
        ("clarifying", "Clarifying"),
        ("ready", "Ready"),
        ("generating", "Generating"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    campaign = models.ForeignKey(
        Campaign,
        on_delete=models.CASCADE,
        related_name="ai_sessions",
        db_column="campaign_id"
    )

    conversation_history = models.JSONField(default=list)

    current_status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES
    )

    model_version = models.CharField(max_length=50, null=True, blank=True)

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "ai_sessions"


class MLConversation(models.Model):
    STAGE_CHOICES = [
        ('clarifying', 'Clarifying'),
        ('ready', 'Ready'),
        ('generated', 'Generated'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    # Assuming 'Campaign' model exists in the same app or you use 'app_label.Campaign'
    campaign = models.ForeignKey(
        'Campaign', 
        on_delete=models.CASCADE, 
        db_column="campaign_id"
    )
    
    messages = models.JSONField(default=list)
    
    current_stage = models.CharField(
        max_length=20, 
        choices=STAGE_CHOICES, 
        default='clarifying'
    )
    
    model_version = models.CharField(max_length=50, null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "ml_conversations"


class MLCampaignContext(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    campaign = models.ForeignKey(
        'Campaign', 
        on_delete=models.CASCADE, 
        db_column="campaign_id"
    )
    
    extracted_fields = models.JSONField(default=dict)
    missing_fields = models.JSONField(default=dict)
    confidence_map = models.JSONField(default=dict)
    completeness_score = models.FloatField(default=0.0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "ml_campaign_context"


class MLGeneration(models.Model):
    TYPE_CHOICES = [
        ('campaign', 'Campaign'),
        ('email', 'Email'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    campaign = models.ForeignKey(
        'Campaign', 
        on_delete=models.CASCADE, 
        db_column="campaign_id"
    )
    
    # Nullable because it might be a campaign-level generation, not attached to a step
    step = models.ForeignKey(
        'CampaignStep', 
        on_delete=models.CASCADE, 
        null=True, 
        blank=True, 
        db_column="step_id"
    )
    
    type = models.CharField(max_length=20, choices=TYPE_CHOICES)
    prompt = models.JSONField(default=dict)
    output = models.JSONField(default=dict)
    model_version = models.CharField(max_length=50, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "ml_generations"


class MLSpamAnalysis(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # References the CampaignEmail model from your previous query
    email = models.ForeignKey(
        'CampaignEmail',
        on_delete=models.CASCADE,
        db_column="email_id"
    )

    provider = models.CharField(max_length=100)
    raw_response = models.JSONField(default=dict)
    normalized_score = models.FloatField()
    risk_factors = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "ml_spam_analysis"


class AIPromptTemplate(models.Model):

    CATEGORY_CHOICES = [
        ("email", "Email"),
        ("campaign", "Campaign"),
        ("lead_search", "Lead Search"),
        ("chit_chat", "Chit Chat"),
        ("spam_analysis", "Spam Analysis"),
        ("custom", "Custom"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    org_id = models.CharField(max_length=36, null=True, blank=True, db_index=True)
    created_by = models.UUIDField(null=True, blank=True)

    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    category = models.CharField(max_length=30, choices=CATEGORY_CHOICES, default="custom")

    template_text = models.TextField()
    variables = models.JSONField(default=list, blank=True)  # list of variable names used in the template

    is_active = models.BooleanField(default=True)
    is_default = models.BooleanField(default=False)  # system-level default templates

    # AI model parameters
    model_name = models.CharField(max_length=100, default="gpt-4o-mini")
    temperature = models.FloatField(default=0.7)
    max_tokens = models.IntegerField(default=500)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "ai_prompt_templates"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.name} ({self.category})"


class AIPromptTemplateVersion(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    template = models.ForeignKey(
        AIPromptTemplate,
        on_delete=models.CASCADE,
        related_name="versions"
    )

    version_number = models.IntegerField()

    # Snapshot of the template fields at this version
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    category = models.CharField(max_length=30)
    template_text = models.TextField()
    variables = models.JSONField(default=list)
    model_name = models.CharField(max_length=100)
    temperature = models.FloatField()
    max_tokens = models.IntegerField()

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "ai_prompt_template_versions"
        ordering = ["-version_number"]
        unique_together = ("template", "version_number")

    def __str__(self):
        return f"{self.template.name} v{self.version_number}"


# EMAIL TRACKING MODELS

class SentEmail(models.Model):
    """Track all sent campaign emails"""
    
    STATUS_CHOICES = [
        ('sent', 'Sent'),
        ('delivered', 'Delivered'),
        ('opened', 'Opened'),
        ('clicked', 'Clicked'),
        ('replied', 'Replied'),
        ('bounced', 'Bounced'),
        ('failed', 'Failed'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    campaign_id = models.CharField(max_length=36)
    step_order = models.IntegerField()
    
    recipient_email = models.EmailField()
    recipient_name = models.CharField(max_length=255, blank=True, null=True)
    
    subject = models.TextField()
    body = models.TextField()
    
    sent_at = models.DateTimeField(auto_now_add=True)
    sent_from = models.EmailField()
    
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='sent')
    
    # Tracking timestamps
    opened_at = models.DateTimeField(null=True, blank=True)
    clicked_at = models.DateTimeField(null=True, blank=True)
    replied_at = models.DateTimeField(null=True, blank=True)
    bounced_at = models.DateTimeField(null=True, blank=True)
    
    metadata = models.JSONField(default=dict, blank=True)
    
    class Meta:
        db_table = "sent_emails"
        ordering = ['-sent_at']
    
    def __str__(self):
        return f"Email to {self.recipient_email} - {self.status}"


class EmailReply(models.Model):
    """Track replies to sent emails"""
    
    SENTIMENT_CHOICES = [
        ('positive', 'Positive'),
        ('neutral', 'Neutral'),
        ('negative', 'Negative'),
        ('interested', 'Interested'),
        ('not_interested', 'Not Interested'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    sent_email = models.ForeignKey(
        SentEmail,
        on_delete=models.CASCADE,
        related_name='replies'
    )
    
    from_email = models.EmailField()
    from_name = models.CharField(max_length=255, blank=True, null=True)
    
    subject = models.TextField()
    body = models.TextField()
    
    received_at = models.DateTimeField(auto_now_add=True)
    is_read = models.BooleanField(default=False)
    
    sentiment = models.CharField(max_length=20, choices=SENTIMENT_CHOICES, blank=True, null=True)
    
    metadata = models.JSONField(default=dict, blank=True)
    
    class Meta:
        db_table = "email_replies"
        ordering = ['-received_at']
    
    def __str__(self):
        return f"Reply from {self.from_email} - {self.sentiment or 'unanalyzed'}"


class CampaignLeadStatus(models.Model):
    """
    Tracks per-lead progress through a campaign sequence.
    One row per (campaign, lead) pair. Updated as each step is sent.
    """
    
    STATUS_CHOICES = [
        ('pending', 'Pending'),        # Lead enrolled, no email sent yet
        ('in_sequence', 'In Sequence'), # At least one step sent, more to go
        ('completed', 'Completed'),     # All steps sent
        ('replied', 'Replied'),         # Lead replied — stop sending
        ('bounced', 'Bounced'),         # Email bounced — stop sending
        ('unsubscribed', 'Unsubscribed'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    campaign = models.ForeignKey(
        Campaign,
        on_delete=models.CASCADE,
        related_name='lead_statuses',
        db_column='campaign_id'
    )
    
    lead = models.ForeignKey(
        Lead,
        on_delete=models.CASCADE,
        related_name='campaign_statuses'
    )
    
    # Which step was last sent (0 = none sent yet)
    last_step_sent = models.IntegerField(default=0)
    
    # When was the last step email sent
    last_sent_at = models.DateTimeField(null=True, blank=True)
    
    # Current status of this lead in the campaign
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    
    # Link to the SentEmail record for the last sent step
    last_sent_email = models.ForeignKey(
        SentEmail,
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = "campaign_lead_status"
        unique_together = ("campaign", "lead")
        ordering = ['-updated_at']
    
    def __str__(self):
        return f"Campaign {self.campaign_id} | Lead {self.lead_id} | Step {self.last_step_sent} | {self.status}"