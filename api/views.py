# api/views.py
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.http import StreamingHttpResponse
import logging
from django.forms.models import model_to_dict
from .services.main_service import APIService
from .services.lead_service import LeadService
from .repositories.lead_repository import LeadRepository
from .models import ConversationSession
from .services.business_extractor import BusinessExtractor
from .services.campaign_service import CampaignService
from .services.recommendation_service import RecommendationService
from .services.company_enrichment_service import CompanyEnrichmentService
import uuid
import json

logger = logging.getLogger(__name__)
_campaign_service = CampaignService()
class HealthCheckView(APIView):
    """
    Simple health check endpoint.
    """
    def get(self, request, *args, **kwargs):
        return Response(
            {"status": "ok"},
            status=status.HTTP_200_OK
        )


class InitConversationView(APIView):
    """
    Initializes a new conversation session.
    """

    def post(self, request):
        tenant_id = request.data.get("tenant_id")
        initial_text = request.data.get("text", "").strip()

        logger.info(f"InitConversation: Tenant={tenant_id}, InitialText='{initial_text}'")

        if not tenant_id:
            logger.warning("InitConversation: Missing tenant_id")
            return Response(
                {"error": "tenant_id is required"},
                status=status.HTTP_400_BAD_REQUEST
            )

        session_id = APIService.init_conversation_session(tenant_id, initial_text)
        logger.info(f"InitConversation: Created Session={session_id}")

        return Response(
            {
                "session_id": session_id,
                "message": "Conversation initialized"
            },
            status=status.HTTP_201_CREATED
        )




