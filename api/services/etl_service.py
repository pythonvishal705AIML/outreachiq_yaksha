
import logging
from django.utils import timezone
from ..models import Lead, PeopleSearch
from ..models_warehouse import LeadHistory, SearchHistory

logger = logging.getLogger(__name__)

class ETLService:
    @staticmethod
    def run_daily_load():
        """
        Snapshot operational data into Warehouse tables.
        Should be run once per day (e.g. at midnight).
        """
        today = timezone.now().date()
        logger.info(f"Starting ETL Load for {today}...")

        # Snapshot Leads
        # Optimization: Only process leads modified in the last 24 hours (or since last run)
        # However, to be safe and "self-healing", we can process ALL leads but perform an UPSERT.
        # Given the user's performance concern, let's limit to Active leads if possible, 
        # but for a true "History" we often want full snapshots.
        # 
        # COMPROMISE per User Request: "Transfer only new data" / "Update if exists"
        # Strategy:
        # 1. Fetch ALL Leads (or filter by updated_at if volume > 100k)
        # 2. Check for existing snapshot for today.
        # 3. If exists, Update. If not, Create.
        # 
        # Efficient Implementation (Delete-Insert for Idempotency without Schema Change):
        # To avoid N+1 queries, we will delete today's existing history for the batch and re-insert.
        
        # We must filter by 'updated_at' to reduce the load.
        
        # Look back 24 hours (or slightly more to cover gaps)
        since_time = timezone.now() - timezone.timedelta(days=1)
        
        logger.info(f"Fetching leads updated since {since_time}...")
        
        leads = Lead.objects.filter(updated_at__gte=since_time).iterator(chunk_size=1000)
        
        batch_size = 500
        batch_leads = []
        
        count_processed = 0
        
        for lead in leads:
            batch_leads.append(lead)
            
            if len(batch_leads) >= batch_size:
                ETLService._process_lead_batch(batch_leads, today)
                count_processed += len(batch_leads)
                batch_leads = []
        
        if batch_leads:
             ETLService._process_lead_batch(batch_leads, today)
             count_processed += len(batch_leads)
             
        logger.info(f"Snapshot Complete: {count_processed} leads processed.")


    @staticmethod
    def _process_lead_batch(leads, snapshot_date):
        """
        Helper to safely persist a batch of lead history records.
        Using Delete-Then-Insert to simulate Upsert for today's snapshot.
        """
        lead_ids = [l.id for l in leads]
        
        # 1. Clear existing snapshots for this batch for TODAY (Idempotency)
        LeadHistory.objects.filter(
            snapshot_date=snapshot_date, 
            original_lead_id__in=lead_ids
        ).delete()
        
        # 2. Bulk Create
        history_objects = []
        for lead in leads:
            history = LeadHistory(
                snapshot_date=snapshot_date,
                original_lead_id=lead.id,
                third_party_org_id=lead.third_party_org_id,
                
                # Core Info
                first_name=lead.first_name,
                last_name=lead.last_name,
                person_full_name=lead.person_full_name,
                email=lead.email,
                phone=lead.phone,
                linkedin_url=lead.linkedin_url,
                other_social_urls=lead.other_social_urls,
                title=lead.title,
                person_seniority=lead.person_seniority,
                person_department=lead.person_department,
                
                # Company Info
                company_name=lead.company_name,
                company_domain=lead.company_domain,
                industry=lead.industry,
                location=lead.location,
                
                # Denormalized Company Data
                company_employees_min=lead.company_employees_min,
                company_employees_max=lead.company_employees_max,
                company_revenue_min_usd=lead.company_revenue_min_usd,
                company_revenue_max_usd=lead.company_revenue_max_usd,
                company_hq_city=lead.company_hq_city,
                company_hq_region=lead.company_hq_region,
                company_hq_country=lead.company_hq_country,
                
                # Discovery Context
                primary_source=lead.primary_source,
                source_meta=lead.source_meta,
                first_seen_at=lead.first_seen_at,
                last_seen_at=lead.last_seen_at,
                last_search_run_id=lead.last_search_run_id,
                
                # Metadata & Flags
                channel=lead.channel,
                is_revealed=lead.is_revealed,
                
                # Verification
                verification_status=lead.verification_status,
                deliverability_score=lead.deliverability_score,
                verification_reason=lead.verification_reason,
                verification_last_checked_at=lead.verification_last_checked_at,
                
                # Scoring
                score=lead.score,
                score_last_computed_at=lead.score_last_computed_at,
                score_components=lead.score_components,
                
                # Legacy Scoring
                quality_score=lead.quality_score,
                icp_fit_score=lead.icp_fit_score,
                score_breakdown=lead.score_breakdown,
                
                # Import
                import_status=lead.import_status,
                import_destination=lead.import_destination,
                imported_contact_id=lead.imported_contact_id,
                imported_at=lead.imported_at,
                import_last_error=lead.import_last_error,
                
                # Dedupe
                dedupe_state=lead.dedupe_state,
                dedupe_group_id=lead.dedupe_group_id,
                primary_lead_id=lead.primary_lead_id,
                dedupe_score=lead.dedupe_score,
                
                # Ownership
                owner_user_id=lead.owner_user_id,
                tags_json=lead.tags_json,
                is_archived=lead.is_archived,
                archived_at=lead.archived_at,
                deleted_at=lead.deleted_at,
                
                # FKs
                lead_list_id=lead.lead_list_id if lead.lead_list_id else None
            )
            history_objects.append(history)
            
        if history_objects:
             LeadHistory.objects.bulk_create(history_objects)

        # Snapshot PeopleSearches (Incremental)
        # Only copy searches created TODAY to avoid duplication
        # Usually search history is immutable, so we just copy new ones.
        today = timezone.now().date()
        searches = PeopleSearch.objects.filter(created_at__date=today)
        search_history_objects = []
        
        for s in searches:
             search_hist = SearchHistory(
                 snapshot_date=today,
                 original_search_id=s.id,
                 search_params=s.params,
                 results=s.results,
                 triggered_by_session=s.session.session_id if s.session else None
             )
             search_history_objects.append(search_hist)
        
        if search_history_objects:
            SearchHistory.objects.bulk_create(search_history_objects)
            
        logger.info(f"Snapshot Complete: {len(search_history_objects)} searches archived.")
