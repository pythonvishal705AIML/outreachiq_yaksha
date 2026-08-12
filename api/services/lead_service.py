import os
import json
import logging
import time
from ..repositories.lead_repository import LeadRepository
from .lead_mapper_service import LeadMapperService
from django.db import IntegrityError

logger = logging.getLogger(__name__)

class LeadService:
    def search_organizations(self, filters):
        """
        Search for Organizations. No external organization-data provider is
        currently configured — returns an empty result set instead of erroring.
        """
        logger.warning(
            "search_organizations called but no external organization-data "
            "provider is configured. Returning empty results."
        )
        return []


    def search_people(self, filters, session_id=None, channel=None, account_id=None, saved_search_id=None, name=None, icp_params=None, search_run_id=None):
        """
        Search for People (Candidates).
        Local-DB first. No external lead-data provider is currently configured,
        so results beyond the local cache come back empty — leads should be
        added via the Excel/CSV upload flow instead.
        Returns list of Lead objects.
        """
        _t_total = time.perf_counter()
        logger.info(f"Executing People Search (Channel: {channel}, Account: {account_id}, Name: {name}, RunID: {search_run_id})...")
        
        # We ensure 'limit' is set if not present.
        limit = filters.get("limit", 10)
        filters["limit"] = limit

        # Track sources dynamically (Use a Set)
        active_sources = set()
        
        # Imports for Persistence
        from ..models import SearchRun, SearchRunLead, PeopleSearch, ConversationSession
        from ..models import Company as CompanyModel
        # --- Resolve session & account context ---
        conversation = None
        if session_id:
            try:
                conversation = ConversationSession.objects.get(session_id=session_id)
                if not account_id:
                    account_id = conversation.tenant_id
            except ConversationSession.DoesNotExist:
                logger.warning(f"Invalid session_id: {session_id}. Proceeding without session.")
                session_id = None  # Reset so downstream `if session_id:` blocks skip cleanly

        # Fallback: Try to get account_id from filters/icp_params if still missing
        if not account_id:
            account_id = filters.get("account_id") or filters.get("org_id") or (
                icp_params.get("account_id") if icp_params else None)

        if not account_id:
            logger.warning("No account_id resolved. SearchRun will have org_id=None.")

            # 1. Local Search First (Skip if appending to existing run)
        if not search_run_id:
            _t_local = time.perf_counter()
            local_leads = LeadRepository.search_local_leads(filters)
            local_count = local_leads.count()
            _local_ms = round((time.perf_counter() - _t_local) * 1000)
            
            # Pagination Logic for Local
            page = int(filters.get("page", 1))
            limit_int = int(limit)
            offset = (page - 1) * limit_int
            
            # If we have enough local leads to cover *this specific page*
            if local_count > offset:
                logger.info(f"Found {local_count} local matches. Serving Page {page} from Cache.")
                
                # Slice for Page
                page_leads = local_leads[offset : offset + limit_int]
                
                # Identify channels from the local leads
                for l in page_leads:
                    if l.channel:
                        active_sources.add(l.channel) # e.g. "upload", "apollo" (legacy)
                
                # Fallback if channel missing
                if not active_sources:
                     active_sources.add("local_cache")


                # Create SearchRun for Local Hit
                local_search_run = SearchRun.objects.create(
                    filters_json=filters,
                    icp_params=icp_params if icp_params else {},
                    source_used=list(active_sources),
                    lead_count=local_count, # Use Total Count
                    status='completed',
                    query_text=name,
                    org_id=account_id # Save Context
                )

                # Link local leads to SearchRun
                for l in page_leads:
                    SearchRunLead.objects.get_or_create(search_run=local_search_run, lead=l)

                # Construct search-result response structure for frontend compatibility
                people_list = []
                for l in page_leads:
                    p_item = {
                        "id": l.third_party_org_id or str(l.id),
                        "lead_id": l.id,
                        # Name
                        "first_name": l.first_name,
                        "last_name": l.last_name,
                        "last_name_obfuscated": l.last_name,
                        # Role
                        "title": l.title,
                        "seniority": l.person_seniority,
                        "departments": [l.person_department] if l.person_department else [],
                        # Contact — actual values instead of booleans
                        "has_email": l.email or None,
                        "has_direct_phone": l.phone or None,
                        "email": l.email,
                        "phone_number": l.phone,
                        # Location
                        "city": l.company_hq_city or l.location,
                        "state": l.company_hq_region,
                        "country": l.company_hq_country,
                        # Company
                        "organization": {
                            "name": l.company_name,
                            "industry": l.industry,
                            "website_url": l.company_domain,
                            "estimated_num_employees_min": l.company_employees_min,
                            "estimated_num_employees_max": l.company_employees_max,
                        },
                        # Social
                        "linkedin_url": l.linkedin_url,
                        # Enrichment
                        "is_revealed": l.is_revealed,
                        "verification_status": l.verification_status,
                        "score": l.score,
                    }
                    people_list.append(p_item)
                    
                # return {
                #     "people": people_list, 
                #     "total_entries": local_count, 
                #     "source": "local_cache"
                # }
                _total_ms = round((time.perf_counter() - _t_total) * 1000)
                print(
                    f"\n[People Search Latency] source=local_cache | "
                    f"local_db={_local_ms}ms | "
                    f"external_api=0ms (cache hit) | "
                    f"lead_processing=0ms | "
                    f"total={_total_ms}ms | "
                    f"leads_returned={len(people_list)}\n"
                )
                return {
                    "people": people_list,
                    "total_entries": local_count,
                    "source": "local_cache",
                    "search_run_id": str(local_search_run.search_id),
                    "status_url": f"/api/leads/search/status/{local_search_run.search_id}/",
                    "full_results_url": f"/api/leads/search/runs/{local_search_run.search_id}/leads/"
                }

        # 2. External Search (if local insufficient OR extending run)
        # No external lead-data provider is currently configured. Local-cache
        # results (above) are the only source; leads beyond that should be
        # added via the Excel/CSV upload flow.

        active_sources.add(channel or "none")

        people = []
        results = {"people": []}

        if channel:
            logger.warning(
                f"No external lead-search provider is configured for channel='{channel}'. "
                "Returning local results only."
            )
        else:
            logger.info("No external lead-search provider configured. Returning local results only.")

        # Map 'pagination.total_entries' to top-level 'total_entries'
        if "pagination" in results:
            results["total_entries"] = results["pagination"].get("total_entries")
        else:
             results["total_entries"] = results.get("total_entries")

        # Enrichment requires an external lead-data provider; none is configured.
        final_enriched_leads_map = {}

        # ---------------------------------------------------
        # EXECUTION TRACKING (Create or Retrieve Run)
        # ---------------------------------------------------

        search_run = None
        if search_run_id:
             try:
                 search_run = SearchRun.objects.get(search_id=search_run_id)
                 # Update Count with latest Total from Provider
                 total = results.get("total_entries")
                 if total:
                      search_run.lead_count = total
                      search_run.save(update_fields=["lead_count"])
             except SearchRun.DoesNotExist:
                 logger.warning(f"Provided search_run_id {search_run_id} not found. Creating new.")
        
        if not search_run:
            total_est = results.get("total_entries") or len(people)
            search_run = SearchRun.objects.create(
                filters_json=filters,
                icp_params=icp_params if icp_params else {},
                source_used=list(active_sources),
                lead_count=total_est, # Store Total Available
                status='completed',
                # query_text=filters.get("name") or query_text_payload,
                query_text=filters.get("name") or ", ".join(filter(None, [
                    ", ".join(filters.get("person_titles") or []),
                    ", ".join(filters.get("q_keywords") or []),
                    ", ".join(filters.get("organization_names") or []),
                ])) or name,
                org_id=account_id,
                saved_search_id=saved_search_id
            )

        search_record = PeopleSearch.objects.create(params=filters, results=results)
        if session_id:
            try:
                search_record.session = conversation
                search_record.save()
            except:
                pass
            
        # ---------------------------------------------------
        # DATA PERSISTENCE & MAPPING (PARALLELIZED)
        # ---------------------------------------------------
        import concurrent.futures

        def process_single_lead(p):
            try:
                pid = str(p.get("id"))
                
                # Check Local Enriched Map (Unused for standard search, but kept for logic consistency)
                lead_obj = final_enriched_leads_map.get(pid)
                
                if lead_obj:
                    # Logic for already enriched leads (from reveal_people usually)
                    lead = lead_obj
                    is_new = False
                    
                    if lead.last_search_run_id != search_run.search_id:
                        lead.last_search_run_id = search_run.search_id
                        lead.save(update_fields=["last_search_run_id"])
                    
                    p["email"] = lead.email
                    p["phone_number"] = lead.phone
                    p["is_revealed"] = True
                    p["lead_id"] = lead.id
                    p["score"] = lead.score
                    if lead.first_name: p["first_name"] = lead.first_name
                    if lead.last_name: p["last_name"] = lead.last_name
                    
                    p.pop("last_name_obfuscated", None)
                    # p.pop("email", None)
                    
                    return lead
                    
                else:
                    # New or Non-Revealed Lead
                    org_data = p.get("organization") or {}
                    company_obj = None
                    if org_data.get("name"):
                        domain = org_data.get("website_url") or org_data.get("primary_domain")
                        defaults = {
                            "name": org_data.get("name"),
                            "domain": domain,
                            "industry": org_data.get("industry") or filters.get("industry"),
                            "source_meta": {"third_party_org_id": org_data.get("id")}
                        }
                        # Optimized Company Creation
                        if domain:
                            company_obj = CompanyModel.objects.filter(domain=domain).first()
                            if not company_obj:
                                 company_obj = CompanyModel.objects.create(**defaults)
                        elif defaults.get("name"):
                            company_obj = CompanyModel.objects.filter(name=defaults["name"]).first()
                            if not company_obj:
                                 company_obj = CompanyModel.objects.create(**defaults)

                    lead, is_new = LeadMapperService.map_and_save_lead(
                        p,
                        channel=channel or "unknown",
                        company_obj=company_obj,
                        extra_flags={"last_search_run_id": search_run.search_id}, 
                        icp_params=icp_params
                    )
                    
                    p["is_revealed"] = lead.is_revealed
                    p["lead_id"] = lead.id
                    p["score"] = lead.score
                    # Replace boolean has_* flags with actual values
                    p["has_email"] = lead.email or None
                    p["has_direct_phone"] = lead.phone or None
                    p["email"] = lead.email
                    p["phone_number"] = lead.phone
                    p["city"] = lead.company_hq_city or p.get("city")
                    p["state"] = lead.company_hq_region or p.get("state")
                    p["country"] = lead.company_hq_country or p.get("country")
                    
                    return lead

            except Exception as e:
                logger.error(f"Error processing lead {p.get('id')}: {e}")
                return None

        # Execute Parallel Processing
        # We process 'people' list in parallel and collect Lead objects for ManyToMany linking
        processed_leads = []
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            future_to_lead = {executor.submit(process_single_lead, p): p for p in people}
            
            for future in concurrent.futures.as_completed(future_to_lead):
                lead = future.result()
                if lead:
                    processed_leads.append(lead)

        # Bulk Link to Search Record (Fast)
        if processed_leads:
            search_record.leads.add(*processed_leads)
            
            # Bulk link to SearchRun (single query instead of N queries)
            srl_objects = [
                SearchRunLead(search_run=search_run, lead=lead)
                for lead in processed_leads
            ]
            SearchRunLead.objects.bulk_create(srl_objects, ignore_conflicts=True)

        results["search_run_id"] = str(search_run.search_id)
        
        # Build full URLs using domain from settings
        from django.conf import settings
        domain_url = getattr(settings, 'SQUIBB_DOMAIN_URL', 'https://test-ai.squibb.ai')
        
        results["status_url"] = f"{domain_url}/api/leads/search/status/{search_run.search_id}/"
        results["full_results_url"] = f"{domain_url}/api/leads/search/runs/{search_run.search_id}/leads/"
        
        return results

    def reveal_people(self, ids, channel=None, account_id=None, icp_params=None):
        """
        Takes a list of third-party/local lead IDs selected by the user.
        Checks DB: if present, returns it.
        If missing/partial, attempts enrichment via an external provider
        (none currently configured) -> Saves -> Returns.
        """
        from ..models import SearchRun, SearchRunLead
        
        logger.info(f"Revealing (Enriching) {len(ids)} people via {channel} (Account: {account_id})...")

        final_leads = []
        ids_to_enrich = []

        # 1. Check DB first
        for pid in ids:
            existing = LeadRepository.get_lead_by_third_party_id(pid, channel=channel)
            # REFACTOR: Check if email is present instead of is_revealed flag
            # FIX (2025): Even if email present, if name is obfuscated, we MUST enrich.
            is_obfuscated = existing and existing.last_name and "***" in existing.last_name
            if existing and existing.email and not is_obfuscated:
                # We have the email AND a clear name -> Consider it revealed/cached
                final_leads.append(existing)
            else:
                # Missing OR Exists but has no email -> Needs Enrichment
                ids_to_enrich.append(pid)
        
        newly_discovered_leads = []

        # 2. Enrich missing ones
        enriched_leads = [] # Track all leads that touched the API
        if ids_to_enrich:
            try:
                # No external enrichment provider is currently configured.
                enriched_results = []
                logger.warning(
                    f"No external enrichment provider is configured (channel='{channel}'). "
                    f"{len(ids_to_enrich)} lead(s) could not be enriched."
                )

                # Parallel Lead Processing
                import concurrent.futures
                
                def process_lead(data):
                     try:
                        return LeadMapperService.map_and_save_lead(data, channel=channel, is_revealed=True, icp_params=icp_params)
                     except Exception as e:
                        logger.error(f"Error processing lead {data.get('id')}: {e}")
                        return None, False

                with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
                    futures = [executor.submit(process_lead, d) for d in enriched_results]
                    
                    for future in concurrent.futures.as_completed(futures):
                        lead, is_new = future.result()
                        if lead:
                            final_leads.append(lead)
                            if is_new:
                                newly_discovered_leads.append(lead)
                            enriched_leads.append(lead)
                     
            except Exception as e:
                logger.error(f"Error during enrichment: {e}", exc_info=True)
        
        # 4. Log Attribution Events
        # Since we removed SearchRun, we must ensure every API cost is tracked via LeadEvent.
        try:
             for lead in enriched_leads:
                 # Determine event type: 'discovered' if new, 'revealed' if existing
                 # Actually, 'revealed' is accurate for the action performed on all.
                 event_type = "discovered" if lead in newly_discovered_leads else "revealed"
                 
                 LeadRepository.create_lead_event(
                    lead=lead, 
                    event_type=event_type, 
                    org_id=account_id,
                    metadata={
                        "sources": [channel, "reveal_api"],
                        "note": "Reveal/Enrich request (No SearchRun)"
                    }
                )
        except Exception as e:
             logger.error(f"Failed to log events for reveal: {e}")

        return final_leads