class ConversationMessageView(APIView):

    def post(self, request):

        session_id = request.data.get("session_id")
        user_text = request.data.get("text", "").strip()
        
        logger.info(f"MessageView: Session={session_id}, Input='{user_text}'")

        if not session_id:
            logger.warning("MessageView: session_id is missing")
            return Response(
                {"error": "session_id is missing"},
                status=status.HTTP_400_BAD_REQUEST
            )

        if not user_text:
            logger.warning("MessageView: text is missing")
            return Response(
                {"error": "text is missing"},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            bot_result = APIService.handle_conversation_message(session_id, user_text)
            # bot_result is {"text": "...", "parameters": {...}}
            logger.info(f"MessageView: Success. Reply='{bot_result.get('text')}'")
        except ConversationSession.DoesNotExist:
             logger.error(f"MessageView: Invalid Session {session_id}")
             return Response(
                {"error": "Invalid session_id"},
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            logger.exception(f"MessageView: Error handling message: {e}")
            return Response(
                {"error": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

        response_data = {
            "reply": bot_result.get("text", "")
        }
        
        # Add Flow Tracking
        if "current_flow" in bot_result:
            response_data["current_flow"] = bot_result["current_flow"]
        if "past_flows" in bot_result:
            response_data["past_flows"] = bot_result["past_flows"]
        if "future_flows" in bot_result:
            response_data["future_flows"] = bot_result["future_flows"]
        
        # Add Campaign Context (for campaign_flow)
        if "campaign_status" in bot_result:
            response_data["campaign_status"] = bot_result["campaign_status"]
        if "campaign_context" in bot_result:
            response_data["campaign_context"] = bot_result["campaign_context"]
        
        # Only include rich data if parameters are present
        if "parameters" in bot_result:
            # response_data["params"] = bot_result["parameters"] 
            
            if "state" in bot_result:
                # Extract slots solely, discard state wrapper
                slots = bot_result["state"].get("slots", {})
                response_data["slots"] = slots

        return Response(response_data)


class ConversationHistoryView(APIView):
    """
    Returns full conversation history.
    """

    def post(self, request):
        session_id = request.data.get("session_id")

        if not session_id:
            return Response(
                {"error": "session_id is required"},
                status=status.HTTP_400_BAD_REQUEST
            )
        output = APIService.session_history(session_id)

        return Response(
            output,
            status=status.HTTP_200_OK
        )


class ResetConversationView(APIView):
    """
    Resets conversation flow/state.
    """

    def post(self, request):
        session_id = request.data.get("session_id")
        logger.info(f"ResetView: Session={session_id}")

        if not session_id:
            return Response(
                {"error": "session_id is required"},
                status=status.HTTP_400_BAD_REQUEST
            )

        APIService.reset_conversation_session(session_id)


        return Response(
            {"message": "Conversation state reset"},
            status=status.HTTP_200_OK
        )


class OrganizationSearchView(APIView):
    def post(self, request):
        """
        Search for Organizations. No external organization-data provider is
        currently configured; returns an empty list.
        Payload: { "params": { "industry": "IT", "location": "NY" } }
        """
        filters = request.data.get("params", {})
        service = LeadService()
        
        try:
            leads = service.search_organizations(filters)
            
            # Serialize response
            data = []
            for l in leads:
                d = model_to_dict(l)
                d['id'] = l.id
                d['created_at'] = l.created_at
                data.append(d)
            
            return Response(data, status=status.HTTP_200_OK)
            
        except Exception as e:
            logger.error(f"Organization Search Failed: {e}", exc_info=True)
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class PeopleSearchView(APIView):
    def post(self, request):
        """
        People Search API (Lite).
        Payload: { "params": { "title": "CEO", ... }, "session_id": "optional" }
        Returns: Dict with people list & pagination & flow status.
        """
        service = LeadService()
        session_id = request.data.get("session_id")
        channel = request.data.get("channel") # No external provider configured by default
        account_id = request.data.get("account_id") # Context

        try:
            filters = request.data.get("params", {})
            saved_search_id = request.data.get("saved_search_id") or request.data.get("saved_id")
            print(filters)
            # If saved_search_id provided, fetch filters from DB
            if saved_search_id:
                 try:
                     from .models import SavedSearch
                     saved_search = SavedSearch.objects.get(saved_id=saved_search_id)
                     saved_filters = saved_search.filters_json
                     
                     # Merge: Params override Saved Filters if both exist (Refinement)
                     # Start with saved filters
                     final_filters = saved_filters.copy()
                     # Update with explicit params
                     final_filters.update(filters)
                     filters = final_filters
                 except SavedSearch.DoesNotExist:
                     return Response({"error": "Saved Search not found"}, status=status.HTTP_404_NOT_FOUND)

            # Ensure `name` is persisted as a single functional ICP label string.
            # LLM output may provide `name` as an array to satisfy prompt formatting rules.
            name_val = filters.get("name")
            if isinstance(name_val, list):
                name_val = next((str(v).strip() for v in name_val if str(v).strip()), None)
            elif isinstance(name_val, str):
                name_val = name_val.strip() or None
            elif name_val is not None:
                name_val = str(name_val).strip() or None

            if not name_val and saved_search_id:
                try:
                    from .models import SavedSearch
                    saved_search = SavedSearch.objects.get(saved_id=saved_search_id)
                    name_val = (saved_search.name or "").strip() or None
                except SavedSearch.DoesNotExist:
                    name_val = None

            if name_val:
                filters["name"] = name_val

            # Explicit Pagination
            page = request.data.get("page", 1)
            per_page = request.data.get("per_page", 10)
            filters["page"] = page
            filters["per_page"] = per_page
            filters["limit"] = per_page
            if account_id:
                filters["account_id"] = account_id
            results = service.search_people(
                filters, 
                session_id=session_id, 
                channel=channel, 
                account_id=account_id,
                icp_params=filters, 
                name=filters.get("name")
            )
            
            response_data = results
            
            # LIMIT RESPONSE TO 5 
            # We still keep 'total_entries' as is (73k+) to show scale, but only return 5 rows for UI/Perf.
            if "people" in response_data:
                response_data["people"] = response_data["people"][:5]
            
            # Flow Tracking Integration
            if session_id:
                try:
                    session = ConversationSession.objects.get(session_id=session_id)
                    
                    # 1. Log User Request
                    from .models import ConversationMessage
                    ConversationMessage.objects.create(
                        session=session,
                        role="user",
                        text=f"People Search Parameters: {filters}",
                        metadata={"type": "people_search_request", "params": filters}
                    )

                    from .services.orchestrator import ConversationOrchestrator
                    orch = ConversationOrchestrator(session)
                    flow_status = orch.transition_flow("people_search_api")
                    response_data.update(flow_status)

                    # 2. Log Assistant Response
                    people_count = len(results.get("people", []))
                    # Convert UUIDs/datetimes to strings for JSON serialization
                    serializable_results = json.loads(json.dumps(results, default=str))
                    ConversationMessage.objects.create(
                        session=session,
                        role="assistant",
                        text=f"Found {people_count} profiles based on search parameters.",
                        metadata={"type": "people_search_response", "results": serializable_results}
                    )

                except ConversationSession.DoesNotExist:
                    logger.warning(f"PeopleSearch: Invalid session_id {session_id}")
            
            return Response(response_data, status=status.HTTP_200_OK)

        except Exception as e:
            logger.error(f"People Search Failed: {e}", exc_info=True)
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class PeopleRevealView(APIView):
    def post(self, request):
        """
        People Reveal API (Enrich).
        Payload: { "ids": ["123", "456"], "session_id": "optional" }
        Returns: Full enriched profiles & flow status.
        """
        service = LeadService()
        session_id = request.data.get("session_id")

        try:
            # Flexible Input: 'ids' (new) or 'apollo_ids' (legacy callers)
            ids_to_reveal = request.data.get("ids") or request.data.get("apollo_ids")
            channel = request.data.get("channel") # No external provider configured by default
            account_id = request.data.get("account_id") # Context

            if not ids_to_reveal:
                 return Response({"error": "ids (or apollo_ids) is required"}, status=status.HTTP_400_BAD_REQUEST)

            leads = service.reveal_people(ids_to_reveal, channel=channel, account_id=account_id)
            data = []
            for l in leads:
                d = model_to_dict(l)
                d['id'] = l.id
                d['is_revealed'] = True
                data.append(d)
                
            response_data = {"results": data}
            
            # Flow Tracking Integration
            if session_id:
                try:
                    session = ConversationSession.objects.get(session_id=session_id)
                    
                    # 1. Log User Request
                    from .models import ConversationMessage
                    ConversationMessage.objects.create(
                        session=session,
                        role="user",
                        text=f"Revealing {len(ids_to_reveal)} profiles",
                        metadata={"type": "people_reveal_request", "ids": ids_to_reveal}
                    )

                    from .services.orchestrator import ConversationOrchestrator
                    orch = ConversationOrchestrator(session)
                    flow_status = orch.transition_flow("people_reveal_api")
                    response_data.update(flow_status)

                    # 2. Log Assistant Response
                    # Convert UUIDs/datetimes to strings for JSON serialization
                    serializable_data = json.loads(json.dumps(response_data, default=str))
                    ConversationMessage.objects.create(
                        session=session,
                        role="assistant",
                        text=f"Revealed and enriched {len(data)} profiles.",
                        metadata={"type": "people_reveal_response", "results": serializable_data}
                    )

                except ConversationSession.DoesNotExist:
                    logger.warning(f"PeopleReveal: Invalid session_id {session_id}")
                
            return Response(response_data, status=status.HTTP_200_OK)

        except Exception as e:
            logger.error(f"People Reveal Failed: {e}", exc_info=True)
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)




class BusinessProfileExtractView(APIView):
    """
    POST /business/extract/
    Extracts business profile from a website URL.
    Payload: { "name": "...", "url": "..." }
    """
    def post(self, request):
        name = request.data.get("name")
        url = request.data.get("url")
        
        if not name or not url:
             return Response({"error": "name and url are required"}, status=status.HTTP_400_BAD_REQUEST)

        try:
             extractor = BusinessExtractor()
             result = extractor.extract(name, url)
             return Response(result, status=status.HTTP_200_OK)
        except ValueError as ve:
             # Website unreachable or scraping failed
             return Response({"error": str(ve)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
             logger.error(f"Business Profile Extraction Failed: {e}", exc_info=True)
             return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class PromptRecommendationView(APIView):
    """
    POST /recommendations/prompts
    Generates 4 personalized prompt suggestions.
    Payload: { "account_id": "..." }
    """
    def post(self, request):
        account_id = request.data.get("account_id")
        
        if not account_id:
             return Response({"error": "account_id is required"}, status=status.HTTP_400_BAD_REQUEST)

        try:
             service = RecommendationService()
             result = service.generate_suggested_prompts(account_id)
             return Response(result, status=status.HTTP_200_OK)
        except ValueError as ve:
             return Response({"error": str(ve)}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
             logger.error(f"Prompt Recommendation Failed: {e}", exc_info=True)
             return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class ScoreLeadView(APIView):
    """
    POST /leads/score/
    Calculates and updates the Quality and ICP Fit score for a lead.
    Payload: { "id": "...", "account_id": "..." }
    """
    def post(self, request):
        try:
            from .models import Lead, BusinessProfile
            from .services.scoring_service import LeadScoringService

            data = request.data
            ext_id = data.get("id")
            account_id = data.get("account_id")

            # 1. Validation
            if not ext_id:
                 return Response({"error": "id is required"}, status=status.HTTP_400_BAD_REQUEST)

            # 2. Fetch Lead
            try:
                lead = None
                # Support looking up by internal id (primary) or third_party_org_id (fallback)
                if str(ext_id).isdigit():
                    lead = Lead.objects.filter(id=int(ext_id)).first()

                if not lead:
                    lead = Lead.objects.filter(third_party_org_id=ext_id).first()

                if not lead:
                    return Response({"error": f"Lead not found with id: {ext_id}"}, status=status.HTTP_404_NOT_FOUND)

            except Exception as e:
                return Response({"error": f"Error finding lead: {str(e)}"}, status=status.HTTP_400_BAD_REQUEST)

            # 3. Fetch Profile (Context)
            profile = None
            if account_id:
                profile = BusinessProfile.objects.filter(account_id=account_id).first()
                if not profile:
                    return Response({"error": f"Business Profile not found for account_id: {account_id}"}, status=status.HTTP_404_NOT_FOUND)
            
            # 4. Score
            result = LeadScoringService.score_lead(lead, profile)
            
            if "error" in result:
                 return Response(result, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

            return Response(result, status=status.HTTP_200_OK)

        except Exception as e:
            logger.error(f"Score Lead Failed: {e}", exc_info=True)
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class SavedSearchView(APIView):
    """
    Manage Saved Searches (filters).
    GET /leads/saved/ -> List all (filtered by user/org) or specific id=?id=...
    POST /leads/saved/ -> Create
    PUT /leads/saved/?id=... -> Update
    DELETE /leads/saved/?id=... -> Delete
    """
    def get(self, request):
        try:
            from .models import SavedSearch
            
            # Optional: Filter by specific ID
            saved_id = request.query_params.get('id')
            if saved_id:
                obj = SavedSearch.objects.filter(saved_id=saved_id).first()
                if not obj:
                    return Response({"error": "Saved search not found"}, status=status.HTTP_404_NOT_FOUND)
                
                d = model_to_dict(obj)
                d['saved_id'] = obj.saved_id
                d['created_at'] = obj.created_at
                d['last_run'] = obj.last_run
                return Response(d, status=status.HTTP_200_OK)

            # List all (Required: Filter by user_id or org_id)
            user_id = request.query_params.get('user_id')
            org_id = request.query_params.get('org_id')
            
            if not user_id and not org_id:
                 return Response({"error": "user_id or org_id query param is required"}, status=status.HTTP_400_BAD_REQUEST)

            queryset = SavedSearch.objects.all().order_by('-created_at')
            if user_id:
                queryset = queryset.filter(user_id=user_id)
            if org_id:
                queryset = queryset.filter(org_id=org_id)
                
            data = []
            for item in queryset:
                d = model_to_dict(item)
                d['saved_id'] = item.saved_id
                d['filters_json'] = item.filters_json
                d['created_at'] = item.created_at
                d['last_run'] = item.last_run
                data.append(d)
                
            return Response(data, status=status.HTTP_200_OK)

        except Exception as e:
            logger.error(f"SavedSearch GET Failed: {e}", exc_info=True)
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def post(self, request):
        try:
            from .models import SavedSearch
            data = request.data
            
            user_id = data.get("user_id")
            org_id = data.get("org_id")
            name = data.get("name")

            # Strict validation
            if not name:
                return Response({"error": "name is required"}, status=status.HTTP_400_BAD_REQUEST)
            if not user_id and not org_id:
                 return Response({"error": "user_id or org_id is required"}, status=status.HTTP_400_BAD_REQUEST)
                
            # Create
            obj = SavedSearch.objects.create(
                user_id=user_id,
                org_id=org_id,
                name=name,
                description=data.get("description"),
                filters_json=data.get("filters_json", {})
            )
            
            # Response
            return Response({
                "success": True, 
                "message": "Saved search created successfully.",
                "saved_id": obj.saved_id
            }, status=status.HTTP_201_CREATED)
            

        except Exception as e:
            logger.error(f"SavedSearch POST Failed: {e}", exc_info=True)
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def put(self, request):
        try:
            from .models import SavedSearch
            saved_id = request.query_params.get('id')
            data = request.data
            
            if not saved_id:
                return Response({"error": "id parameter is required for update"}, status=status.HTTP_400_BAD_REQUEST)
                
            obj = SavedSearch.objects.filter(saved_id=saved_id).first()
            if not obj:
                return Response({"error": "Saved search not found"}, status=status.HTTP_404_NOT_FOUND)
                
            # Update fields if present
            if "name" in data:
                obj.name = data["name"]
            if "description" in data:
                obj.description = data["description"]
            
            # Map 'filters' (user payload) to 'filters_json' (model field) or update 'filters_json' directly
            new_filters = data.get("filters_json") or data.get("filters")
            if new_filters is not None:
                obj.filters_json = new_filters
                
            if "user_id" in data:
                obj.user_id = data["user_id"]
            if "org_id" in data:
                obj.org_id = data["org_id"]  

            obj.save()
            
            d = model_to_dict(obj)
            d['saved_id'] = obj.saved_id
            d['created_at'] = obj.created_at
            d['updated_at'] = obj.updated_at
            return Response(d, status=status.HTTP_200_OK)

        except Exception as e:
            logger.error(f"SavedSearch PUT Failed: {e}", exc_info=True)
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def delete(self, request):
        try:
            from .models import SavedSearch
            saved_id = request.query_params.get('id')
            
            if not saved_id:
                return Response({"error": "id parameter is required for delete"}, status=status.HTTP_400_BAD_REQUEST)
                
            obj = SavedSearch.objects.filter(saved_id=saved_id).first()
            if not obj:
                return Response({"error": "Saved search not found"}, status=status.HTTP_404_NOT_FOUND)
                
            obj.delete()
            return Response({"message": "Deleted successfully"}, status=status.HTTP_200_OK)

        except Exception as e:
            logger.error(f"SavedSearch DELETE Failed: {e}", exc_info=True)
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class AIQueryParseView(APIView):
    """
    POST /leads/ai/parse/
    Parses natural language into structured filters.
    Payload: { 
        "text": "Software engineers",
        "account_id": "optional_id", 
    }
    """
    def post(self, request):
        try:
            text = request.data.get("text")
            account_id = request.data.get("account_id")
            
            if not text:
                return Response({"error": "text is required"}, status=status.HTTP_400_BAD_REQUEST)
            
            # 1. Fetch Business Profile (if applicable)
            business_data = {}
            if account_id:
                from .models import BusinessProfile
                bp = BusinessProfile.objects.filter(account_id=account_id).first()
                if bp:
                    business_data = model_to_dict(bp)
            
            # 2. Call Extractor
            from .services.lead_extractor import LeadParameterExtractor
            extractor = LeadParameterExtractor()
            
            # Map view inputs to service inputs
            # user_query -> text
            # business_data -> Business Profile from DB
            print("business_data", business_data)
            result = extractor.extract(
                business_data=business_data, 
                current_state=None, 
                user_query=text,
                post_process=True
            )
            
            if "error" in result:
                return Response({"success": False, "error": result["error"]}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
                
            
            response_payload = {
                "success": True,
                "data": {
                    "filters": result.get("parameters", {}),
                    "confidence": result.get("confidence", {}),
                    "explanation": result.get("explanation"),
                    "raw_llm_output": None
                }
            }
                
            return Response(response_payload, status=status.HTTP_200_OK)
            
        except Exception as e:
             logger.error(f"AI Parse Failed: {e}", exc_info=True)
             return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


"""
Search History API
Return list of past SearchRuns.
"""
class SearchHistoryView(APIView):
    def get(self, request):
        try:
            from .models import SearchRun, SavedSearch
            
            # 1. Get Context (org_id is the primary filter)
            org_id = request.query_params.get("org_id") or request.query_params.get("account_id")
            
            # 2. Query Search Runs
            # if org_id:
            #     runs_query = SearchRun.objects.filter(org_id=org_id)
            
            # runs = runs_query.order_by('-created_at')[:50]
            if org_id:
                runs_query = SearchRun.objects.filter(org_id=org_id)
            else:
                return Response({"error": "org_id or account_id is required"}, status=status.HTTP_400_BAD_REQUEST)

            runs = runs_query.order_by('-created_at')[:50]
            
            # 3. Query Saved Searches (for name mapping)
            saved_name_map = {} # Map saved_id -> name
            saved_filter_map = [] # Map filters -> name
            
            if org_id:
                saved_searches = SavedSearch.objects.filter(org_id=org_id)
                for ss in saved_searches:
                    saved_name_map[ss.saved_id] = ss.name
                    saved_filter_map.append({"filters": ss.filters_json, "name": ss.name})

            data = []
            for run in runs:
                # 4. Determine Name
                run_name = None
                
                # Priority 0: Name from ICP Params (User Provided)
                # The user specifically asked to extract name from here
                if run.icp_params and run.icp_params.get("name"):
                    run_name = run.icp_params.get("name")
                    if isinstance(run_name, list):
                        run_name = next((str(v).strip() for v in run_name if str(v).strip()), None)
                
                # Priority 1: Direct Link (Backwards compat)
                if not run_name and run.saved_search_id and run.saved_search_id in saved_name_map:
                    run_name = saved_name_map[run.saved_search_id]

                # Priority 2: Direct name in filters (Legacy)
                if not run_name:
                    run_name = run.filters_json.get("name")
                    if isinstance(run_name, list):
                        run_name = next((str(v).strip() for v in run_name if str(v).strip()), None)
                
                # Priority 3: Fallback — use query_text but reject old JSON-dump and legacy junk values
                _LEGACY_FALLBACK_TEXTS = {"Search via API", "Search", "People Search"}
                if not run_name:
                    qt = run.query_text or ""
                    if qt.strip().startswith("{"):
                        try:
                            import json as _json
                            qt_data = _json.loads(qt)
                            titles = qt_data.get("person_titles") or []
                            locations = qt_data.get("person_locations") or []
                            industries = qt_data.get("industries") or []
                            parts = []
                            if titles: parts.append(", ".join(titles[:3]))
                            if industries: parts.append(", ".join(industries[:2]))
                            if locations: parts.append(", ".join(locations[:2]))
                            run_name = " — ".join(parts) if parts else None
                        except Exception:
                            run_name = None
                    elif qt and qt not in _LEGACY_FALLBACK_TEXTS:
                        run_name = qt

                # Priority 4: Try filters_json fields when all else fails
                if not run_name:
                    fj = run.filters_json or {}
                    titles = fj.get("person_titles") or []
                    industries = fj.get("industries") or []
                    locations = fj.get("person_locations") or []
                    parts = []
                    if titles: parts.append(", ".join(titles[:3]))
                    if industries: parts.append(", ".join(industries[:2]))
                    if locations: parts.append(", ".join(locations[:2]))
                    if parts:
                        run_name = " — ".join(parts)
                    elif run.created_at:
                        run_name = "Search on " + run.created_at.strftime("%b %d")
                    else:
                        run_name = "People Search"
                
                data.append({
                    "search_id": run.search_id,
                    "name": run_name, # Enriched Name
                    "lead_count": run.lead_count, 
                    "status": run.status,
                    "created_at": run.created_at,
                })
            
            return Response({"success": True, "history": data}, status=status.HTTP_200_OK)
        except Exception as e:
            logger.error(f"Search History Failed: {e}", exc_info=True)
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

"""
Search Status Endpoint
Check status of a specific run (polling).
"""
class SearchStatusView(APIView):
    def get(self, request, search_run_id):
        try:
            from .models import SearchRun
            run = SearchRun.objects.get(search_id=search_run_id)

            preview_leads = run.leads.all().order_by('search_run_leads__created_at')
            results_preview = []
            for l in preview_leads:
                 l_dict = model_to_dict(l)
                 # Add computed/extra fields not in model_to_dict by default or needing formatting
                 l_dict['id'] = str(l.id) # UUIDs sometimes need str conversion
                 if l.created_at: l_dict['created_at'] = l.created_at
                 results_preview.append(l_dict)

            # Construct Progress Object (Synchronous for now, so mostly 100% or 0)
            # In future, if async, these would read from run.stats_json
            progress_stats = {
                "total_expected": run.lead_count,
                "fetched": run.lead_count,
                "verified": 0, # Placeholder until E6
                "deduped": 0,  # Placeholder until E11
                "persisted": run.lead_count
            }

            return Response({
                "success": True,
                "data": {
                    "search_run_id": str(run.search_id),
                    "status": run.status,
                    "progress": progress_stats,
                    "result_preview": results_preview,
                    "errors": [] # Placeholder for run.errors_json if added later
                }
            }, status=status.HTTP_200_OK)
            
        except SearchRun.DoesNotExist:
            return Response({"error": "Search run not found"}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            logger.error(f"Search Status Failed: {e}", exc_info=True)
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class LeadDetailView(APIView):
    """
    GET /leads/{lead_id}/
    Details of a specific lead.
    """
    def get(self, request, lead_id):
        try:
             from .models import Lead
             
             # Support various ID formats (internal, third-party)
             lead = Lead.objects.filter(id=lead_id).first()
             if not lead and str(lead_id).isdigit():
                 lead = Lead.objects.filter(id=int(lead_id)).first()
             if not lead:
                 lead = Lead.objects.filter(third_party_org_id=lead_id).first()
             if not lead:
                 lead = Lead.objects.filter(third_party_org_id=lead_id).first()
                 
             if not lead:
                 return Response({"error": "Lead not found"}, status=status.HTTP_404_NOT_FOUND)
             
             d = model_to_dict(lead)
             d['id'] = lead.id
             
             if lead.company:
                c = model_to_dict(lead.company)
                c['id'] = lead.company.id
                d['company_details'] = c
                
             d['score_components'] = lead.score_components
             d['third_party_org_id'] = lead.third_party_org_id
             d['source_meta'] = lead.source_meta
             d['tags_json'] = lead.tags_json
             
             return Response(d, status=status.HTTP_200_OK)
             
        except Exception as e:
            logger.error(f"Lead Detail GET Failed: {e}", exc_info=True)
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class LeadFetchView(APIView):
    """
    POST /leads/fetch/
    Fetch full lead profile by ID and Channel.

    Payload:
    {
        "id": "...",
        "channel": "upload",
        "enrich_company": true  # optional, triggers Clearbit enrichment
    }
    """
    def post(self, request):
        try:
            from .models import Lead
            
            lead_id = request.data.get("id")
            channel = request.data.get("channel")
            enrich_company = bool(request.data.get("enrich_company", True))
            
            if not lead_id:
                return Response({"error": "id is required"}, status=status.HTTP_400_BAD_REQUEST)

            lead = None
            
            # 1. Try Local DB ID (Primary Key)
            if str(lead_id).isdigit():
                lead = Lead.objects.filter(id=int(lead_id)).first()
            
            if not lead:
                lead = Lead.objects.filter(third_party_org_id=lead_id).first()

            if not lead:
                 return Response({"error": "Lead not found"}, status=status.HTTP_404_NOT_FOUND)
            
            # 2. Optionally enrich company details via Clearbit
            enriched_company_details = None
            if enrich_company:
                try:
                    enriched_company_details = CompanyEnrichmentService.enrich_lead_company(lead)
                except Exception as e:
                    # Don't fail the whole request if Clearbit enrichment fails
                    logger.error(
                        f"Company enrichment failed during LeadFetchView for lead {lead.id}: {e}",
                        exc_info=True,
                    )

            # 3. Serialization (Matching LeadDetailView)
            d = model_to_dict(lead)
            d['id'] = lead.id
            
            if lead.company:
                c = model_to_dict(lead.company)
                c['id'] = lead.company.id
                d['company_details'] = c

            # If we computed an explicit enriched snapshot, prefer it
            if enriched_company_details:
                d['company_details'] = enriched_company_details
            
            # Ensure complex fields are included
            d['score_components'] = lead.score_components
            d['third_party_org_id'] = lead.third_party_org_id
            d['tags_json'] = lead.tags_json
            d['source_meta'] = lead.source_meta
            
            # Explicit Verification Fields
            d['verification_status'] = lead.verification_status
            d['verification_score'] = lead.deliverability_score  # Map to expected frontend key
            d['verification_reason'] = lead.verification_reason
            d['email_status'] = lead.verification_status  # Alias for convenience
            
            # Mask Email logic (User request: "not need to show the email keep true")
            # We return True if email exists, else None/False
            d['email'] = True if lead.email else False
            
            return Response(d, status=status.HTTP_200_OK)

        except Exception as e:
            logger.error(f"Lead Fetch POST Failed: {e}", exc_info=True)
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class LeadUploadView(APIView):
    """
    POST /leads/upload/ (multipart/form-data)
    Imports leads from an uploaded .csv or .xlsx file. Leads are upserted
    by email (channel="upload"). No external lead-data API is called.

    Form fields:
        file             - required, the .csv/.xlsx file
        lead_list_name   - optional, groups imported leads into a new LeadList
        owner_user_id    - optional
    """
    def post(self, request):
        from .services.lead_upload_service import import_leads

        upload = request.FILES.get("file")
        if not upload:
            return Response({"error": "file is required"}, status=status.HTTP_400_BAD_REQUEST)

        lead_list_name = request.data.get("lead_list_name") or None
        owner_user_id = request.data.get("owner_user_id") or None

        try:
            result = import_leads(
                upload,
                upload.name,
                lead_list_name=lead_list_name,
                owner_user_id=owner_user_id,
            )
            return Response(result, status=status.HTTP_200_OK)
        except ValueError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.error(f"Lead Upload Failed: {e}", exc_info=True)
            return Response({"error": "An unexpected error occurred during lead upload."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class LeadVerificationView(APIView):
    """
    POST /leads/verify/lead/
    Verifies a specific lead's email.
    Payload: { 
        "lead_id": "...",     
        "channel": "...",     
        "force": false 
    }
    """
    def post(self, request, lead_id=None):
        try:
            from .models import Lead
            from .services.verification_service import VerificationService
            from django.utils import timezone
            import datetime
            
            data = request.data
            
            # 1. Resolve Lead ID
            target_id = lead_id or data.get("lead_id")
            if not target_id:
                return Response({"error": "lead_id is required in URL or body"}, status=status.HTTP_400_BAD_REQUEST)

            channel = data.get("channel")
            
            # 2. Fetch Lead (Channel-Aware)
            lead = None
            if channel:
                 lead = Lead.objects.filter(third_party_org_id=target_id, channel=channel).first()
            
            if not lead:
                # Fallback Lookups
                lead = Lead.objects.filter(id=target_id).first()
                if not lead:
                    lead = Lead.objects.filter(third_party_org_id=target_id).first()
                if not lead and str(target_id).isdigit():
                     lead = Lead.objects.filter(id=int(target_id)).first()
            
            if not lead:
                return Response({"error": "Lead not found"}, status=status.HTTP_404_NOT_FOUND)
                
            if not lead.email:
                 # Check if we can get email from body? No, verification usually assumes lead has email.
                 # Unless we want to update email too? Assuming no for now.
                return Response({"error": "Lead has no email to verify"}, status=status.HTTP_400_BAD_REQUEST)

            # 3. Check Cache
            force = data.get("force", False)
            MIN_RECHECK_WINDOW = datetime.timedelta(hours=24)
            
            last_checked = getattr(lead, 'verification_last_checked_at', None)
            
            if not force and last_checked:
                is_recent = (timezone.now() - last_checked) < MIN_RECHECK_WINDOW
                if is_recent and lead.verification_status != 'unknown':
                     return Response({
                        "success": True,
                        "data": {
                            "mode": "cached",
                            "verification_status": lead.verification_status,
                            "verification_last_checked_at": last_checked
                        }
                    }, status=status.HTTP_200_OK)

            # 4. Perform Verification
            status_key, reason = VerificationService.verify_email_dns(lead.email)
            
            # 5. Update Lead
            lead.verification_status = status_key.lower()
            lead.verification_reason = reason
            lead.verification_last_checked_at = timezone.now()
            
            lead.save(update_fields=['verification_status', 'verification_reason', 'verification_last_checked_at', 'updated_at'])
            
            return Response({
                "success": True,
                "data": {
                    "mode": "live",
                    "verification_status": lead.verification_status,
                    "verification_reason": lead.verification_reason,
                    "verification_last_checked_at": lead.verification_last_checked_at
                }
            }, status=status.HTTP_200_OK)

        except Exception as e:
            logger.error(f"Lead Verification Failed: {e}", exc_info=True)
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class SearchRunResultsView(APIView):
    """
    GET /leads/search/runs/{run_id}/leads/
    Returns paginated leads for a specific search run.
    Query Params:
        page: int (default 1)
        page_size: int (default 10, max 100)
    """
    def get(self, request, run_id):
        try:
            from .models import SearchRun
            from django.forms.models import model_to_dict
            
            # 1. Fetch Search Run
            run = SearchRun.objects.filter(search_id=run_id).first()
            if not run:
                return Response({"error": "Search Run not found"}, status=status.HTTP_404_NOT_FOUND)
                
            # 2. Pagination Logic
            try:
                page = int(request.query_params.get('page', 1))
                page_size = int(request.query_params.get('page_size', 10))
            except ValueError:
                page = 1
                page_size = 10
                
            # Clamp page_size
            if page_size > 100: page_size = 100
            if page_size < 1: page_size = 10
            
            # 3. Query Leads
            # 3. Query Leads
            # Note: Using .order_by('search_run_leads__created_at') limits to insertion order (A, B, C) matches Search API.
            leads_qs = run.leads.all().order_by('search_run_leads__created_at')
            current_count = leads_qs.count()

            start = (page - 1) * page_size
            end = start + page_size

            # 4. Lazy Loading: If we need data beyond what we have, Fetch it!
            # E.g. Requesting 10-20, but we have 10.
            MAX_FETCHES = 3 # Safety break
            fetches = 0
            
            service = LeadService() # For lazy fetching

            gap_leads = []

            while current_count < end and fetches < MAX_FETCHES:
                # Trigger Fetch for Next Page
                next_page_sequential = (current_count // page_size) + 1
                
                # Gap Logic: If user asks for Page 5, but we only have Page 1, next_page_sequential is 2.
                # User wants to JUMP to 5.
                is_gap_fetch = False
                if page > next_page_sequential:
                    next_page_to_fetch = page
                    is_gap_fetch = True
                    logger.info(f"Lazy Loading: GAP DETECTED. Jumping to Page {page} (Skipping {next_page_sequential}-{page-1})...")
                else:
                    next_page_to_fetch = next_page_sequential
                    logger.info(f"Lazy Loading: Sequential. Need more leads for run {run_id}. Fetching Page {next_page_to_fetch}...")
                
                try:
                    fetch_filters = run.filters_json.copy() if run.filters_json else {}
                    fetch_filters["page"] = next_page_to_fetch
                    fetch_filters["per_page"] = page_size
                    fetch_filters["limit"] = page_size
                    
                    # Call Service to search (and append)
                    # Delegates to whatever lead-search provider LeadService has configured
                    search_results = service.search_people(fetch_filters, search_run_id=run.search_id)
                    
                    fetches += 1
                    
                    if is_gap_fetch:
                        # If we jumped, we CANNOT rely on leads_qs slicing (because of the index mismatch).
                        # We must capture the results directly from the service return.
                        gap_leads = search_results.get("people", [])
                        
                        # Update run count immediately from result to ensure accuracy
                        if "total_entries" in search_results:
                            run.lead_count = search_results["total_entries"]
                            run.save(update_fields=["lead_count"])
                        
                        # Break immediately, do not loop.
                        break

                    # Refresh to see if we got data (Standard Path)
                    leads_qs = run.leads.all().order_by('search_run_leads__created_at')
                    new_count = leads_qs.count()
                    
                    if new_count == current_count:
                        # API returned nothing new?
                        break
                        
                    current_count = new_count
                    
                    # Refresh Run to get updated total count logic if any
                    run.refresh_from_db()

                except Exception as e:
                    logger.error(f"Lazy Load Failed: {e}", exc_info=True)
                    break 

            total_count = run.lead_count # Use the TRUE total from the search provider (stored on Run)
            
            # Slicing
            start = (page - 1) * page_size
            end = start + page_size
            leads_page = leads_qs[start:end]
            
            # 4. Serialize (Match Search API Format)
            results = []
            
            if gap_leads:
                 # Use the directly fetched leads (Already formatted as dicts by LeadService)
                 results = gap_leads
            else:
                # Standard Slice & Serialize
                for l in leads_page:
                    # Reconstruct the unified search-result structure
                    p_item = {
                        "id": l.third_party_org_id or str(l.id),
                        "first_name": l.first_name,
                        "last_name": l.last_name, 
                        # "last_name_obfuscated": l.last_name, # Logic for obfuscation if needed
                        "title": l.title,
                        "organization": {
                            "name": l.company_name, 
                            "industry": l.industry,
                            "primary_domain": l.company_domain
                        },
                        "city": l.location,
                        "state": l.location, # approximation
                        "country": l.location, # approximation
                        "has_email": bool(l.email),
                        "has_direct_phone": bool(l.phone),
                        "has_city": bool(l.location),
                        "has_state": bool(l.location),
                        "has_country": bool(l.location),
                        "last_refreshed_at": l.updated_at,
                        # "is_revealed": l.is_revealed,
                        # "email": l.email if l.is_revealed else None,
                        # "phone_number": l.phone if l.is_revealed else None,
                        "lead_id": l.id,
                        "score": l.score,
                        "verification_status": l.verification_status,
                        "linkedin_url": l.linkedin_url
                    }
                    
                    # If company object linked, enrich further (match E12 struct)
                    if l.company:
                        p_item["organization"]["id"] = l.company.third_party_org_id
                        if l.company.domain: p_item["organization"]["primary_domain"] = l.company.domain
                        p_item["organization"]["has_industry"] = bool(l.company.industry)
                        p_item["organization"]["has_phone"] = False # Not currently stored on company model
                        p_item["organization"]["has_city"] = bool(l.company.hq_city)
                        p_item["organization"]["has_state"] = bool(l.company.hq_region)
                        p_item["organization"]["has_country"] = bool(l.company.hq_country)
                        p_item["organization"]["has_employee_count"] = bool(l.company.employees_min)
                    else:
                        # Defaults if no company linked
                        p_item["organization"]["has_industry"] = bool(l.industry)
                        p_item["organization"]["has_city"] = False

                    results.append(p_item)
            
            import math
            total_pages = math.ceil(total_count / page_size) if page_size > 0 else 1
                
            return Response({
                "run_id": run_id,
                "total_entries": total_count,
                "total_pages": total_pages,
                "page": page,
                "page_size": page_size,
                "people": results
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            logger.error(f"Search Results Fetch Failed: {e}", exc_info=True)
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

"""
E3: Filter Normalization & Options
"""
class FilterNormalizationView(APIView):
    """
    POST /leads/filters/normalize
    Standardizes filter inputs (locations, industries, etc.) using the canonical taxonomy.
    """
    def post(self, request):
        try:
            from .services.normalization_service import NormalizationService
            filters = request.data.get("filters", {})
            normalized = NormalizationService.normalize_filters(filters)
            return Response({"success": True, "data": normalized}, status=status.HTTP_200_OK)
        except Exception as e:
            logger.error(f"Filter Normalization Failed: {e}", exc_info=True)
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class FilterOptionsView(APIView):
    """
    GET /leads/filters/options
    Returns static taxonomy lists for frontend dropdowns.
    """
    def get(self, request):
        try:
            from .services.normalization_service import NormalizationService
            options = NormalizationService.get_options()
            return Response({"success": True, "data": options}, status=status.HTTP_200_OK)
        except Exception as e:
            logger.error(f"Filter Options Fetch Failed: {e}", exc_info=True)
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class LeadNoteView(APIView):
    """
    Unified Lead Note API
    GET /leads/{lead_id}/notes - List all notes
    POST /leads/{lead_id}/notes - Create a note
    GET /leads/{lead_id}/notes/{note_id} - Get single note
    PATCH /leads/{lead_id}/notes/{note_id} - Update a note
    DELETE /leads/{lead_id}/notes/{note_id} - Soft delete a note
    """
    def _get_lead(self, lead_id):
        from .models import Lead
        # 1. Try Third Party Org ID (most common external usage)
        lead = Lead.objects.filter(third_party_org_id=lead_id).first()
        if lead: return lead

        # 2. Try Third Party Org ID
        lead = Lead.objects.filter(third_party_org_id=lead_id).first()
        if lead: return lead

        # 3. Try Internal ID (if numeric)
        if str(lead_id).isdigit():
            lead = Lead.objects.filter(id=lead_id).first()
            if lead: return lead
            
        return None
    
    def _get_note(self, note_id, lead_id):
        from .models import LeadNote
        lead = self._get_lead(lead_id)
        if not lead:
            return None
            
        # Ensure note belongs to the resolved lead and is not deleted
        return LeadNote.objects.filter(id=note_id, lead=lead, is_deleted=False).first()

    def get(self, request, lead_id, note_id=None):
        try:
            from .models import LeadNote
            lead = self._get_lead(lead_id)
            if not lead:
                return Response({"error": "Lead not found"}, status=status.HTTP_404_NOT_FOUND)

            # Detail View
            if note_id:
                note = self._get_note(note_id, lead_id)
                if not note:
                    return Response({"error": "Note not found"}, status=status.HTTP_404_NOT_FOUND)
                
                data = {
                    "note_id": str(note.id),
                    "author_user_id": note.author_user_id,
                    "author_name": "Unknown",
                    "body": note.body,
                    "created_at": note.created_at,
                    "updated_at": note.updated_at
                }
                return Response({"success": True, "data": data}, status=status.HTTP_200_OK)

            # List View
            notes = LeadNote.objects.filter(lead=lead, is_deleted=False).order_by('-created_at')
            data = []
            for n in notes:
                data.append({
                    "note_id": str(n.id),
                    "author_user_id": n.author_user_id,
                    "author_name": "Unknown",
                    "body": n.body,
                    "created_at": n.created_at,
                    "updated_at": n.updated_at
                })
                
            return Response({"success": True, "data": data}, status=status.HTTP_200_OK)
        except Exception as e:
            logger.error(f"LeadNote GET Failed: {e}", exc_info=True)
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def post(self, request, lead_id):
        try:
            from .models import Lead, LeadNote
            
            body = request.data.get("body")
            if not body:
                return Response({"error": "body is required"}, status=status.HTTP_400_BAD_REQUEST)
                
            lead = self._get_lead(lead_id)
            if not lead:
                return Response({"error": "Lead not found"}, status=status.HTTP_404_NOT_FOUND)
            
            # Context Extraction
            author_id = "system" 
            if hasattr(request, "user") and request.user and hasattr(request.user, "id"):
                 author_id = str(request.user.id)
            
            # Org ID Extraction (if available in context)
            org_id = request.data.get("org_id") 
            # In realauth, this comes from request.user.org_id
            
            note = LeadNote.objects.create(
                lead=lead,
                body=body,
                author_user_id=org_id,
                org_id=org_id
            )
            
            return Response({
                "success": True, 
                "data": {
                    "note_id": str(note.id),
                    "created_at": note.created_at
                }
            }, status=status.HTTP_201_CREATED)
        except Exception as e:
            logger.error(f"Create Note Failed: {e}", exc_info=True)
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def patch(self, request, lead_id, note_id=None):
        if not note_id:
             return Response({"error": "note_id required for update"}, status=status.HTTP_400_BAD_REQUEST)
             
        try:
            note = self._get_note(note_id, lead_id)
            if not note:
                return Response({"error": "Note not found"}, status=status.HTTP_404_NOT_FOUND)

            body = request.data.get("body")
            if body:
                note.body = body
                note.save()
            
            return Response({
                "success": True, 
                "data": {
                    "note_id": str(note.id),
                    "body": note.body,
                    "updated_at": note.updated_at
                }
            }, status=status.HTTP_200_OK)

        except Exception as e:
            logger.error(f"Update Note Failed: {e}", exc_info=True)
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def delete(self, request, lead_id, note_id=None):
        if not note_id:
             return Response({"error": "note_id required for delete"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            note = self._get_note(note_id, lead_id)
            if not note:
                return Response({"error": "Note not found"}, status=status.HTTP_404_NOT_FOUND)

            # Soft Delete
            note.is_deleted = True
            note.save()
            
            return Response({"success": True, "message": "Note deleted"}, status=status.HTTP_200_OK)

        except Exception as e:
            logger.error(f"Delete Note Failed: {e}", exc_info=True)
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class LeadTimelineView(APIView):
    """
    GET /leads/{lead_id}/events - Get activity timeline
    Supports lead_id as Internal ID or Third Party Org ID.
    """
    def _get_lead(self, lead_id):
        from .models import Lead
        # 1. Try Third Party Org ID
        lead = Lead.objects.filter(third_party_org_id=lead_id).first()
        if lead: return lead

        # 2. Try Third Party Org ID
        lead = Lead.objects.filter(third_party_org_id=lead_id).first()
        if lead: return lead

        # 3. Try Internal ID (if numeric)
        if str(lead_id).isdigit():
            lead = Lead.objects.filter(id=lead_id).first()
            if lead: return lead
            
        return None

    def get(self, request, lead_id):
        try:
            from .models import LeadEvent
            lead = self._get_lead(lead_id)
            if not lead:
                return Response({"error": "Lead not found"}, status=status.HTTP_404_NOT_FOUND)

            events = LeadEvent.objects.filter(lead=lead).order_by('-timestamp')
            data = []
            for e in events:
                data.append({
                    "event_id": e.id,
                    "event_type": e.event_type,
                    "timestamp": e.timestamp,
                    "actor_user_id": e.actor_user_id,
                    "metadata": e.metadata
                })
            return Response({"success": True, "data": data}, status=status.HTTP_200_OK)
        except Exception as e:
            logger.error(f"Timeline Fetch Failed: {e}", exc_info=True)
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class MarkDuplicateView(APIView):
    """
    POST /leads/mark-duplicate
    Marks a lead as a duplicate of another primary lead.
    Payload: { "lead_id": "...", "primary_lead_id": "..." }
    """
    def _get_lead(self, lead_id):
        # reuse robust lookup logic
        try:
            from .models import Lead
            return Lead.objects.get(third_party_org_id=lead_id)
        except Lead.DoesNotExist:
            try:
                if lead_id.isdigit():
                    return Lead.objects.get(id=lead_id)
            except:
                pass
        return None

    def post(self, request):
        try:
            from .repositories.lead_repository import LeadRepository
            
            # 1. Resolve Duplicate Lead (Target)
            lead_id = request.data.get("lead_id")
            if not lead_id:
                return Response({"error": "lead_id is required"}, status=status.HTTP_400_BAD_REQUEST)

            duplicate_lead = self._get_lead(lead_id)
            if not duplicate_lead:
                return Response({"error": "Lead not found"}, status=status.HTTP_404_NOT_FOUND)

            # 2. Resolve Primary Lead
            primary_id_input = request.data.get("primary_lead_id")
            if not primary_id_input:
                return Response({"error": "primary_lead_id is required"}, status=status.HTTP_400_BAD_REQUEST)
            
            primary_lead = self._get_lead(primary_id_input)
            if not primary_lead:
                return Response({"error": "Primary lead not found"}, status=status.HTTP_404_NOT_FOUND)

            # 3. Validation
            if duplicate_lead.id == primary_lead.id:
                 return Response({"error": "Cannot mark lead as duplicate of itself"}, status=status.HTTP_400_BAD_REQUEST)

            org_id = request.data.get("org_id") # Use context from request

            # 4. Handle Dedupe Group
            group_id = primary_lead.dedupe_group_id
            if not group_id:
                group_id = f"dg_{uuid.uuid4().hex[:8]}"
                # Update Primary to be in this group
                primary_lead.dedupe_group_id = group_id
                if not primary_lead.dedupe_state or primary_lead.dedupe_state == 'original':
                    primary_lead.dedupe_state = 'primary'
                primary_lead.save()
                
                # Log event for primary
                LeadRepository.create_lead_event(
                    lead=primary_lead,
                    event_type="duplicate_added",
                    org_id=org_id,
                    metadata={"duplicate_lead_id": duplicate_lead.third_party_org_id or str(duplicate_lead.id)}
                )

            # 5. Update Duplicate Lead
            duplicate_lead.dedupe_state = 'duplicate'
            duplicate_lead.primary_lead_id = primary_lead.third_party_org_id or str(primary_lead.id) # Link via public ID preferably
            duplicate_lead.dedupe_group_id = group_id
            duplicate_lead.dedupe_score = request.data.get("confidence", 100) # Manual action implies 100%
            duplicate_lead.save()

            # 6. Log Event for Duplicate
            LeadRepository.create_lead_event(
                 lead=duplicate_lead,
                 event_type="marked_as_duplicate",
                 org_id=org_id,
                 metadata={
                     "primary_lead_id": primary_lead.third_party_org_id or str(primary_lead.id),
                     "reason": request.data.get("reason", "manual")
                 }
            )

            return Response({
                "success": True, 
                "data": {
                    "lead_id": duplicate_lead.third_party_org_id or str(duplicate_lead.id),
                    "primary_lead_id": primary_lead.third_party_org_id or str(primary_lead.id),
                    "dedupe_group_id": group_id
                }
            }, status=status.HTTP_200_OK)

        except Exception as e:
            logger.error(f"Mark Duplicate Failed: {e}", exc_info=True)
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class DedupeGroupView(APIView):
    """
    GET /leads/dedupe-groups/{group_id}/
    Returns details of a deduplication group (primary + duplicates).
    """
    def get(self, request, group_id):
        try:
            from .models import Lead
            
            # 1. Query Leads in Group
            leads = Lead.objects.filter(dedupe_group_id=group_id)
            if not leads.exists():
                return Response({"error": "Dedupe group not found"}, status=status.HTTP_404_NOT_FOUND)
            
            # 2. Identify Primary and format response
            primary_lead_id = None
            leads_data = []
            
            for lead in leads:
                # Determine primary
                if lead.dedupe_state == 'primary' or lead.dedupe_state == 'original':
                    primary_lead_id = lead.third_party_org_id or str(lead.id)
                
                # Format lead object
                leads_data.append({
                    "lead_id": lead.third_party_org_id or str(lead.id),
                    "dedupe_state": lead.dedupe_state,
                    "source": lead.primary_source or lead.channel or "unknown",
                    "score": lead.score,
                    "name": lead.person_full_name or f"{lead.first_name} {lead.last_name}".strip()
                })
            
            return Response({
                "success": True,
                "data": {
                    "dedupe_group_id": group_id,
                    "primary_lead_id": primary_lead_id,
                    "leads": leads_data
                }
            }, status=status.HTTP_200_OK)

        except Exception as e:
            logger.error(f"Dedupe Group Fetch Failed: {e}", exc_info=True)
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class BulkActionView(APIView):
    """
    POST /leads/bulk/actions/
    Unified endpoint for bulk operations on leads.
    Payload: 
    { 
        "lead_ids": ["id1", "id2"], 
        "action": "verify" | "score" | "delete" | "export_crm",
        "parameters": {} 
    }
    """
    def post(self, request):
        try:
            from .services.scoring_service import LeadScoringService
            from .services.verification_service import VerificationService
            from .models import Lead
            
            lead_ids = request.data.get("lead_ids", [])
            action = request.data.get("action")
            
            if not lead_ids or not action:
                 return Response({"error": "lead_ids and action are required"}, status=status.HTTP_400_BAD_REQUEST)

            # Limit to prevent timeout in synchronous mode
            MAX_BATCH = 100
            if len(lead_ids) > MAX_BATCH:
                 return Response({"error": f"Max {MAX_BATCH} leads per request."}, status=status.HTTP_400_BAD_REQUEST)

            # Resolve Leads (Internal ID or Third Party)
            leads = Lead.objects.filter(id__in=lead_ids)
            if not leads.exists():
                leads = Lead.objects.filter(third_party_org_id__in=lead_ids)
            
            results = []
            success_count = 0
            
            if action == "score":
                for lead in leads:
                    res = LeadScoringService.score_lead(lead)
                    results.append({"id": lead.id, "score": res.get("score"), "error": res.get("error")})
                    success_count += 1
                    
            elif action == "verify":
                for lead in leads:
                    if lead.email:
                        status_val, reason = VerificationService.verify_email_dns(lead.email)
                        lead.verification_status = status_val
                        lead.save()
                        results.append({"id": lead.id, "status": status_val, "reason": reason})
                        success_count += 1
                    else:
                        results.append({"id": lead.id, "error": "No email"})
                        
            elif action == "delete":
                # Bulk Delete
                count, _ = leads.delete()
                success_count = count
                results = [{"message": "Deleted"}]
            
            elif action == "export_crm":
                # Mock Export
                success_count = leads.count()
                results = [{"id": l.id, "crm_status": "queued"} for l in leads]
            
            else:
                 return Response({"error": f"Unknown action: {action}"}, status=status.HTTP_400_BAD_REQUEST)
                
            return Response({
                "success": True, 
                "message": f"Processed {success_count} items.", 
                "details": results
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            logger.error(f"Bulk Action Failed: {e}", exc_info=True)
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class CRMExportView(APIView):
    """
    POST /leads/{lead_id}/crm/push
    Push a single lead to CRM (Stub).
    """
    def post(self, request, lead_id):
        return Response({"success": True, "message": "Lead queued for CRM sync (Stub)"}, status=status.HTTP_200_OK)



class LeadMergeView(APIView):
    """
    POST /leads/merge
    Merges a source lead into a target lead.
    Payload: { "source_lead_id": "...", "target_lead_id": "...", "org_id": "..." }
    """
    def post(self, request):
        from .models import Lead # Local import to avoid circular dependency if LeadMergeService also imports Lead directly
        from .services.lead_merge_service import LeadMergeService

        source_lead_id = request.data.get("source_lead_id")
        target_lead_id = request.data.get("target_lead_id")
        org_id = request.data.get("org_id") # Optional: for event logging context

        if not source_lead_id or not target_lead_id:
            return Response(
                {"error": "Both source_lead_id and target_lead_id are required."},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            merged_lead = LeadMergeService.merge_leads(source_lead_id, target_lead_id, org_id)
            return Response(
                {
                    "success": True,
                    "message": f"Lead {source_lead_id} successfully merged into {target_lead_id}.",
                    "merged_lead_id": merged_lead.third_party_org_id
                },
                status=status.HTTP_200_OK
            )
        except ValueError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Lead.DoesNotExist as e:
            return Response({"error": str(e)}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            logger.error(f"Lead Merge Failed: {e}", exc_info=True)
            return Response({"error": "An unexpected error occurred during lead merge."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class CampaignClarificationView(APIView):
    """
    POST /ml/campaigns/clarify
    Analyze conversation to see if we have enough info to generate a campaign.
    """
    def post(self, request):
        try:
            data = request.data
            campaign_id = data.get("campaign_id")
            conversation = data.get("conversation", [])

            if not campaign_id or not conversation:
                return Response({"error": "campaign_id and conversation are required"}, status=status.HTTP_400_BAD_REQUEST)

            # service = CampaignService()
            # result = service.clarify_intent(campaign_id, conversation)
            result = _campaign_service.clarify_intent(campaign_id, conversation)

            return Response(result, status=status.HTTP_200_OK)

        except Exception as e:
            logger.error(f"Clarification API Error: {e}", exc_info=True)
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class CampaignGenerationView(APIView):
    """
    POST /ml/campaigns/generate
    Generate a linear campaign plan (Steps + Emails) based on context.
    """
    def post(self, request):
        try:
            data = request.data
            campaign_id = data.get("campaign_id")
            context = data.get("context", {})

            if not campaign_id or not context:
                return Response({"error": "campaign_id and context are required"}, status=status.HTTP_400_BAD_REQUEST)
            #
            # service = CampaignService()
            # result = service.generate_campaign(campaign_id, context)
            result = _campaign_service.generate_campaign(campaign_id, context)

            # Replace {{company_name}} / {{sender_name}} with real user data
            # and {{first_name}} / lead {{company_name}} with sample preview data
            from .services.template_replacer import TemplateReplacer
            user_context = TemplateReplacer.get_user_context(request.user)
            for step in result.get("steps", []):
                email = step.get("email", {})
                if email:
                    replaced = TemplateReplacer.replace_email_content(
                        email.get("subject", ""), email.get("body", ""), request.user, preview_mode=True
                    )
                    email["subject"] = replaced["subject"]
                    email["body"] = replaced["body"]

            return Response(result, status=status.HTTP_200_OK)

        except Exception as e:
            logger.error(f"Generation API Error: {e}", exc_info=True)
            return Response({"error": "Campaign generation failed. Please try again."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class EmailGenerationView(APIView):
    """
    POST /ml/emails/generate/
    Generate a specific email draft (Subject + Body) based on instructions.
    """
    def post(self, request):
        try:
            data = request.data
            campaign_context = data.get("campaign_context", {})
            step_context = data.get("step_context", {})
            instructions = data.get("instructions", "")
            template_id = data.get("template_id")

            if not instructions:
                return Response({"error": "instructions are required"}, status=status.HTTP_400_BAD_REQUEST)

            result = _campaign_service.generate_email_draft(campaign_context, step_context, instructions, template_id=template_id)

            # Replace {{company_name}} / {{sender_name}} with real user data
            # and {{first_name}} / lead {{company_name}} with sample preview data
            from .services.template_replacer import TemplateReplacer
            replaced = TemplateReplacer.replace_email_content(
                result.get("subject", ""), result.get("body", ""), request.user, preview_mode=True
            )
            result["subject"] = replaced["subject"]
            result["body"] = replaced["body"]

            return Response(result, status=status.HTTP_200_OK)

        except Exception as e:
            logger.error(f"Email Generation API Error: {e}", exc_info=True)
            return Response({"error": "Email generation failed. Please try again."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class EmailSpamAnalysisView(APIView):
    """
    POST /ml/emails/spam-analysis/
    Analyze an email for spam risk and provide recommendations.
    """
    def post(self, request):
        try:
            data = request.data or {}
            email = data.get("email", {})

            subject = email.get("subject", "")
            body = email.get("body", "")

            if not subject and not body:
                return Response(
                    {"error": "Either email.subject or email.body must be provided"},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            email_id = email.get("id") # Optional, but needed for saving if model requires it
            #
            # service = CampaignService()
            # result = service.analyze_spam_risk(subject, body, email_id)
            result = _campaign_service.analyze_spam_risk(subject, body, email_id)
            return Response(result, status=status.HTTP_200_OK)

        except Exception as e:
            logger.error(f"Spam Analysis API Error: {e}", exc_info=True)
            return Response(
                {"error": "Internal server error"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class CampaignReplyGenerationView(APIView):
    """
    POST /ml/emails/reply/
    Generate an AI reply to a prospect's response to a campaign email.
    """
    def post(self, request):
        try:
            data = request.data or {}
            original_email = data.get("original_email", {})
            prospect_reply = data.get("prospect_reply", "")
            campaign_context = data.get("campaign_context", {})
            lead_info = data.get("lead_info", {})
            tone = data.get("tone", "professional")
            instructions = data.get("instructions", "")

            if not prospect_reply:
                return Response(
                    {"error": "prospect_reply is required"},
                    status=status.HTTP_400_BAD_REQUEST
                )
            if not original_email.get("subject") and not original_email.get("body"):
                return Response(
                    {"error": "original_email (subject or body) is required"},
                    status=status.HTTP_400_BAD_REQUEST
                )

            result = _campaign_service.generate_reply(
                original_email=original_email,
                prospect_reply=prospect_reply,
                campaign_context=campaign_context,
                lead_info=lead_info,
                tone=tone,
                instructions=instructions,
            )
            return Response(result, status=status.HTTP_200_OK)

        except Exception as e:
            logger.error(f"Reply Generation API Error: {e}", exc_info=True)
            return Response(
                {"error": "Internal server error"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

class ReplyUnderstandingView(APIView):
    """
    POST /ml/emails/reply/understand/
    Uses LLM to interpret the meaning and intent of a prospect's reply beyond keyword matching.
    """
    def post(self, request):
        try:
            data = request.data or {}
            prospect_reply = data.get("prospect_reply", "")

            if not prospect_reply:
                return Response(
                    {"error": "prospect_reply is required"},
                    status=status.HTTP_400_BAD_REQUEST
                )

            result = _campaign_service.understand_reply(
                prospect_reply=prospect_reply,
                original_email=data.get("original_email"),
                campaign_context=data.get("campaign_context"),
                lead_info=data.get("lead_info"),
            )
            return Response(result, status=status.HTTP_200_OK)

        except Exception as e:
            logger.error(f"Reply Understanding API Error: {e}", exc_info=True)
            return Response(
                {"error": "Internal server error"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class SubjectLineGenerationView(APIView):
    """
    POST /api/ml/emails/subject/
    Generate a single AI subject line from campaign context + lead attributes.
    Returns: {"subject": "..."}
    """
    def post(self, request):
        try:
            data = request.data or {}
            campaign_context = data.get("campaign_context", {})
            lead_attributes = data.get("lead_attributes", {})
            instructions = data.get("instructions", "")
            template_id = data.get("template_id")

            subject = _campaign_service.generate_subject_line(
                campaign_context=campaign_context,
                lead_attributes=lead_attributes,
                instructions=instructions,
                template_id=template_id,
            )
            return Response({"subject": subject}, status=status.HTTP_200_OK)

        except Exception as e:
            logger.error(f"Subject Line Generation API Error: {e}", exc_info=True)
            return Response({"error": "Subject line generation failed. Please try again."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class AIInsightsView(APIView):
    """
    GET /api/ml/insights/
    Returns AI insights scoped to the authenticated user's account.
    Staff may override with ?org_id=<id>.
    """

    def get(self, request):
        try:
            from .services.ai_insights_service import AIInsightsService
            from authentication.models import Organization

            # ── Resolve authenticated user ────────────────────────────────
            user = getattr(request, 'user', None)
            if not (user and getattr(user, 'is_authenticated', False)):
                user = None

            # org_id: staff can override via query param; everyone else gets
            # their own account automatically
            org_id = request.query_params.get("org_id")
            user_id = None
            user_info = {}
            account_info = {}

            if user:
                user_id = str(user.id)
                if not org_id:
                    org_id = user.account_id  # scope to this user's account

                user_info = {
                    "id": str(user.id),
                    "email": user.email,
                    "first_name": user.first_name or "",
                    "last_name": user.last_name or "",
                    "full_name": (f"{user.first_name or ''} {user.last_name or ''}".strip()
                                  or user.email),
                    "role": getattr(user, 'role', ""),
                }

                if org_id:
                    try:
                        org = Organization.objects.get(id=org_id)
                        account_info = {"id": str(org.id), "name": org.name or org_id}
                    except Organization.DoesNotExist:
                        account_info = {"id": org_id, "name": org_id}

            data = AIInsightsService.get_insights(org_id=org_id, user_id=user_id)
            data["user_info"] = user_info
            data["account_info"] = account_info
            return Response(data, status=status.HTTP_200_OK)

        except Exception as e:
            logger.error(f"AI Insights API Error: {e}", exc_info=True)
            return Response({"error": "Failed to load AI insights. Please try again."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ---------------------------------------------------------------------------
# AI Context Builder
# ---------------------------------------------------------------------------

class AIContextBuildView(APIView):
    """
    POST /ai/context/build
    Renders a prompt template with lead + campaign data.
    Body: { "template_id": "...", "lead_data": {}, "campaign_context": {}, "step_context": {} }
    Returns: { "rendered_prompt": "...", "template_id", "model_name", "temperature", "max_tokens" }
    """
    def post(self, request):
        from .services.ai_prompt_template_service import AIPromptTemplateService
        data = request.data or {}
        template_id = data.get("template_id")
        if not template_id:
            return Response({"error": "template_id is required"}, status=status.HTTP_400_BAD_REQUEST)

        merged = {}
        merged.update(data.get("campaign_context") or {})
        merged.update(data.get("step_context") or {})
        merged.update(data.get("lead_data") or {})

        result = AIPromptTemplateService.build_context(template_id, merged)
        if not result:
            return Response({"error": "template not found"}, status=status.HTTP_404_NOT_FOUND)
        return Response(result, status=status.HTTP_200_OK)


# ---------------------------------------------------------------------------
# AI Prompt Templates
# ---------------------------------------------------------------------------

class AIPromptTemplateListView(APIView):
    """
    GET  /ai/prompt-templates/   — list (filter: org_id, category)
    POST /ai/prompt-templates/   — create
    """

    def get(self, request):
        from .services.ai_prompt_template_service import AIPromptTemplateService
        org_id   = request.query_params.get("org_id")
        category = request.query_params.get("category")
        data = AIPromptTemplateService.list_templates(org_id=org_id, category=category)
        return Response(data, status=status.HTTP_200_OK)

    def post(self, request):
        from .services.ai_prompt_template_service import AIPromptTemplateService
        try:
            data = AIPromptTemplateService.create_template(request.data)
            return Response(data, status=status.HTTP_201_CREATED)
        except ValueError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


class AIPromptTemplateDetailView(APIView):
    """
    GET    /ai/prompt-templates/<id>/  — retrieve
    PUT    /ai/prompt-templates/<id>/  — update (non-default only)
    DELETE /ai/prompt-templates/<id>/  — soft-delete (non-default only)
    """

    def get(self, request, template_id):
        from .services.ai_prompt_template_service import AIPromptTemplateService
        t = AIPromptTemplateService.get_template(template_id)
        if not t:
            return Response({"error": "Not found"}, status=status.HTTP_404_NOT_FOUND)
        return Response(AIPromptTemplateService.serialize_template(t))

    def put(self, request, template_id):
        from .services.ai_prompt_template_service import AIPromptTemplateService
        t = AIPromptTemplateService.get_template(template_id)
        if not t:
            return Response({"error": "Not found"}, status=status.HTTP_404_NOT_FOUND)
        if t.is_default:
            return Response({"error": "System defaults cannot be modified"}, status=status.HTTP_403_FORBIDDEN)
        try:
            data = AIPromptTemplateService.update_template(t, request.data)
            return Response(data)
        except ValueError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, template_id):
        from .services.ai_prompt_template_service import AIPromptTemplateService
        t = AIPromptTemplateService.get_template(template_id)
        if not t:
            return Response({"error": "Not found"}, status=status.HTTP_404_NOT_FOUND)
        if t.is_default:
            return Response({"error": "System defaults cannot be deleted"}, status=status.HTTP_403_FORBIDDEN)
        AIPromptTemplateService.delete_template(t)
        return Response({"message": "Template deleted"}, status=status.HTTP_200_OK)


class AIPromptTemplateVersionsView(APIView):
    """
    GET /ai/prompt-templates/<id>/versions/  — list all saved versions
    """

    def get(self, request, template_id):
        from .services.ai_prompt_template_service import AIPromptTemplateService
        data = AIPromptTemplateService.list_versions(template_id)
        if data is None:
            return Response({"error": "Not found"}, status=status.HTTP_404_NOT_FOUND)
        return Response(data, status=status.HTTP_200_OK)


class AIPromptTemplateRollbackView(APIView):
    """
    POST /ai/prompt-templates/<id>/rollback/
    Body: {"version_number": <int>}
    Restores the template to the given version; saves current state as a new version first.
    """

    def post(self, request, template_id):
        from .services.ai_prompt_template_service import AIPromptTemplateService
        version_number = request.data.get("version_number")
        if version_number is None:
            return Response({"error": "version_number is required"}, status=status.HTTP_400_BAD_REQUEST)
        try:
            version_number = int(version_number)
        except (TypeError, ValueError):
            return Response({"error": "version_number must be an integer"}, status=status.HTTP_400_BAD_REQUEST)

        data, err = AIPromptTemplateService.rollback_template(template_id, version_number)
        if err == "template_not_found":
            return Response({"error": "Template not found"}, status=status.HTTP_404_NOT_FOUND)
        if err == "version_not_found":
            return Response({"error": f"Version {version_number} not found"}, status=status.HTTP_404_NOT_FOUND)
        return Response(data, status=status.HTTP_200_OK)


class ContextualFollowUpView(APIView):
    """
    POST /ml/emails/contextual-followup/
    Generate a context-aware follow-up email using the full thread history passed inline.
    The LLM sees every prior outbound email and inbound reply so it never repeats
    itself and can address any prospect objections.

    Payload:
        {
            "thread_messages": [
                {"direction": "outbound", "subject": "...", "body": "...", "sent_at": "2024-01-01T10:00:00"},
                {"direction": "inbound",  "body": "Not interested right now", "sent_at": "2024-01-02T09:00:00"}
            ],
            "campaign_context": {"goal": "Book demos", "value_proposition": "..."},
            "lead_info": {"first_name": "John", "company_name": "Acme"},
            "tone": "professional",
            "instructions": "Reference their previous objection about timing"
        }

    Response:
        {
            "subject": "Re: Quick follow up",
            "body": "<email body>",
            "reasoning": "Prospect said not interested — used a softer re-engagement angle"
        }
    """

    def post(self, request):
        data = request.data
        thread_messages = data.get("thread_messages", [])
        campaign_context = data.get("campaign_context", {})
        lead_info = data.get("lead_info", {})
        tone = data.get("tone", "professional")
        instructions = data.get("instructions", "")

        if not thread_messages:
            return Response({"error": "thread_messages is required and cannot be empty"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            result = _campaign_service.generate_contextual_followup(
                thread_messages=thread_messages,
                campaign_context=campaign_context,
                lead_info=lead_info,
                tone=tone,
                instructions=instructions,
            )
            return Response(result, status=status.HTTP_200_OK)
        except ValueError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.error(f"ContextualFollowUpView error: {e}", exc_info=True)
            return Response({"error": "Follow-up generation failed. Please try again."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class SendCampaignEmailView(APIView):
    """
    POST /api/campaigns/send-email/
    Send a generated campaign email via Gmail.
    Body: { "to_email": "...", "subject": "...", "body": "..." }
    Bulk: { "recipients": ["a@x.com", "b@x.com"], "subject": "...", "body": "..." }
    """
    def post(self, request):
        from .services.gmail_service import GmailService
        data = request.data
        subject = data.get("subject", "").strip()
        body    = data.get("body", "").strip()

        if not subject or not body:
            return Response({"error": "subject and body are required"}, status=status.HTTP_400_BAD_REQUEST)

        # Replace {{company_name}} / {{sender_name}} with real user data before sending
        from .services.template_replacer import TemplateReplacer
        replaced = TemplateReplacer.replace_email_content(subject, body, request.user)
        subject = replaced["subject"]
        body = replaced["body"]

        gmail = GmailService()
        recipients = data.get("recipients")
        if recipients:
            result = gmail.send_bulk(recipients, subject, body)
            return Response(result, status=status.HTTP_200_OK)

        to_email = data.get("to_email", "").strip()
        if not to_email:
            return Response({"error": "to_email or recipients is required"}, status=status.HTTP_400_BAD_REQUEST)

        result = gmail.send_email(to_email, subject, body)
        if result.get("success"):
            return Response({"success": True, "message": f"Email sent to {to_email}"}, status=status.HTTP_200_OK)
        return Response({"success": False, "error": result.get("error")}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class SendToLeadsView(APIView):
    """
    POST /api/campaigns/send-to-leads/
    Sends a campaign step to all leads in the campaign's lead list.
    Creates CampaignLeadStatus records and SentEmail tracking.
    If step_order == 1, this enrolls leads and sends Step 1.
    Also activates the campaign for auto follow-ups.

    Body: {
        "campaign_id": "uuid",
        "step_order": 1,       # which step to send now
        "test_mode": false
    }
    """

    def post(self, request):
        import time
        from .models import (
            Campaign, CampaignStep, CampaignEmail, CampaignLeadStatus,
            SentEmail, Lead, LeadList
        )
        from .services.template_replacer import TemplateReplacer

        data = request.data
        campaign_id = data.get("campaign_id")
        step_order = int(data.get("step_order", 1))

        if not campaign_id:
            return Response({"error": "campaign_id is required"}, status=status.HTTP_400_BAD_REQUEST)

        # ── Load campaign ──
        try:
            campaign = Campaign.objects.get(id=campaign_id)
        except Campaign.DoesNotExist:
            return Response({"error": "Campaign not found"}, status=status.HTTP_404_NOT_FOUND)

        # ── Load step + email template ──
        try:
            step = CampaignStep.objects.get(campaign=campaign, step_order=step_order)
            campaign_email = step.email  # OneToOne reverse
        except CampaignStep.DoesNotExist:
            return Response({"error": f"Step {step_order} not found"}, status=status.HTTP_404_NOT_FOUND)
        except CampaignEmail.DoesNotExist:
            return Response({"error": f"Step {step_order} has no email template"}, status=status.HTTP_404_NOT_FOUND)

        if not campaign_email.subject or not campaign_email.body:
            return Response({"error": "Email template has empty subject or body"}, status=status.HTTP_400_BAD_REQUEST)

        # ── Get leads ──
        leads = []
        if campaign.lead_list_id:
            try:
                lead_list = LeadList.objects.get(id=campaign.lead_list_id)
                leads = list(Lead.objects.filter(lead_list=lead_list, email__isnull=False).exclude(email=''))
            except (LeadList.DoesNotExist, ValueError):
                # lead_list_id might be a search_run_id or session-based
                pass

        # Fallback: try to get leads from the session's search
        if not leads:
            session_id = data.get("session_id")
            if session_id:
                from .models import PeopleSearch
                try:
                    search = PeopleSearch.objects.filter(
                        session__session_id=session_id
                    ).order_by('-created_at').first()
                    if search:
                        leads = list(search.leads.filter(email__isnull=False).exclude(email=''))
                except Exception:
                    pass

        if not leads:
            return Response({"error": "No leads found for this campaign"}, status=status.HTTP_400_BAD_REQUEST)

        # ── Get sender ──
        sender_service = None
        sender_email = None

        # Try OAuth first
        try:
            from .services.gmail_oauth_service import GmailOAuthService
            oauth = GmailOAuthService(request.user)
            if oauth.is_connected():
                sender_service = oauth
                sender_email = oauth._token.gmail_address
        except Exception:
            pass

        # Fallback to SMTP
        if not sender_service:
            try:
                from .services.gmail_service import GmailService
                from django.conf import settings
                smtp_email = getattr(settings, 'GMAIL_USER', '')
                if smtp_email:
                    sender_service = GmailService()
                    sender_email = smtp_email
            except Exception:
                pass

        if not sender_service:
            return Response({"error": "No email sender configured. Connect Gmail or set SMTP credentials."},
                            status=status.HTTP_400_BAD_REQUEST)

        # ── Send to each lead ──
        sent_count = 0
        failed_count = 0
        failed_details = []

        for lead in leads:
            # Skip if already sent this step to this lead
            existing = CampaignLeadStatus.objects.filter(
                campaign=campaign,
                lead=lead,
                last_step_sent__gte=step_order
            ).exists()
            if existing:
                continue

            # Replace placeholders per lead
            replaced = TemplateReplacer.replace_email_content(
                campaign_email.subject, campaign_email.body, request.user, lead
            )

            try:
                result = sender_service.send_email(lead.email, replaced['subject'], replaced['body'])

                if result.get('success'):
                    lead_name = f"{lead.first_name or ''} {lead.last_name or ''}".strip()

                    # Create SentEmail record
                    sent_record = SentEmail.objects.create(
                        campaign_id=str(campaign.id),
                        step_order=step_order,
                        recipient_email=lead.email,
                        recipient_name=lead_name,
                        subject=replaced['subject'],
                        body=replaced['body'],
                        sent_from=sender_email,
                        status='sent',
                    )

                    # Create or update CampaignLeadStatus
                    from django.utils import timezone as tz
                    total_steps = CampaignStep.objects.filter(campaign=campaign).count()
                    new_status = 'completed' if step_order >= total_steps else 'in_sequence'

                    CampaignLeadStatus.objects.update_or_create(
                        campaign=campaign,
                        lead=lead,
                        defaults={
                            'last_step_sent': step_order,
                            'last_sent_at': tz.now(),
                            'last_sent_email': sent_record,
                            'status': new_status,
                        }
                    )

                    sent_count += 1
                    time.sleep(0.5)  # Rate limit
                else:
                    failed_count += 1
                    failed_details.append({"email": lead.email, "error": result.get("error")})

            except Exception as e:
                failed_count += 1
                failed_details.append({"email": lead.email, "error": str(e)})
                logger.error(f"SendToLeadsView: Failed to send to {lead.email}: {e}")

        # ── Activate campaign for auto follow-ups ──
        if sent_count > 0 and campaign.status in ('approved', 'ai_generated', 'draft'):
            campaign.status = 'active'
            campaign.save(update_fields=['status', 'updated_at'])

        return Response({
            "success": True,
            "sent_count": sent_count,
            "failed_count": failed_count,
            "total_leads": len(leads),
            "sent_from": sender_email,
            "failed_details": failed_details[:10],  # Limit response size
        }, status=status.HTTP_200_OK)


class TestCampaignStepView(APIView):
    """
    POST /api/campaigns/test-step/
    Sends a single campaign step email to a test address (no lead tracking).
    Body: { "campaign_id": "uuid", "step_order": 1, "test_email": "you@example.com" }
    """

    def post(self, request):
        from .models import Campaign, CampaignStep, CampaignEmail
        from .services.template_replacer import TemplateReplacer

        data = request.data
        campaign_id = data.get("campaign_id")
        step_order = int(data.get("step_order", 1))
        test_email = data.get("test_email", "").strip()

        if not campaign_id or not test_email:
            return Response({"error": "campaign_id and test_email are required"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            campaign = Campaign.objects.get(id=campaign_id)
            step = CampaignStep.objects.get(campaign=campaign, step_order=step_order)
            campaign_email = step.email
        except (Campaign.DoesNotExist, CampaignStep.DoesNotExist, CampaignEmail.DoesNotExist):
            return Response({"error": f"Campaign or step {step_order} not found"}, status=status.HTTP_404_NOT_FOUND)

        if not campaign_email.subject or not campaign_email.body:
            return Response({"error": "Email template is empty"}, status=status.HTTP_400_BAD_REQUEST)

        # Replace placeholders with preview data (no real lead)
        replaced = TemplateReplacer.replace_email_content(
            campaign_email.subject, campaign_email.body, request.user, None, preview_mode=True
        )

        # Get sender
        sender_service = None
        sender_email = None

        try:
            from .services.gmail_oauth_service import GmailOAuthService
            oauth = GmailOAuthService(request.user)
            if oauth.is_connected():
                sender_service = oauth
                sender_email = oauth._token.gmail_address
        except Exception:
            pass

        if not sender_service:
            try:
                from .services.gmail_service import GmailService
                from django.conf import settings
                smtp_email = getattr(settings, 'GMAIL_USER', '')
                if smtp_email:
                    sender_service = GmailService()
                    sender_email = smtp_email
            except Exception:
                pass

        if not sender_service:
            return Response({"error": "No email sender configured"}, status=status.HTTP_400_BAD_REQUEST)

        result = sender_service.send_email(test_email, replaced['subject'], replaced['body'])

        if result.get('success'):
            return Response({
                "success": True,
                "step_order": step_order,
                "sent_to": test_email,
                "sent_from": sender_email,
            }, status=status.HTTP_200_OK)

        return Response({"success": False, "error": result.get("error")}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)