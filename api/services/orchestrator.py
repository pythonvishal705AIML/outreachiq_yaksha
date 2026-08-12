# import logging
# from .intent_classifier import IntentClassifier
# from .chit_chat_handler import BrandChitChatHandler
# from ..models import BusinessProfile
# from .lead_extractor import LeadParameterExtractor

# LEAD_SEARCH_FLOW = "lead_search"
# CAMPAIGN_FLOW = "campaign_flow"
# COLLECTING_INFO = "collecting_info"
# CONFIRM_SEARCH_PARAMS = "confirm_search_params"

# from django.forms.models import model_to_dict

# logger = logging.getLogger(__name__)

# class ConversationOrchestrator:
#     def __init__(self, session):
#         self.session = session
#         self.state = session.state or {}

#         self.intent_classifier = IntentClassifier()
#         # Try to fetch tenant profile for dynamic brand name
#         try:
#             profile = BusinessProfile.objects.get(account_id=session.tenant_id)
#             brand_name = profile.name if profile.name else "Your Assistant"
#             # Get tone from JSON field
#             brand_tone = profile.tone_preferences if profile.tone_preferences else "friendly"
#         except BusinessProfile.DoesNotExist:
#             brand_name = "Your Assistant"
#             brand_tone = "friendly"

#         self.chit_chat_handler = BrandChitChatHandler(
#             brand_name=brand_name,
#             brand_tone=brand_tone
#         )
#         self.extractor = LeadParameterExtractor()

#     # ---------- HELPER METHODS ----------
#     def _save_state(self):
#         self.session.state = self.state
#         self.session.save()

#     def _get_future_flows(self, current_flow: str, step: str) -> list:
#         """
#         Determines the likely next steps in the end-to-end business process.
#         Returns full API URLs using the SQUIBB_DOMAIN_URL from settings.
#         """
#         from django.conf import settings
        
#         domain_url = getattr(settings, 'SQUIBB_DOMAIN_URL', 'https://test-ai.squibb.ai')
        
#         # Mapping of flow names to their API paths
#         flow_url_mapping = {
#             "people_search_api": "/api/leads/search/people/",
#             "people_reveal_api": "/api/leads/reveal/people/",
#             "campaign": "/api/ml/campaigns/generate/",
#             "campaign_generate": "/api/ml/campaigns/generate/",
#             "lead_search": "/api/leads/search/people/",
#         }
        
#         future = []
        
#         if current_flow == LEAD_SEARCH_FLOW:
#             if step == CONFIRM_SEARCH_PARAMS:
#                 future.append("people_search_api")
#             else:
#                 # Still in progress
#                 future.append("people_search_api") # Eventually we get here
                
#         elif current_flow == "people_search_api":
#             future.append("people_reveal_api")
            
#         elif current_flow == "people_reveal_api":
#             future.append("campaign") # Hypothetical next step
        
#         elif current_flow == CAMPAIGN_FLOW:
#             # When in campaign flow, suggest campaign generation
#             if step == "ready_for_generation":
#                 future.append("campaign_generate")
#             else:
#                 # Still clarifying
#                 future.append("campaign_generate")

#         # Check based on past flows if current is empty
#         if not current_flow:
#             past = self.state.get("past_flows", [])
            
#             # Find last "meaningful" flow (ignore chit_chat)
#             last_meaningful = None
#             for flow_name in reversed(past):
#                 if flow_name != "chit_chat":
#                     last_meaningful = flow_name
#                     break
            
#             if last_meaningful == "people_search_api":
#                  future.append("people_reveal_api")
#             elif last_meaningful == "people_reveal_api":
#                  future.append("campaign")
#             else:
#                  # Default: If we have started chatting (messages exist), suggest lead_search.
#                  # If session is brand new (no messages), keep it empty.
#                  if self.session.messages.exists():
#                      future.append("lead_search")

#         # Convert flow names to full URLs
#         future_with_urls = []
#         for flow_name in future:
#             url_path = flow_url_mapping.get(flow_name, f"/api/{flow_name}/")
#             full_url = f"{domain_url}{url_path}"
#             future_with_urls.append({
#                 "flow": flow_name,
#                 "url": full_url
#             })
        
