import logging
from ..models import Lead, LeadEvent, LeadList

logger = logging.getLogger(__name__)

class LeadRepository:
    """
    Handles all database interactions for Leads.
    """

    @staticmethod
    def get_lead_by_third_party_id(tid, channel=None):
        if channel:
            return Lead.objects.filter(third_party_org_id=tid, channel=channel).first()
        return Lead.objects.filter(third_party_org_id=tid).first()

    @staticmethod
    def get_lead_by_email(email):
        return Lead.objects.filter(email__iexact=email).first()

    @staticmethod
    def get_lead_by_company_name(name):
        return Lead.objects.filter(company_name=name).first()

    @staticmethod
    def create_lead(data):
        """
        Creates a new Lead record from a dictionary.
        """
        try:
            lead = Lead.objects.create(**data)
            return lead
        except Exception as e:
            logger.error(f"Error creating lead: {e}")
            raise

    @staticmethod
    def create_lead_event(lead, event_type, metadata=None, org_id=None, actor_user_id=None):
        """
        Logs an event for a lead.
        """
        if metadata is None:
            metadata = {}
            
        # Fallback for org_id if not provided but lead has it (TODO: Lead doesn't have org_id directly yet in some contexts, but let's allow passing it)
        # Note: Lead model might not store org_id directly if it's implicitly tenant-scoped or uses company relation. 
        # Checking Lead model: no 'org_id' field on Lead class in lines 175-269.
        
        return LeadEvent.objects.create(
            lead=lead,
            org_id=org_id,
            event_type=event_type,
            metadata=metadata,
            actor_user_id=actor_user_id
        )

    @staticmethod
    def save_lead_if_new(candidate_data, source_type="person"):
        """
        Checks for duplicates by Third-Party ID, Email, or Company Name (depending on type).
        If exists, returns existing lead.
        If new, creates and returns new lead.

        Args:
            candidate_data (dict): The raw or normalized data derived from the source.
            source_type (str): 'organization' or 'person' (used to decide dedup logic).
        """

        # 1. Check Third Party ID
        tid = candidate_data.get("third_party_org_id")
        if tid:
            existing = LeadRepository.get_lead_by_third_party_id(tid)
            if existing:
                return existing, False

        # 2. Check Email (if person)
        email = candidate_data.get("email")
        if email:
            existing = LeadRepository.get_lead_by_email(email)
            if existing:
                return existing, False

        # 3. Check Company Name (if organization and no specific ID match yet)
        # Note: Name checks can be risky, but requested in original logic.
        if source_type == "organization":
            name = candidate_data.get("company_name")
            if name:
                existing = LeadRepository.get_lead_by_company_name(name)
                if existing:
                    return existing, False

        # 4. Create New
        # Ensure we don't pass fields that aren't in the model if candidate_data has extras?
        # Assuming candidate_data is prepared correctly by the Service.
        new_lead = LeadRepository.create_lead(candidate_data)
        return new_lead, True

    @staticmethod
    def search_local_leads(filters):
        """
        Searches the local database for leads matching the criteria.
        Returns QuerySet.
        """
        from django.db.models import Q

        query = Q()

        # Job Titles (OR logic if multiple)
        titles = filters.get("job_titles", [])
        if titles:
            title_query = Q()
            for t in titles:
                title_query |= Q(title__icontains=t)
            query &= title_query

        # Location (city/state/country)
        location = filters.get("location") or filters.get("person_locations", [])
        if location:
            # Handle list or string
            if isinstance(location, list):
                loc_query = Q()
                for l in location:
                    loc_query |= Q(location__icontains=l)
                query &= loc_query
            else:
                query &= Q(location__icontains=location)

        # Industry
        industry = filters.get("industry")
        if industry:
            query &= Q(industry__icontains=industry)

        # Keyword (generic search)
        keyword = filters.get("q_keywords")
        if keyword:
            query &= (Q(title__icontains=keyword) | Q(company_name__icontains=keyword))

        return Lead.objects.filter(query).order_by('-score', '-id') # Rank by Score using the new field
