from django.db import models


class LeadHistory(models.Model):
    """
    Daily snapshot of Lead data.
    Designed to mimic a Fact table in a Data Warehouse.
    """
    snapshot_date = models.DateField(auto_now_add=True)
    
    # Dimension: Original Lead Reference
    original_lead_id = models.IntegerField(db_index=True) # References Lead.id (Internal ID)
    third_party_org_id = models.CharField(max_length=36, null=True, blank=True)
    
    # Core Info
    first_name = models.CharField(max_length=100, blank=True, null=True)
    last_name = models.CharField(max_length=100, blank=True, null=True)
    person_full_name = models.CharField(max_length=300, null=True, blank=True)
    
    email = models.EmailField(null=True, blank=True)
    phone = models.CharField(max_length=50, blank=True, null=True)
    linkedin_url = models.URLField(blank=True, null=True)
    other_social_urls = models.JSONField(default=dict, blank=True, null=True)
    
    title = models.CharField(max_length=255, blank=True, null=True)
    person_seniority = models.CharField(max_length=80, null=True, blank=True)
    person_department = models.CharField(max_length=150, null=True, blank=True)
    
    # Company Info
    company_name = models.CharField(max_length=255, blank=True, null=True)
    company_domain = models.CharField(max_length=255, null=True, blank=True)
    industry = models.CharField(max_length=100, blank=True, null=True)
    location = models.CharField(max_length=255, blank=True, null=True)

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
    last_search_run_id = models.CharField(max_length=36, null=True, blank=True)

    # Metadata & Flags
    channel = models.CharField(max_length=40, null=True, blank=True)
    
    # Verification (E6)
    verification_status = models.CharField(max_length=20, null=True, blank=True)
    deliverability_score = models.IntegerField(null=True, blank=True)
    verification_reason = models.CharField(max_length=100, null=True, blank=True)
    verification_last_checked_at = models.DateTimeField(null=True, blank=True)

    # Scoring (M2/E7)
    score = models.IntegerField(null=True)
    score_last_computed_at = models.DateTimeField(null=True, blank=True)
    score_components = models.JSONField(default=dict, blank=True)
    
    # Legacy Scoring
    quality_score = models.IntegerField(null=True, blank=True)
    icp_fit_score = models.IntegerField(null=True, blank=True)
    score_breakdown = models.JSONField(default=dict, blank=True)

    # Enrichment Status
    is_revealed = models.BooleanField(default=False)
    
    # Import (E8)
    import_status = models.CharField(max_length=20, null=True, blank=True)
    import_destination = models.CharField(max_length=80, null=True, blank=True)
    imported_contact_id = models.CharField(max_length=255, null=True, blank=True)
    imported_at = models.DateTimeField(null=True, blank=True)
    import_last_error = models.CharField(max_length=500, null=True, blank=True)

    # Dedupe (E11)
    dedupe_state = models.CharField(max_length=20, null=True, blank=True)
    dedupe_group_id = models.CharField(max_length=36, null=True, blank=True)
    primary_lead_id = models.CharField(max_length=36, null=True, blank=True)
    dedupe_score = models.IntegerField(null=True, blank=True)

    # Ownership & LCM
    owner_user_id = models.CharField(max_length=36, null=True, blank=True)
    tags_json = models.JSONField(default=list, blank=True, null=True)
    
    is_archived = models.BooleanField(default=False)
    archived_at = models.DateTimeField(null=True, blank=True)
    deleted_at = models.DateTimeField(null=True, blank=True)
    
    # Foreign Keys (stored as ID for history/fact table)
    lead_list_id = models.IntegerField(null=True, blank=True) # Store ID only

    class Meta:
        db_table = "dw_lead_history"
        indexes = [
            models.Index(fields=['snapshot_date', 'original_lead_id']),
        ]

    def __str__(self):
        return f"{self.snapshot_date} - {self.email or self.original_lead_id}"


class SearchHistory(models.Model):
    """
    Archive of search activities and aggregate stats.
    """
    snapshot_date = models.DateField(auto_now_add=True)
    
    # Link to original operational data (optional)
    original_search_id = models.IntegerField(null=True)
    
    # Attributes
    search_params = models.JSONField(default=dict)
    results = models.JSONField(default=dict, blank=True) # Full raw results
    
    # Metadata
    triggered_by_session = models.CharField(max_length=255, null=True, blank=True)

    class Meta:
        db_table = "dw_search_history"

    def __str__(self):
        return f"{self.snapshot_date} - Search {self.original_search_id}"