#         return future_with_urls

#     def transition_flow(self, new_flow: str):
#         """
#         Explicitly transitions the state to a new flow (e.g. triggered by an external API call).
#         Returns the new flow status.
#         """
#         current = self.state.get("flow")
        
#         # Only archive if it's a different flow and not just a re-run
#         if current and current != new_flow:
#             past = self.state.get("past_flows", [])
            
#             # Prevent consecutive duplicates
#             if not past or past[-1] != current:
#                 past.append(current)
#                 self.state["past_flows"] = past
        
#         self.state["flow"] = new_flow
#         self.state["step"] = "executed" 
#         self._save_state()
        
#         return self._get_flow_status()

#     def _get_flow_status(self) -> dict:
#         current_flow = self.state.get("flow")
#         step = self.state.get("step")
#         past_flows = self.state.get("past_flows", [])
#         future_flows = self._get_future_flows(current_flow, step)
        
#         return {
#             "current_flow": current_flow,
#             "past_flows": past_flows,
#             "future_flows": future_flows
#         }

#     # ---------- PUBLIC ENTRY POINT ----------
#     def handle_message(self, user_text: str) -> dict:
#         logger.info(f"Orchestrator: Handle Message. Session={self.session.session_id}, State={self.state}")
        
#         # Load history
#         self.history = [
#             {"role": msg.role, "content": msg.text}
#             for msg in self.session.messages.order_by("timestamp")
#         ]
        
#         # Limit context
#         if len(self.history) > 10:
#             self.history = self.history[-10:]

#         # 1. Classify Intent (Check for global commands/chitchat)
#         classification = self.intent_classifier.classify(self.history)
#         intent = classification.get("general_intent")
#         logger.info(f"Orchestrator: Classified Intent='{intent}'")

#         # 2. Global Handlers (High Priority)
#         if intent == "chit_chat":
#             # If explicit chit-chat is detected, respond and DO NOT change flow state
#             # This allows "interruption" without losing context
#             logger.info("Orchestrator: Handling Chit Chat (Interruption or Start)")
#             reply_text = self.chit_chat_handler.respond(user_text, history=self.history)
            
#             response = {
#                 "text": reply_text,
#                 "state": self.state # Preserve existing state
#             }
            
#             # 1. Get Status based on PRE-saved state
#             status = self._get_flow_status()
            
#             # Filter redundant 'chit_chat' from past_flows for display if we are currently in chit_chat
#             display_past = status["past_flows"][:]
#             if display_past and display_past[-1] == "chit_chat":
#                 display_past.pop()
            
#             # If we are interrupting a flow (e.g. lead_search), add it to past_flows for visibility
#             background_flow = self.state.get("flow")
#             if background_flow:
#                  if not display_past or display_past[-1] != background_flow:
#                     display_past.append(background_flow)
            
#             status["past_flows"] = display_past
#             status["current_flow"] = "chit_chat" # Visual override
            
#             # 2. Update Past Flows (for NEXT turn)
#             past = self.state.get("past_flows", [])
#             if not past or past[-1] != "chit_chat":
#                 past.append("chit_chat")
#                 self.state["past_flows"] = past
#                 self._save_state()
            
#             # 3. Return response with Clean status
#             response.update(status)
#             return response

#         # 3. Flow Routing
#         active_flow = self.state.get("flow")

#         # IMPORTANT: If already in a multi-turn flow (campaign or lead_search), 
#         # continue that flow unless explicitly starting something new.
#         # This prevents campaign answers like "I want to target SaaS CTOs" from 
#         # being misclassified as lead_search.
        
#         if active_flow == CAMPAIGN_FLOW:
#             # User is in campaign flow - continue with campaign regardless of detected intent
#             # (unless they explicitly say "create campaign" which would just continue anyway)
#             logger.info(f"Orchestrator: Continuing active campaign flow")
#             return self._route_active_flow(user_text)
        
