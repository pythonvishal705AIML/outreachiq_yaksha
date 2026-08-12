from api.models import BusinessProfile, Campaign, CampaignContext, CampaignEmail, CampaignStep, LeadListNew
from api.services.campaign_service import CampaignService as APICampaignService
from agent_runtime.services.campaign_service import CampaignService
from agent_runtime.prompts import CAMPAIGN_BRAND_MANAGER_PROMPT
from agent_runtime.clients.streaming import stream_completion

class CampaignAgent:
    def __init__(self, session):
        self.session = session
        self.service = APICampaignService()

    def _ensure_campaign(self) -> Campaign:
        state = self.session.state or {}
        campaign_id = state.get("campaign_id")
        if campaign_id:
            try:
                return Campaign.objects.get(id=campaign_id)
            except Campaign.DoesNotExist:
                pass

        # Generate campaign name from ICP slots
        slots = state.get("slots", {})
        search_run_id = state.get("search_run_id")
        
        # If slots are empty, try to get them from search_run
        if not slots and search_run_id:
            try:
                from api.models import SearchRun
                search_run = SearchRun.objects.get(id=search_run_id)
                if search_run.search_params:
                    slots = search_run.search_params
            except Exception:
                pass
        
        campaign_name = self._generate_campaign_name(slots)

        # Use lead_list_id from session state (set by LeadSelectionService)
        lead_list_id = state.get("lead_list_id")
        user_id = state.get("user_id")

        # Create campaign using Django ORM (not raw SQL)
        # This ensures proper UUID handling and foreign key compatibility
        campaign = Campaign.objects.create(
            org_id_id=self.session.tenant_id,  # tenant_id is the Account.id (CharField)
            name=campaign_name,
            creation_mode="ai",
            status="ai_clarifying",
            lead_list_id=lead_list_id,
            created_by=user_id,
        )

        state["campaign_id"] = str(campaign.id)
        state["flow"] = "campaign_flow"
        state["search_run_id"] = search_run_id  # Keep search_run_id in state for reference
        self.session.state = state
        self.session.save(update_fields=["state", "updated_at"])
        
        return campaign

    def _generate_campaign_name(self, slots: dict) -> str:
        """Generate campaign name from ICP slots."""
        parts = []
        
        # Add person location (city/state)
        person_locations = slots.get("person_locations", [])
        if person_locations and isinstance(person_locations, list) and len(person_locations) > 0:
            # Extract just city or state name (e.g., "California, US" -> "California")
            location = person_locations[0].split(',')[0].strip()
            parts.append(location)
        
        # Add organization location as fallback
        if not parts:
            org_locations = slots.get("organization_locations", [])
            if org_locations and isinstance(org_locations, list) and len(org_locations) > 0:
                location = org_locations[0].split(',')[0].strip()
                parts.append(location)
        
        # Add keywords (industry/sector)
        keywords = slots.get("q_keywords", [])
        if keywords and isinstance(keywords, list) and len(keywords) > 0:
            # Take first keyword and clean it up
            keyword = keywords[0].replace("saas applications", "SaaS").replace("software as a service (saas)", "SaaS")
            if len(keyword) < 20:  # Only add if not too long
                parts.append(keyword.title())
        
        # Add person title/role
        person_titles = slots.get("person_titles", [])
        if person_titles and isinstance(person_titles, list) and len(person_titles) > 0:
            # Take first title and simplify
            title = person_titles[0].replace("director of marketing", "Marketing Directors")
            title = title.replace("marketing director", "Marketing Directors")
            title = title.replace("marketing manager", "Marketing Managers")
            title = title.title()
            parts.append(title)
        
        # Build name
        if parts:
            # Limit to 3 parts max for readability
            campaign_name = " ".join(parts[:3]) + " Campaign"
            return campaign_name
        
        # Fallback with timestamp to ensure uniqueness
        import datetime
        timestamp = datetime.datetime.now().strftime("%b %d")
        return f"AI Campaign {timestamp}"

    def handle(self, user_text: str, history: list[dict], agent_log=None) -> dict:
        if agent_log:
            agent_log.log_action(actor="campaign_agent", action="ensure_campaign")
        campaign = self._ensure_campaign()
        
        # Gather slots and business profile for smart defaults
        state = self.session.state or {}
        slots = state.get("slots", {})
        
        # Update campaign name if slots are now available and name is still generic
        if slots and campaign.name in ["AI powered Campaign", "AI powered"] or campaign.name.startswith("AI Campaign"):
            new_name = self._generate_campaign_name(slots)
            if new_name != campaign.name:
                campaign.name = new_name
                campaign.save(update_fields=["name", "updated_at"])
        
        business_profile = self._organization_context()
        
        # Option 1: Use CAMPAIGN_CLARIFICATION_PROMPT (minimal questions with smart defaults)
        # Option 2: Use CAMPAIGN_CLARIFICATION_PROMPT_COMBINED (single combined question)
        # Set use_combined_prompt=True for Option 2, False for Option 1
        use_combined_prompt = False  # Change to True to use Option 2
        
        if agent_log:
            agent_log.log_action(actor="campaign_agent", action="clarify_intent", detail={"campaign_id": str(campaign.id)})
        
        clarification = self.service.clarify_intent(
            str(campaign.id), 
            history,
            slots=slots,
            business_profile=business_profile,
            use_combined_prompt=use_combined_prompt
        )
        
        status = clarification.get("status")
        missing_fields = clarification.get("missing_fields") or []
        questions = clarification.get("questions") or []
        if status != "ready_for_generation":
            question = None
            if questions and isinstance(questions, list):
                first_q = questions[0]
                if isinstance(first_q, dict):
                    question = first_q.get("question")
                elif isinstance(first_q, str):
                    question = first_q
            if not question:
                question = (
                    "Before I generate the campaign, what is your primary goal, "
                    "target audience, and desired tone?"
                )
            return {
                "text": question,
                "campaign_status": "ai_clarifying",
                "campaign_context": {
                    "organization": self._organization_context(),
                    "clarification": clarification,
                    "missing_fields": missing_fields,
                },
                "parameters": {"campaign_id": str(campaign.id), "missing_fields": missing_fields},
                "state": {"slots": (self.session.state or {}).get("slots", {})},
                "current_flow": "campaign_flow",
                "past_flows": (self.session.state or {}).get("past_flows", []),
                "future_flows": [{"flow": "campaign_generate", "url": "/api/ml/campaigns/generate/"}],
            }

        # Flatten the LLM-extracted clarification fields to the top level so that
        # generate_campaign can find goal/target_audience/tone/value_proposition/follow_up
        # via context.get(...). They are nested under clarification["context"] in the
        # LLM response but generate_campaign reads them at the top level of context.
        clarification_ctx = clarification.get("context", {})
        context = {
            "organization": self._organization_context(),
            "clarification": clarification,
            "last_user_input": user_text,
            "goal": clarification_ctx.get("goal", ""),
            "target_audience": clarification_ctx.get("target_audience", ""),
            "tone": clarification_ctx.get("tone", ""),
            "value_proposition": clarification_ctx.get("value_proposition", ""),
            # CAMPAIGN_CLARIFICATION_PROMPT returns "follow_up"; generate_campaign reads "follow_up_logic"
            "follow_up_logic": clarification_ctx.get("follow_up", "") or clarification_ctx.get("follow_up_logic", ""),
        }
        if agent_log:
            agent_log.log_action(actor="campaign_agent", action="generate_campaign", detail={"campaign_id": str(campaign.id)})
        campaign_payload = self.service.generate_campaign(str(campaign.id), context)

        # generate_campaign already validates and embeds emails in each step.
        # Use those directly instead of making a redundant generate_email_draft call per step.
        generated = []
        for idx, step in enumerate(campaign_payload.get("steps", []), start=1):
            # update_or_create so that re-generation updates delay_days and condition
            # instead of silently keeping stale values from the first generation.
            step_obj, _ = CampaignStep.objects.update_or_create(
                campaign=campaign,
                step_order=idx,
                defaults={
                    "delay_days": int(step.get("delay_days", 0)),
                    "condition": step.get("condition", "always"),
                },
            )
            #direct genratge all mail Generate full campaign
            email = step.get("email", {})
            CampaignEmail.objects.update_or_create(
                step=step_obj,
                defaults={"subject": email.get("subject", ""), "body": email.get("body", ""), "origin": "ai"},
            )
            generated.append(email)

        CampaignContext.objects.update_or_create(
            campaign=campaign,
            defaults={"context_json": context, "status": "complete", "completeness_score": 0.8},
        )

        state = self.session.state or {}
        state.update({"flow": "campaign_flow", "step": "ready_for_generation", "campaign_id": str(campaign.id)})
        self.session.state = state
        self.session.save(update_fields=["state", "updated_at"])

        # ── Step 5 & 6: Call Sequence List API ───────────────────────────────
        if agent_log:
            agent_log.log_action(actor="campaign_agent", action="fetch_sequences", detail={"campaign_id": str(campaign.id)})
        
        # Call get_campaign_sequences to get the formatted response (static method)
        sequence_response = CampaignService.get_campaign_sequences(
            session_id=self.session.session_id,
            campaign_id=str(campaign.id)
        )

        # Build success message with sequence details
        steps_data = sequence_response.get("data", {}).get("steps", [])
        
        # Short summary for frontend reply field
        if campaign.name and len(steps_data) > 0:
            short_reply = f"Campaign '{campaign.name}' with {len(steps_data)} email steps has been generated successfully and is ready for review."
        else:
            short_reply = "Campaign created successfully."

        # Return the sequence API response with additional metadata
        return {
            "reply": short_reply,
            "campaign_status": sequence_response.get("data", {}).get("campaign_status", "ai_generated"),
            "campaign_id": str(campaign.id),
            "search_run_id": state.get("search_run_id"),
            "sequence_list": sequence_response,
            "state": {"slots": state.get("slots", {})},
            "current_flow": "campaign_flow",
            "past_flows": state.get("past_flows", []),
            "future_flows": [{"flow": "campaign_review", "url": f"/api/agent/v1/campaigns/sequences/?campaign_id={campaign.id}"}],
        }

    def handle_stream(self, user_text: str, history: list[dict], agent_log=None):
        """
        Generator: yields streaming events so the user sees activity immediately
        instead of a blank screen for 15-20s.

        Stage 1 (clarification): streams the clarification question word by word.
        Stage 2 (generation):    yields a "working" token right away, then runs
                                 generate_campaign() and yields the final result.
        """
        if agent_log:
            agent_log.log_action(actor="campaign_agent", action="ensure_campaign")
        campaign = self._ensure_campaign()
        
        # Gather slots and business profile for smart defaults
        state = self.session.state or {}
        slots = state.get("slots", {})
        
        # Update campaign name if slots are now available and name is still generic
        if slots and campaign.name in ["AI powered Campaign", "AI powered"] or campaign.name.startswith("AI Campaign"):
            new_name = self._generate_campaign_name(slots)
            if new_name != campaign.name:
                campaign.name = new_name
                campaign.save(update_fields=["name", "updated_at"])
        
        business_profile = self._organization_context()
        
        # Option 1: Use CAMPAIGN_CLARIFICATION_PROMPT (minimal questions with smart defaults)
        # Option 2: Use CAMPAIGN_CLARIFICATION_PROMPT_COMBINED (single combined question)
        # Set use_combined_prompt=True for Option 2, False for Option 1
        use_combined_prompt = False  # Change to True to use Option 2
        
        if agent_log:
            agent_log.log_action(actor="campaign_agent", action="clarify_intent", detail={"campaign_id": str(campaign.id)})
        
        clarification = self.service.clarify_intent(
            str(campaign.id), 
            history,
            slots=slots,
            business_profile=business_profile,
            use_combined_prompt=use_combined_prompt
        )
        
        status = clarification.get("status")

        # ── Stage 1: still collecting info — stream the question back ──
        if status != "ready_for_generation":
            questions = clarification.get("questions") or []
            question = None
            if questions:
                first_q = questions[0]
                question = first_q.get("question") if isinstance(first_q, dict) else first_q
            if not question:
                question = (
                    "Before I generate the campaign, what is your primary goal, "
                    "target audience, and desired tone?"
                )

            missing_fields = clarification.get("missing_fields") or []
            result_data = {
                "text": question,
                "campaign_status": "ai_clarifying",
                "campaign_context": {
                    "organization": self._organization_context(),
                    "clarification": clarification,
                    "missing_fields": missing_fields,
                },
                "parameters": {"campaign_id": str(campaign.id), "missing_fields": missing_fields},
                "state": {"slots": (self.session.state or {}).get("slots", {})},
                "current_flow": "campaign_flow",
                "past_flows": (self.session.state or {}).get("past_flows", []),
                "future_flows": [{"flow": "campaign_generate", "url": "/api/ml/campaigns/generate/"}],
            }

            # Stream word by word so the user sees text arriving
            for word in question.split(" "):
                yield {"type": "token", "text": word + " "}
            yield {"type": "result", "data": result_data}
            return

        # ── Stage 2: ready — tell user immediately, then run heavy generation ──
        yield {"type": "token", "text": "Got it! Building your campaign now... "}

        clarification_ctx = clarification.get("context", {})
        context = {
            "organization": self._organization_context(),
            "clarification": clarification,
            "last_user_input": user_text,
            "goal": clarification_ctx.get("goal", ""),
            "target_audience": clarification_ctx.get("target_audience", ""),
            "tone": clarification_ctx.get("tone", ""),
            "value_proposition": clarification_ctx.get("value_proposition", ""),
            "follow_up_logic": clarification_ctx.get("follow_up", "") or clarification_ctx.get("follow_up_logic", ""),
        }

        if agent_log:
            agent_log.log_action(actor="campaign_agent", action="generate_campaign", detail={"campaign_id": str(campaign.id)})
        try:
            campaign_payload = self.service.generate_campaign(str(campaign.id), context)
        except Exception as e:
            if agent_log:
                agent_log.log_error(actor="campaign_agent", error=str(e), detail={"stage": "generate_campaign"})
            yield {"type": "token", "text": "Sorry, I ran into an error generating your campaign. Please try again."}
            yield {"type": "result", "data": {"text": str(e), "campaign_status": "error", "current_flow": "campaign_flow"}}
            return

        generated = []
        for idx, step in enumerate(campaign_payload.get("steps", []), start=1):
            step_obj, _ = CampaignStep.objects.update_or_create(
                campaign=campaign,
                step_order=idx,
                defaults={
                    "delay_days": int(step.get("delay_days", 0)),
                    "condition": step.get("condition", "always"),
                },
            )
            email = step.get("email", {})
            CampaignEmail.objects.update_or_create(
                step=step_obj,
                defaults={"subject": email.get("subject", ""), "body": email.get("body", ""), "origin": "ai"},
            )
            generated.append(email)

        CampaignContext.objects.update_or_create(
            campaign=campaign,
            defaults={"context_json": context, "status": "complete", "completeness_score": 0.8},
        )

        state = self.session.state or {}
        state.update({"flow": "campaign_flow", "step": "ready_for_generation", "campaign_id": str(campaign.id)})
        self.session.state = state
        self.session.save(update_fields=["state", "updated_at"])

        # ── Step 5 & 6: Call Sequence List API ───────────────────────────────
        if agent_log:
            agent_log.log_action(actor="campaign_agent", action="fetch_sequences", detail={"campaign_id": str(campaign.id)})
        
        # Call get_campaign_sequences to get the formatted response (static method)
        sequence_response = CampaignService.get_campaign_sequences(
            session_id=self.session.session_id,
            campaign_id=str(campaign.id)
        )

        # Build success message with sequence details
        steps_data = sequence_response.get("data", {}).get("steps", [])
        
        # Short summary for frontend reply field
        if campaign.name and len(steps_data) > 0:
            short_reply = f"Campaign '{campaign.name}' with {len(steps_data)} email steps has been generated successfully and is ready for review."
        else:
            short_reply = "Campaign created successfully."

        result_data = {
            "reply": short_reply,
            "campaign_status": sequence_response.get("data", {}).get("campaign_status", "ai_generated"),
            "campaign_id": str(campaign.id),
            "search_run_id": state.get("search_run_id"),
            "sequence_list": sequence_response,
            "state": {"slots": state.get("slots", {})},
            "current_flow": "campaign_flow",
            "past_flows": state.get("past_flows", []),
            "future_flows": [{"flow": "campaign_review", "url": f"/api/agent/v1/campaigns/sequences/?campaign_id={campaign.id}"}],
        }

        # Stream the short reply message then close
        for word in short_reply.split(" "):
            yield {"type": "token", "text": word + " "}
        yield {"type": "result", "data": result_data}

    def _organization_context(self) -> dict:
        try:
            profile = BusinessProfile.objects.get(account_id=self.session.tenant_id)
            return {
                "org_id": self.session.tenant_id,
                "name": profile.name,
                "industry": profile.industry,
                "description": profile.description,
                "brand_voice": profile.brand_voice,
                "tone_preferences": profile.tone_preferences or {},
                "services": profile.services or [],
            }
        except BusinessProfile.DoesNotExist:
            return {"org_id": self.session.tenant_id}
