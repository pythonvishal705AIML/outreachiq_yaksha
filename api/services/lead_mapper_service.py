import logging
from django.utils import timezone
from django.db import IntegrityError
from ..repositories.lead_repository import LeadRepository
from ..models import Company as CompanyModel

logger = logging.getLogger(__name__)

class LeadMapperService:
    """
    Handles Mapping Raw Data -> Lead Model and Saving/Deduplication.
    Extracted from LeadService to separate Data Ingestion logic from Search Orchestration.
    """

    @staticmethod
    def map_and_save_lead(raw_data, channel="upload", company_obj=None, is_revealed=False, extra_flags=None, icp_params=None):
        """
        Robust helper to Map Raw Data -> Lead Model and Save.
        Handles:
             - Mapping ID -> third_party_org_id
             - Storing raw data -> source_meta
             - Channel assignment
             - Dedup via LeadRepository
        """

        # 1. Normalize Core Fields
        # Note: logic tries to extract common fields regardless of channel if possible,
        # or defaults to the generic structure if specific keys match.
        
        # Extract ID (Generic)
        tid = raw_data.get("id")
        
        # Extract Organization
        org_data = raw_data.get("organization") or {}
        
        # Extract Phone
        phone = None
        if raw_data.get("phone_numbers"):
             phone = raw_data.get("phone_numbers")[0].get("raw_number")
        
        # ---------------------------------------------------------------------
        # AUTO-ENRICH COMPANY (If not provided)
        # ---------------------------------------------------------------------
        if not company_obj and org_data.get("name"):
            try:
                
                # Fields to capture
                c_name = org_data.get("name")
                c_domain = org_data.get("website_url") or org_data.get("primary_domain")
                c_industry = org_data.get("industry")
                c_tid = org_data.get("id") # Third-party company ID

                defaults = {
                    "name": c_name,
                    "industry": c_industry,
                    "third_party_org_id": c_tid,
                    "hq_city": org_data.get("city"),
                    "hq_region": org_data.get("state"),
                    "hq_country": org_data.get("country"),
                    "linkedin_url": org_data.get("linkedin_url"),
                    "employees_min": None,
                    "employees_max": org_data.get("estimated_num_employees"),
                    "source_meta": {"third_party_org_id": c_tid, "raw_data": org_data}
                }
                
                # Check for ID match first (Strongest Link)
                if c_tid:
                    company_obj, _ = CompanyModel.objects.update_or_create(
                        third_party_org_id=c_tid,
                        defaults=defaults
                    )
                # Fallback to Domain (Medium Link)
                elif c_domain:
                     defaults["domain"] = c_domain
                     company_obj, _ = CompanyModel.objects.update_or_create(
                        domain=c_domain,
                        defaults=defaults
                    )
                # Fallback to Name (Weakest Link)
                else:
                    company_obj, _ = CompanyModel.objects.get_or_create(
                        name=c_name,
                        defaults=defaults
                    )
            except Exception as e:
                logger.warning(f"Failed to auto-create company for lead {tid}: {e}")
        
        lead_data = {
            "first_name": raw_data.get("first_name"),
            "last_name": raw_data.get("last_name") or raw_data.get("last_name_obfuscated"),
            "email": raw_data.get("email"),
            "phone": phone,
            "linkedin_url": raw_data.get("linkedin_url"),
            "title": raw_data.get("title"),
            "person_seniority": raw_data.get("seniority"),
            "person_department": raw_data.get("departments", [None])[0] if raw_data.get("departments") else None,
            
            "company": company_obj,
            "company_name": org_data.get("name"),
            "company_domain": org_data.get("website_url"),
            "industry": org_data.get("industry"),
            "location": raw_data.get("city") or raw_data.get("state") or raw_data.get("country"),
            
            "channel": channel,
            "primary_source": channel, # Default primary source to channel
            "third_party_org_id": tid,
            
            # GENERIC SOURCE DATA
            "source_meta": raw_data,
            
            "last_seen_at": timezone.now(),
            "verification_status": "valid" if raw_data.get("email_status") == "verified" else "unknown"
        }
        
        if is_revealed:
            lead_data["is_revealed"] = True

        # Merge extra flags
        if extra_flags:
            lead_data.update(extra_flags)

        # 2. Save / Update
        # Try finding existing first
        existing = LeadRepository.get_lead_by_third_party_id(tid)
        
        if existing:
            # Update fields
            # CHECK-BEFORE-UPDATE: Prevent collision if email belongs to another lead
            new_email = lead_data.get("email")
            
            # Check if we are changing the email (or setting it for the first time)
            # Logic: If new_email is set, and it's different from current (case-insensitive)
            should_check_conflict = False
            if new_email:
                if not existing.email:
                     should_check_conflict = True
                elif new_email.lower() != existing.email.lower():
                     should_check_conflict = True
            
            if should_check_conflict:
                # Email is changing. Check valid ownership.
                conflict = LeadRepository.get_lead_by_email(new_email)
                if conflict and conflict.id != existing.id:
                    logger.warning(f"Update Collision: Lead {existing.id} tried to claim email '{new_email}' owned by {conflict.id}.")
                    logger.info(f"SWITCHING TARGET: Using existing lead {conflict.id} (Winner) instead of {existing.id}.")
                    
                    # SWITCH strategy: abandon the 'existing' stub, use the 'conflict' lead.
                    existing = conflict
                    
                    # Ensure we don't accidentally overwrite the Winner's ID unless necessary
                    # If Winner has no third-party ID, give it the one we have.
                    if not existing.third_party_org_id and tid:
                         existing.third_party_org_id = tid
                    
                    # Remove ID from update payload to prevent overwrite if keys exist
                    lead_data.pop("third_party_org_id", None)
                    lead_data.pop("id", None) # Generic ID key handling
                    
            for k, v in lead_data.items():
                if v is not None: 
                     setattr(existing, k, v)
            
            try:
                existing.save()
            except IntegrityError:
                # Double Safety Net
                logger.error(f"IntegrityError failed during update for {existing.id}. Trying refresh.")
                raise # Should be rare now
            
                raise # Should be rare now
            
            _trigger_post_processing(existing, is_new=False, icp_params=icp_params)
            return existing, False
        else:
            # CHECK EMAIL EXISTENCE (IntegrityError Fix)
            # If we didn't find by ID, we might still have this person by Email
            email = lead_data.get("email")
            if email:
                logger.info(f"Checking existence by email: {email}")
                existing_by_email = LeadRepository.get_lead_by_email(email)
                logger.info(f"Email check result: {existing_by_email}")
                if existing_by_email:
                    # Update the existing email record with the new ID and details
                    for k, v in lead_data.items():
                        if v is not None:
                            setattr(existing_by_email, k, v)
                    existing_by_email.save()
                    _trigger_post_processing(existing_by_email, is_new=False, icp_params=icp_params)
                    return existing_by_email, False

            # Create New
            try:
                lead = LeadRepository.create_lead(lead_data)
                _trigger_post_processing(lead, is_new=True, icp_params=icp_params)
                return lead, True
            except IntegrityError:
                logger.warning(f"IntegrityError encountered for {email}. Lead likely exists.")
                # Fallback: Try to fetch again (race condition handler)
                existing = LeadRepository.get_lead_by_email(email)
                if existing:
                    # Update found lead
                    for k, v in lead_data.items():
                        if v is not None:
                            setattr(existing, k, v)
                    existing.save()
                    _trigger_post_processing(existing, is_new=False, icp_params=icp_params)
                    return existing, False
                raise

def _trigger_post_processing(lead, is_new=False, icp_params=None):
    """
    Synchronous triggers for Verify/Score to match flowchart.
    In prod, these should be .delay() celery tasks.
    """
    try:
        from .verification_service import VerificationService
        from .scoring_service import LeadScoringService
        
        # A. Verification (If email present and not verified)
        # Re-verify if it's new OR if status is unknown
        should_verify = lead.email and (is_new or lead.verification_status == "unknown")
        
        if should_verify:
            # OPTIMIZATION: Removed synchronous verification (Too slow for search loop)
            # status, reason = VerificationService.verify_email_dns(lead.email)
            # lead.verification_status = status
            # lead.save(update_fields=['verification_status'])
            pass
            
        # B. Scoring (Always score on update/create)
        # This will save the model
        LeadScoringService.score_lead(lead, icp_params=icp_params)
        
    except Exception as e:
        logger.error(f"Post-processing trigger failed for lead {lead.id}: {e}")