#         if intent == "lead_search":
#             # User explicitly wants to search. 
#             # If already in search, continue. If not, start new.
#             if active_flow != LEAD_SEARCH_FLOW:
#                  return self.start_lead_search(user_text)
#             # If already in lead search, let it flow through to _handle_lead_search 
#             # (which might treat this as a refinement)
        
#         if intent == "create_campaign":
#             if active_flow != CAMPAIGN_FLOW:
#                 return self.start_campaign_flow(user_text)
#             # Else fall through to route_active_flow

#         # 4. Active Flow Processing
#         if active_flow:
#             logger.info(f"Orchestrator: Routing to active flow '{active_flow}'.")
#             return self._route_active_flow(user_text)

#         # 5. Fallback (No flow, no clear intent, or unknown)
#         return self._handle_no_active_flow(intent, user_text)

#     # ---------- FLOW ROUTING ----------
#     def _handle_no_active_flow(self, intent: str, user_text: str) -> dict:
#         # If we reached here, intent wasn't chit_chat (handled above).
#         # And it wasn't lead_search (handled above or below).
        
#         # Double check just in case logic slips
#         if intent == "lead_search":
#              return self.start_lead_search(user_text)

#         msg = "I’m not fully sure what you want yet — can you tell me what you’d like to do? I can help you find leads or companies."
        
#         response = {
#             "text": msg,
#             "state": self.state
#         }
#         response.update(self._get_flow_status())
#         return response

#     def _route_active_flow(self, user_text: str) -> dict:
#         flow = self.state.get("flow")
        
#         if flow == LEAD_SEARCH_FLOW:
#             return self._handle_lead_search(user_text)
            
#         if flow == CAMPAIGN_FLOW:
#             return self._handle_campaign_flow(user_text)

#         # Should not happen if flow is valid, but safe fallback
#         response = {
#             "text": "I’m currently in a task but got lost. Let's start over.",
#             "state": {} 
#         }
#         response.update(self._get_flow_status())
#         return response

#     # ---------- FLOW LOGIC ----------
#     def start_lead_search(self, user_text: str) -> dict:
#         logger.info("Orchestrator: Starting Lead Search Flow")
#         # 1. Fetch Profile (if any)
#         try:
#             profile = BusinessProfile.objects.get(account_id=self.session.tenant_id)
#             description = profile.description or ""
#         except BusinessProfile.DoesNotExist:
#             description = ""
            
#         # 2. Init State (Preserve existing slots if available)
#         existing_slots = self.state.get("slots", {})
        
#         past_flows = self.state.get("past_flows", [])
        
#         self.state = {
#             "flow": LEAD_SEARCH_FLOW,
#             "step": COLLECTING_INFO,
#             "slots": existing_slots,
#             "past_flows": past_flows
#         }
#         self._save_state()
        
#         # 3. Trigger first pass with user's actual text to capture any initial params (e.g. "Find CEOs in NY")
#         return self._run_collection_cycle(description, user_text)

#     def _handle_lead_search(self, user_text: str) -> dict:
#         # Fetch profile
#         try:
#             profile = BusinessProfile.objects.get(account_id=self.session.tenant_id)
#             description = profile.description or ""
#         except BusinessProfile.DoesNotExist:
#             description = ""

#         # INTERRUPTION CHECK REMOVED: Handled globally in handle_message


#         # Run cycle with user input
#         return self._run_collection_cycle(description, user_text)

#     def _run_collection_cycle(self, description: str, user_input: str) -> dict:
#         current_slots = self.state.get("slots", {})
        
#         try:
#              profile_obj = BusinessProfile.objects.get(account_id=self.session.tenant_id)
#              profile_data = model_to_dict(profile_obj)
#         except BusinessProfile.DoesNotExist:
#              profile_data = {}

#         # 1. LLM Decision
#         # Get last 5 messages for context
#         history_context = self.history[-7:] if hasattr(self, 'history') and self.history else []
        
#         result = self.extractor.extract(
#             business_data=profile_data, 
#             current_state=current_slots, 
#             user_query=user_input,
#             history=history_context
#         )
        
