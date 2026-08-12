from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
import logging
from api.models import Lead, BusinessProfile
from api.services.scoring_service import LeadScoringService

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = "Runs the Lead Scoring Engine (Regression Model) for stale leads."



    def add_arguments(self, parser):
        parser.add_argument(
            '--limit',
            type=int,
            default=None,
            help='Optional: Stop after scoring N leads. Default: Process ALL stale leads.'
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force rescore all leads, ignoring the 6-hour stale check.'
        )

    def handle(self, *args, **options):
        self.stdout.write("Starting Lead Scoring Job...")
        logger.info("Starting Lead Scoring Job...")

        # 1. Identify Stale Leads
        job_start_time = timezone.now()
        
        force = options['force']
        
        # Base Query for Stale Leads
        def get_stale_leads():
            if force:
               return Lead.objects.all()
            
            # Default: Anything scored BEFORE this job started is considered 'stale' for this run.
            return Lead.objects.filter(
                score_last_computed_at__lt=job_start_time
            ) | Lead.objects.filter(score_last_computed_at__isnull=True)

        total_stale = get_stale_leads().count()
        self.stdout.write(f"Found {total_stale} stale leads to score.")
        
        if total_stale == 0:
            return

        limit = options['limit']
        if limit:
            self.stdout.write(f"Limit set: will stop after {limit} leads.")

        processed_count = 0
        success_count = 0
        error_count = 0
        
        BATCH_SIZE = 100 

        def process_single_lead(lead):
            nonlocal success_count, error_count
            try:
                # Fix: Resolve org_id via SearchRun
                profile = None
                org_id = None
                s_link = lead.search_run_leads.first()
                if s_link and s_link.search_run:
                    org_id = s_link.search_run.org_id
                
                if org_id:
                    profile = BusinessProfile.objects.filter(account_id=org_id).first()
                
                # Run Scoring
                result = LeadScoringService.score_lead(lead, profile)
                
                if "error" in result:
                    error_count += 1
                else:
                    success_count += 1
                    
            except Exception as e:
                logger.error(f"Critical error processing lead {lead.id}: {e}")
                error_count += 1

        # LOGIC SPLIT:
        # Force Mode -> Iterate linearly (leads don't disappear from query)
        # Stale Mode -> Consume queue (leads disappear from query as they are updated)
        
        if force:
            self.stdout.write("Strategy: Linear Iteration (Force Mode)")
            # Use iterator for memory efficiency on large tables
            qs = get_stale_leads().order_by('id') # consistent ordering
            for lead in qs.iterator(chunk_size=BATCH_SIZE):
                if limit and processed_count >= limit:
                    break
                
                process_single_lead(lead)
                processed_count += 1
                
                if processed_count % BATCH_SIZE == 0:
                     self.stdout.write(f"Processed {processed_count}/{total_stale}...")

        else:
            self.stdout.write("Strategy: Queue Consumption (Stale Mode)")
            while True:
                if limit and processed_count >= limit:
                    break
                    
                # Fetch next batch (processed leads drop out of query automatically)
                batch = list(get_stale_leads()[:BATCH_SIZE])
                
                if not batch:
                    break # No more work
                
                for lead in batch:
                    if limit and processed_count >= limit:
                        break
                        
                    process_single_lead(lead)
                    processed_count += 1
                        
                self.stdout.write(f"Processed {processed_count}/{total_stale}...")

        self.stdout.write(f"Job Complete. Scored: {success_count}, Errors: {error_count}")
        logger.info(f"Scoring Job Complete. Scored: {success_count}, Errors: {error_count}")