#         # 2. Update State
#         if result.get("parameters"):
#             self.state["slots"] = result["parameters"]
        
#         status = result.get("status")
#         logger.info(f"Orchestrator: Extract Result. Status={status}, Params={result.get('parameters', {}).keys()}")

#         # 3. Decision
#         if status == "MISSING_INFO":
#             self._save_state()
#             question = result.get("next_question") or "Could you provide more details?"
            
#             response = {
#                 "text": question,
#                 "state": self.state
#             }
#             response.update(self._get_flow_status())
#             return response
            
#         if status == "COMPLETE":
#             self.state["step"] = CONFIRM_SEARCH_PARAMS
#             # self.state["flow"] = None # KEPT ACTIVE
#             self._save_state()
            
#             params = result.get("parameters", {})
#             response = {
#                 "text": "Lead search parameters generated successfully.",
#                 "parameters": params,
#                 "state": self.state
#             }
#             response.update(self._get_flow_status())
#             return response
            
#         response = {
#             "text": "I'm having trouble understanding. Could you rephrase?",
#             "state": self.state
#         }
#         response.update(self._get_flow_status())
#         return response

#     # ---------- CAMPAIGN FLOW ----------
#     def start_campaign_flow(self, user_text: str) -> dict:
#         logger.info("Orchestrator: Starting Campaign Flow")
        
#         # Init State
#         self.state = {
#             "flow": CAMPAIGN_FLOW,
#             "step": "clarifying",
#             "campaign_context": {}, # Stores goal, tone, etc.
#             "past_flows": self.state.get("past_flows", [])
#         }
#         self._save_state()
        
#         return self._handle_campaign_flow(user_text)

#     def _handle_campaign_flow(self, user_text: str) -> dict:
#         from .campaign_service import CampaignService
#         import uuid
        
#         # 1. Get or Create Campaign ID for tracking
#         campaign_id = self.state.get("campaign_id")
#         if not campaign_id:
#             campaign_id = str(uuid.uuid4())
#             self.state["campaign_id"] = campaign_id
        
#         # 2. Get Current Context
#         current_context = self.state.get("campaign_context", {})
        
#         # 3. Call Service to Clarify using existing clarify_intent method
#         # We pass the full history (CampaignService expects conversation_history)
#         service = CampaignService()
#         result = service.clarify_intent(campaign_id, self.history)
        
#         # 4. Map Result to Response
#         status = result.get("status")
#         response_text = ""
        
#         if status == "needs_clarification":
#             # Extract the question to ask
#             questions = result.get("questions", [])
#             if questions:
#                 response_text = questions[0].get("question", "Could you tell me more about your campaign goals?")
#             else:
#                 response_text = "Could you tell me more about your campaign goals?"
            
#             # Track missing fields in state
#             self.state["missing_fields"] = result.get("missing_fields", [])
            
#         elif status == "ready_for_generation":
#             # Extract context and store it
#             extracted_context = result.get("context", {})
#             current_context.update(extracted_context)
#             self.state["campaign_context"] = current_context
#             self.state["step"] = "ready_for_generation"
            
#             # Summarize what we have
#                     # goal = extracted_context.get("goal", "your goal")
#                     # audience = extracted_context.get("target_audience", "your audience")
#             response_text = f"Great! I have everything I need to generate your campaign."
        
#         else:
#             # Unknown status fallback
#             response_text = "I'm having trouble understanding. Could you describe your campaign goals?"
        
#         self._save_state()
        
#         response = {
#             "text": response_text,
#             "state": self.state,
#             "campaign_status": status,  # Frontend uses this to show "Generate" button
#             "campaign_context": self.state.get("campaign_context", {})  # For API consumption
#         }
#         response.update(self._get_flow_status())
#         return response

#     # ---------- STATE ----------
#     def _save_state(self):
#         self.session.state = self.state
#         self.session.save()





import logging
from .intent_classifier import IntentClassifier
from .chit_chat_handler import BrandChitChatHandler
from ..models import BusinessProfile
from .lead_extractor import LeadParameterExtractor

LEAD_SEARCH_FLOW = "lead_search"
CAMPAIGN_FLOW = "campaign_flow"
COLLECTING_INFO = "collecting_info"
CONFIRM_SEARCH_PARAMS = "confirm_search_params"

from django.forms.models import model_to_dict

logger = logging.getLogger(__name__)

class ConversationOrchestrator:
    def __init__(self, session):
        self.session = session
        self.state = session.state or {}

        self.intent_classifier = IntentClassifier()
        # Try to fetch tenant profile for dynamic brand name
        try:
            profile = BusinessProfile.objects.get(account_id=session.tenant_id)
            brand_name = profile.name if profile.name else "Your Assistant"
            # Get tone from JSON field
            brand_tone = profile.tone_preferences if profile.tone_preferences else "friendly"
        except BusinessProfile.DoesNotExist:
            brand_name = "Your Assistant"
            brand_tone = "friendly"

        self.chit_chat_handler = BrandChitChatHandler(
            brand_name=brand_name,
            brand_tone=brand_tone
        )
        self.extractor = LeadParameterExtractor()

    # ---------- HELPER METHODS ----------
    def _save_state(self):
        self.session.state = self.state
        self.session.save()

    def _get_future_flows(self, current_flow: str, step: str) -> list:
        """
        Determines the likely next steps in the end-to-end business process.
        Returns full API URLs using the SQUIBB_DOMAIN_URL from settings.
        """
        from django.conf import settings
        
        domain_url = getattr(settings, 'SQUIBB_DOMAIN_URL', 'https://test-ai.squibb.ai')
        
        # Mapping of flow names to their API paths
        flow_url_mapping = {
            "people_search_api": "/api/leads/search/people/",
            "people_reveal_api": "/api/leads/reveal/people/",
            "campaign": "/api/ml/campaigns/generate/",
            "campaign_generate": "/api/ml/campaigns/generate/",
            "lead_search": "/api/leads/search/people/",
        }
        
        future = []
        
        if current_flow == LEAD_SEARCH_FLOW:
            if step == CONFIRM_SEARCH_PARAMS:
                future.append("people_search_api")
            else:
                # Still in progress
                future.append("people_search_api") # Eventually we get here
                
        elif current_flow == "people_search_api":
            future.append("people_reveal_api")
            
        elif current_flow == "people_reveal_api":
            future.append("campaign") # Hypothetical next step
        
        elif current_flow == CAMPAIGN_FLOW:
            # When in campaign flow, suggest campaign generation
            if step == "ready_for_generation":
                future.append("campaign_generate")
            else:
                # Still clarifying
                future.append("campaign_generate")

        # Check based on past flows if current is empty
        if not current_flow:
            past = self.state.get("past_flows", [])
            
            # Find last "meaningful" flow (ignore chit_chat)
            last_meaningful = None
            for flow_name in reversed(past):
                if flow_name != "chit_chat":
                    last_meaningful = flow_name
                    break
            
            if last_meaningful == "people_search_api":
                 future.append("people_reveal_api")
            elif last_meaningful == "people_reveal_api":
                 future.append("campaign")
            else:
                 # Default: If we have started chatting (messages exist), suggest lead_search.
                 # If session is brand new (no messages), keep it empty.
                 if self.session.messages.exists():
                     future.append("lead_search")

        # Convert flow names to full URLs
        future_with_urls = []
        for flow_name in future:
            url_path = flow_url_mapping.get(flow_name, f"/api/{flow_name}/")
            full_url = f"{domain_url}{url_path}"
            future_with_urls.append({
                "flow": flow_name,
                "url": full_url
            })
        
        return future_with_urls

    def transition_flow(self, new_flow: str):
        """
        Explicitly transitions the state to a new flow (e.g. triggered by an external API call).
        Returns the new flow status.
        """
        current = self.state.get("flow")
        
        # Only archive if it's a different flow and not just a re-run
        if current and current != new_flow:
            past = self.state.get("past_flows", [])
            
            # Prevent consecutive duplicates
            if not past or past[-1] != current:
                past.append(current)
                self.state["past_flows"] = past
        
        self.state["flow"] = new_flow
        self.state["step"] = "executed" 
        self._save_state()
        
        return self._get_flow_status()

    def _get_flow_status(self) -> dict:
        current_flow = self.state.get("flow")
        step = self.state.get("step")
        past_flows = self.state.get("past_flows", [])
        future_flows = self._get_future_flows(current_flow, step)
        
        return {
            "current_flow": current_flow,
            "past_flows": past_flows,
            "future_flows": future_flows
        }

    # ---------- PUBLIC ENTRY POINT ----------
    def handle_message(self, user_text: str) -> dict:
        logger.info(f"Orchestrator: Handle Message. Session={self.session.session_id}, State={self.state}")
        
        # Load history
        self.history = [
            {"role": msg.role, "content": msg.text}
            for msg in self.session.messages.order_by("timestamp")
        ]
        
        # Limit context
        if len(self.history) > 10:
            self.history = self.history[-10:]

        # 1. Classify Intent (Check for global commands/chitchat)
        classification = self.intent_classifier.classify(self.history)
        intent = classification.get("general_intent")
        logger.info(f"Orchestrator: Classified Intent='{intent}'")

        # 2. Global Handlers (High Priority)
        if intent == "chit_chat":
            # If explicit chit-chat is detected, respond and DO NOT change flow state
            # This allows "interruption" without losing context
            logger.info("Orchestrator: Handling Chit Chat (Interruption or Start)")
            reply_text = self.chit_chat_handler.respond(user_text, history=self.history)
            if not reply_text:
                reply_text = f"Hi! How can I help you today? I can help you find leads or build sales campaigns."
            
            response = {
                "text": reply_text,
                "state": self.state # Preserve existing state
            }
            
            # 1. Get Status based on PRE-saved state
            status = self._get_flow_status()
            
            # Filter redundant 'chit_chat' from past_flows for display if we are currently in chit_chat
            display_past = status["past_flows"][:]
            if display_past and display_past[-1] == "chit_chat":
                display_past.pop()
            
            # If we are interrupting a flow (e.g. lead_search), add it to past_flows for visibility
            background_flow = self.state.get("flow")
            if background_flow:
                 if not display_past or display_past[-1] != background_flow:
                    display_past.append(background_flow)
            
            status["past_flows"] = display_past
            status["current_flow"] = "chit_chat" # Visual override
            
            # 2. Update Past Flows (for NEXT turn)
            past = self.state.get("past_flows", [])
            if not past or past[-1] != "chit_chat":
                past.append("chit_chat")
                self.state["past_flows"] = past
                self._save_state()
            
            # 3. Return response with Clean status
            response.update(status)
            return response

        # 3. Flow Routing
        active_flow = self.state.get("flow")

        # IMPORTANT: If already in a multi-turn flow (campaign or lead_search), 
        # continue that flow unless explicitly starting something new.
        # This prevents campaign answers like "I want to target SaaS CTOs" from 
        # being misclassified as lead_search.
        
        if active_flow == CAMPAIGN_FLOW:
            # User is in campaign flow - continue with campaign regardless of detected intent
            # (unless they explicitly say "create campaign" which would just continue anyway)
            logger.info(f"Orchestrator: Continuing active campaign flow")
            return self._route_active_flow(user_text)
        
        if intent == "lead_search":
            # User explicitly wants to search. 
            # If already in search, continue. If not, start new.
            if active_flow != LEAD_SEARCH_FLOW:
                 return self.start_lead_search(user_text)
            # If already in lead search, let it flow through to _handle_lead_search 
            # (which might treat this as a refinement)
        
        if intent == "create_campaign":
            if active_flow != CAMPAIGN_FLOW:
                return self.start_campaign_flow(user_text)
            # Else fall through to route_active_flow

        # 4. Active Flow Processing
        if active_flow:
            # If intent is unknown while in an active flow, the message is off-topic
            # or a greeting — hand it to chit-chat to ask a clarifying question
            # rather than blindly feeding it into the current flow.
            if intent == "unknown":
                logger.info("Orchestrator: Unknown intent in active flow — routing to chit-chat for clarification")
                reply_text = self.chit_chat_handler.respond(user_text, history=self.history)
                if not reply_text:
                    reply_text = "I'm not sure I understood that. Could you clarify what you'd like to do?"
                response = {"text": reply_text, "state": self.state}
                response.update(self._get_flow_status())
                return response

            logger.info(f"Orchestrator: Routing to active flow '{active_flow}'.")
            return self._route_active_flow(user_text)

        # 5. Fallback (No flow, no clear intent, or unknown)
        return self._handle_no_active_flow(intent, user_text)

    # ---------- FLOW ROUTING ----------
    def _handle_no_active_flow(self, intent: str, user_text: str) -> dict:
        # If we reached here, intent was not chit_chat or lead_search.
        
        # Double check just in case logic slips
        if intent == "lead_search":
             return self.start_lead_search(user_text)

        if intent == "create_campaign":
             return self.start_campaign_flow(user_text)

        # Last-resort heuristic: if the message contains strong lead-search signals,
        # start that flow rather than showing the generic fallback.
        text_lower = user_text.lower()
        lead_signals = ["find", "search", "cto", "ceo", "cfo", "coo", "vp",
                        "director", "manager", "founder", "leads", "people",
                        "companies", "startups", "looking for", "get me", "show me"]
        if any(signal in text_lower for signal in lead_signals):
            logger.info("Orchestrator: No-flow fallback detected lead-search signals, starting lead_search")
            return self.start_lead_search(user_text)

        msg = "I'm not sure what you're looking for — could you tell me more? For example: 'Find CTOs at SaaS startups in the US' or 'Create an outreach campaign'."
        
        response = {
            "text": msg,
            "state": self.state
        }
        response.update(self._get_flow_status())
        return response

    def _route_active_flow(self, user_text: str) -> dict:
        flow = self.state.get("flow")
        
        if flow == LEAD_SEARCH_FLOW:
            return self._handle_lead_search(user_text)
            
        if flow == CAMPAIGN_FLOW:
            return self._handle_campaign_flow(user_text)

        # Should not happen if flow is valid, but safe fallback
        response = {
            "text": "I’m currently in a task but got lost. Let's start over.",
            "state": {} 
        }
        response.update(self._get_flow_status())
        return response

    # ---------- FLOW LOGIC ----------
    def start_lead_search(self, user_text: str) -> dict:
        logger.info("Orchestrator: Starting Lead Search Flow")
        # 1. Fetch Profile (if any)
        try:
            profile = BusinessProfile.objects.get(account_id=self.session.tenant_id)
            description = profile.description or ""
        except BusinessProfile.DoesNotExist:
            description = ""
            
        # 2. Init State (Preserve existing slots if available)
        existing_slots = self.state.get("slots", {})
        
        past_flows = self.state.get("past_flows", [])
        
        self.state = {
            "flow": LEAD_SEARCH_FLOW,
            "step": COLLECTING_INFO,
            "slots": existing_slots,
            "past_flows": past_flows
        }
        self._save_state()
        
        # 3. Trigger first pass with user's actual text to capture any initial params (e.g. "Find CEOs in NY")
        return self._run_collection_cycle(description, user_text)

    def _handle_lead_search(self, user_text: str) -> dict:
        # Fetch profile
        try:
            profile = BusinessProfile.objects.get(account_id=self.session.tenant_id)
            description = profile.description or ""
        except BusinessProfile.DoesNotExist:
            description = ""

        # INTERRUPTION CHECK REMOVED: Handled globally in handle_message


        # Run cycle with user input
        return self._run_collection_cycle(description, user_text)

    def _run_collection_cycle(self, description: str, user_input: str) -> dict:
        current_slots = self.state.get("slots", {})
        
        try:
             profile_obj = BusinessProfile.objects.get(account_id=self.session.tenant_id)
             profile_data = model_to_dict(profile_obj)
        except BusinessProfile.DoesNotExist:
             profile_data = {}

        # 1. LLM Decision
        # Get last 5 messages for context
        history_context = self.history[-7:] if hasattr(self, 'history') and self.history else []
        
        result = self.extractor.extract(
            business_data=profile_data, 
            current_state=current_slots, 
            user_query=user_input,
            history=history_context
        )
        
        # 2. Update State
        if result.get("parameters"):
            self.state["slots"] = result["parameters"]
        
        status = result.get("status")
        logger.info(f"Orchestrator: Extract Result. Status={status}, Params={result.get('parameters', {}).keys()}")

        # 3. Decision
        if status == "MISSING_INFO":
            self._save_state()
            question = result.get("next_question") or "Could you provide more details?"
            
            response = {
                "text": question,
                "state": self.state
            }
            response.update(self._get_flow_status())
            return response
            
        if status == "COMPLETE":
            self.state["step"] = CONFIRM_SEARCH_PARAMS
            # self.state["flow"] = None # KEPT ACTIVE
            self._save_state()
            
            params = result.get("parameters", {})
            response = {
                "text": "Lead search parameters generated successfully.",
                "parameters": params,
                "state": self.state
            }
            response.update(self._get_flow_status())
            return response
            
        response = {
            "text": "I'm having trouble understanding. Could you rephrase?",
            "state": self.state
        }
        response.update(self._get_flow_status())
        return response

    # ---------- CAMPAIGN FLOW ----------
    def start_campaign_flow(self, user_text: str) -> dict:
        logger.info("Orchestrator: Starting Campaign Flow")
        
        # Init State
        self.state = {
            "flow": CAMPAIGN_FLOW,
            "step": "clarifying",
            "campaign_context": {}, # Stores goal, tone, etc.
            "past_flows": self.state.get("past_flows", [])
        }
        self._save_state()
        
        return self._handle_campaign_flow(user_text)

    def _handle_campaign_flow(self, user_text: str) -> dict:
        from .campaign_service import CampaignService
        import uuid
        
        # 1. Get or Create Campaign ID for tracking
        campaign_id = self.state.get("campaign_id")
        if not campaign_id:
            campaign_id = str(uuid.uuid4())
            self.state["campaign_id"] = campaign_id
        
        # 2. Get Current Context
        current_context = self.state.get("campaign_context", {})
        
        # 3. Call Service to Clarify using existing clarify_intent method
        # We pass the full history (CampaignService expects conversation_history)
        service = CampaignService()
        result = service.clarify_intent(campaign_id, self.history)
        
        # 4. Map Result to Response
        status = result.get("status")
        response_text = ""
        
        if status == "needs_clarification":
            # Extract the question to ask
            questions = result.get("questions", [])
            if questions:
                response_text = questions[0].get("question", "Could you tell me more about your campaign goals?")
            else:
                response_text = "Could you tell me more about your campaign goals?"
            
            # Track missing fields in state
            self.state["missing_fields"] = result.get("missing_fields", [])
            
        elif status == "ready_for_generation":
            # Extract context and store it
            extracted_context = result.get("context", {})
            current_context.update(extracted_context)
            self.state["campaign_context"] = current_context
            self.state["step"] = "ready_for_generation"
            
            # Summarize what we have
                    # goal = extracted_context.get("goal", "your goal")
                    # audience = extracted_context.get("target_audience", "your audience")
            response_text = f"Great! I have everything I need to generate your campaign."
        
        else:
            # Unknown status fallback
            response_text = "I'm having trouble understanding. Could you describe your campaign goals?"
        
        self._save_state()
        
        response = {
            "text": response_text,
            "state": self.state,
            "campaign_status": status,  # Frontend uses this to show "Generate" button
            "campaign_context": self.state.get("campaign_context", {})  # For API consumption
        }
        response.update(self._get_flow_status())
        return response

    # ---------- STATE ----------
    def _save_state(self):
        self.session.state = self.state
        self.session.save()