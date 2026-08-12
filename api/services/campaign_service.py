import json
import logging
import threading
from typing import List, Dict, Any
from ..clients.llm_client import LLMClient
from ..models import Campaign, MLConversation, MLCampaignContext, MLGeneration, CampaignStep, CampaignEmail, MLSpamAnalysis
from ..prompts import CAMPAIGN_CLARIFICATION_PROMPT, CAMPAIGN_CLARIFICATION_PROMPT_COMBINED, CAMPAIGN_GENERATION_PROMPT, EMAIL_GENERATION_PROMPT, EMAIL_SPAM_SCORE, REPLY_GENERATION_PROMPT, REPLY_UNDERSTANDING_PROMPT, SUBJECT_LINE_GENERATION_PROMPT, TONE_PREFIXES, CONTEXTUAL_FOLLOWUP_PROMPT, CAMPAIGN_GENERATION_FALLBACK_PROMPT, EMAIL_GENERATION_FALLBACK_PROMPT

logger = logging.getLogger(__name__)

# ── Singleton: reuse one LLMClient across all requests ──
_shared_llm_client = LLMClient()

class CampaignService:
    """
    Service to handle Campaign creation logic, specifically the 
    Clarification & Intent Understanding phase using LLM.
    """

    def __init__(self):
        # self.llm_client = LLMClient()
        self.llm_client = _shared_llm_client
        self.model = "gpt-4o-mini"  # Fast, capable — replaces gpt-5-mini for speed

    def clarify_intent(
        self, 
        campaign_id: str, 
        conversation_history: List[Dict],
        slots: Dict = None,
        business_profile: Dict = None,
        use_combined_prompt: bool = False
    ) -> Dict[str, Any]:
        """
        Analyzes the conversation history to determine if we have enough info 
        to build a campaign, or if we need to ask clarifying questions.
        
        Args:
            campaign_id (str): UUID of the campaign (for logging).
            conversation_history (list): List of {"role": "...", "content": "..."} dicts.
            slots (dict): ICP/search parameters (location, industry, titles, etc.)
            business_profile (dict): Organization context (name, services, tone, etc.)
            use_combined_prompt (bool): If True, uses CAMPAIGN_CLARIFICATION_PROMPT_COMBINED (Option 2)
                                       If False, uses CAMPAIGN_CLARIFICATION_PROMPT (Option 1)

        Returns:
            dict: The JSON response parsed from the LLM (status, context/questions).
        """
        logger.info(f"CampaignService: Clarifying intent for campaign {campaign_id}")

        # Build pre-populated context from slots and business profile
        pre_populated_context = self._build_prepopulated_context(slots, business_profile)

        # Choose prompt based on option
        system_prompt = CAMPAIGN_CLARIFICATION_PROMPT_COMBINED if use_combined_prompt else CAMPAIGN_CLARIFICATION_PROMPT

        # 1. Prepare Messages
        messages = [
            {"role": "system", "content": system_prompt},
        ]
        
        # Add pre-populated context as a system message if available
        if pre_populated_context:
            context_message = self._format_prepopulated_context(pre_populated_context)
            messages.append({"role": "system", "content": context_message})
        
        # Append conversation context
        for msg in conversation_history:
             if msg.get("content"):
                 messages.append({"role": msg.get("role"), "content": msg.get("content")})

        # 2. Call LLM
        try:
            response_text = self.llm_client.get_completion(
                messages=messages,
                model="gpt-4o-mini",
                temperature=0.0,
                max_tokens=300,
                json_mode=True
            )
            
            parsed_response = json.loads(response_text)
            
            # Merge pre-populated context into the response if ready for generation
            if parsed_response.get("status") == "ready_for_generation":
                context = parsed_response.get("context", {})
                # Fill in any missing fields with pre-populated values
                for key, value in pre_populated_context.items():
                    if not context.get(key):
                        context[key] = value
                parsed_response["context"] = context
            
        except json.JSONDecodeError:
            logger.error(f"CampaignService: Failed to parse JSON from LLM: {response_text}")
            return {
                "status": "needs_clarification",
                "missing_fields": ["unknown_error"],
                "questions": [{"field": "general", "question": "I'm having trouble processing that. Could you start over with your goal?"}]
            }
        except Exception as e:
            logger.error(f"CampaignService: LLM Error: {e}", exc_info=True)
            return {
                "status": "needs_clarification",
                "missing_fields": ["unknown_error"],
                "questions": [{"field": "general", "question": "I'm having trouble right now. Please try again in a moment."}]
            }

        # 3. Log to ML Tables (Fire and Forget)
        threading.Thread(
            target=self._log_ml_interaction,
            args=(campaign_id, conversation_history, parsed_response),
            daemon=True,
        ).start()
        return parsed_response

    def _build_prepopulated_context(self, slots: Dict = None, business_profile: Dict = None) -> Dict:
        """
        Builds pre-populated context from ICP slots and business profile.
        This reduces the number of questions needed.
        """
        context = {}
        
        if not slots:
            slots = {}
        if not business_profile:
            business_profile = {}
        
        # 1. Auto-populate Target Audience from slots
        target_parts = []
        
        # Extract titles
        titles = slots.get("title") or slots.get("titles") or slots.get("person_titles", [])
        if isinstance(titles, list) and titles:
            if len(titles) == 1:
                target_parts.append(titles[0])
            elif len(titles) <= 3:
                target_parts.append(", ".join(titles))
            else:
                target_parts.append(f"{titles[0]} and similar roles")
        elif isinstance(titles, str) and titles:
            target_parts.append(titles)
        
        # Extract industry
        industry = slots.get("industry") or slots.get("industries", [])
        if isinstance(industry, list) and industry:
            target_parts.append(f"at {industry[0]} companies")
        elif isinstance(industry, str) and industry:
            target_parts.append(f"at {industry} companies")
        
        # Extract location
        location = slots.get("location") or slots.get("locations") or slots.get("person_locations", [])
        if isinstance(location, list) and location:
            target_parts.append(f"in {location[0]}")
        elif isinstance(location, str) and location:
            target_parts.append(f"in {location}")
        
        if target_parts:
            context["target_audience"] = " ".join(target_parts)
        else:
            context["target_audience"] = "decision-makers at target companies"
        
        # 2. Auto-populate Tone from business profile
        tone = business_profile.get("tone_preferences") or business_profile.get("brand_voice")
        if tone:
            if isinstance(tone, dict):
                # If tone_preferences is a dict, extract a reasonable value
                context["tone"] = tone.get("primary") or tone.get("default") or "Professional"
            else:
                context["tone"] = str(tone)
        else:
            context["tone"] = "Professional and conversational"
        
        # 3. Auto-populate Value Proposition from business profile
        services = business_profile.get("services", [])
        description = business_profile.get("description", "")
        
        if services and isinstance(services, list) and len(services) > 0:
            if len(services) == 1:
                context["value_proposition"] = services[0]
            else:
                context["value_proposition"] = f"{services[0]} and related services"
        elif description:
            # Use first sentence of description
            first_sentence = description.split('.')[0] if '.' in description else description
            context["value_proposition"] = first_sentence[:150]  # Limit length
        else:
            context["value_proposition"] = "our solutions and services"
        
        # 4. DO NOT set default follow-up logic - always ask user
        # This field should be explicitly confirmed by the user during campaign creation
        
        # 5. Add business name for reference
        if business_profile.get("name"):
            context["business_name"] = business_profile.get("name")
        
        return context

    def _format_prepopulated_context(self, context: Dict) -> str:
        """
        Formats the pre-populated context as a system message for the LLM.
        """
        parts = ["**Pre-populated Context (use these as defaults):**"]
        
        if context.get("target_audience"):
            parts.append(f"- Target Audience: {context['target_audience']}")
        if context.get("tone"):
            parts.append(f"- Tone: {context['tone']}")
        if context.get("value_proposition"):
            parts.append(f"- Value Proposition: {context['value_proposition']}")
        if context.get("follow_up_logic"):
            parts.append(f"- Follow-up Logic: {context['follow_up_logic']}")
        if context.get("business_name"):
            parts.append(f"- Business Name: {context['business_name']}")
        
        parts.append("\nUse these values unless the user explicitly wants to change them.")
        
        return "\n".join(parts)

    def _log_ml_interaction(self, campaign_id: str, history: List[Dict], result: Dict):
        """
        Logs the conversation and extraction result to ML internal tables.
        """
        try:
            # log conversation snapshot
            MLConversation.objects.create(
                campaign_id=campaign_id,
                messages=history,
                current_stage=result.get("status", "unknown"),
                model_version=""
            )

            # log context extraction
            c_score = 1.0 if result.get("status") == "ready_for_generation" else 0.0

            MLCampaignContext.objects.create(
                campaign_id=campaign_id,
                extracted_fields=result.get("context", {}),
                missing_fields=result.get("missing_fields", []),
                confidence_map={}, # Placeholder for now
                completeness_score=c_score
            )
        except Exception as e:
            logger.error(f"CampaignService: Failed to log ML interaction: {e}")

    def generate_campaign(self, campaign_id: str, context: Dict) -> Dict:
        """
        Generates a linear campaign sequence based on confirmed context.
        Persists to campaign_steps and campaign_emails.
        Logs to ml_generations.
        """
        logger.info(f"CampaignService: Generating campaign {campaign_id}")

        # 1. Prepare Prompt
        prompt = CAMPAIGN_GENERATION_PROMPT

        goal=context.get("goal", "")
        target_audience=context.get("target_audience", "")
        tone=context.get("tone", "")
        value_proposition=context.get("value_proposition", "")
        follow_up=context.get("follow_up_logic", "") or context.get("follow_up", "")

        user_content = f"Goal: {goal}\nTarget Audience: {target_audience}\nTone: {tone}\nValue Proposition: {value_proposition}\nFollow-up: {follow_up}"

        messages = [
            {"role": "system", "content": prompt},
            {"role": "user", "content": user_content}
        ]

        # 2. Call LLM
        try:
            response_text = self.llm_client.get_completion(
                messages=messages,
                model="gpt-4o-mini",   # ← was gpt-5.2 (heavy), now fast model
                temperature=0.7,        # ← was 1.0, lowered for faster/stable output
                json_mode=True
            )
            # Sanitize response
            if "```" in response_text:
                response_text = response_text.replace("```json", "").replace("```", "").strip()

            # print(f"DEBUG LLM Raw Pre-Load: {response_text}")
            parsed_data = json.loads(response_text)
            # print(f"DEBUG LLM Raw: {response_text}")
            # print(f"DEBUG Parsed keys: {parsed_data.keys() if isinstance(parsed_data, dict) else 'Not a dict'}")

        except Exception as e:
            logger.warning(f"CampaignService: Primary generation failed, retrying with fallback prompt: {e}")
            try:
                fallback_messages = [
                    {"role": "system", "content": CAMPAIGN_GENERATION_FALLBACK_PROMPT},
                    {"role": "user", "content": user_content}
                ]
                response_text = self.llm_client.get_completion(
                    messages=fallback_messages,
                    model="gpt-4o-mini",
                    temperature=0.3,
                    json_mode=True
                )
                if "```" in response_text:
                    response_text = response_text.replace("```json", "").replace("```", "").strip()
                parsed_data = json.loads(response_text)
                logger.info("CampaignService: Fallback generation succeeded")
            except Exception as e2:
                logger.error(f"CampaignService: Fallback generation also failed: {e2}", exc_info=True)
                raise e2

        # Log to ML table
        steps = parsed_data.get("steps", [])
        if not steps:
            raise ValueError("LLM returned no campaign steps")
        # #steporder
        # for step in parsed_data.get("steps", []):
        #     step["steps"] = f"step_{step.get('step_order', 0)}"
        for i, step in enumerate(parsed_data.get("steps", [])):
            ordered = {"step_order": step["step_order"], "steps": f"step_{step['step_order']}"}
            ordered.update({k: v for k, v in step.items() if k != "step_order"})
            parsed_data["steps"][i] = ordered

        for i, step in enumerate(steps):
            email = step.get("email", {})
            if not email.get("subject") or not email.get("body"):
                raise ValueError(f"Step {i + 1} missing email subject or body")

        # Log to ML table
        # self._log_generation(campaign_id, prompt, parsed_data, "campaign")
        threading.Thread(
            target=self._log_generation,
            args=(campaign_id, prompt, parsed_data, "campaign"),
            daemon=True,
        ).start()

        return parsed_data
    
    def generate_email_draft(self, campaign_context: Dict, step_context: Dict, instructions: str, template_id: str = None) -> Dict:
        """
        Generates a specific email draft (Subject + Body) based on instructions.
        If template_id is provided, uses that template (rendered with context data) as the system prompt.
        """
        if template_id:
            from .ai_prompt_template_service import AIPromptTemplateService
            merged = {**(campaign_context or {}), **(step_context or {})}
            built = AIPromptTemplateService.build_context(template_id, merged)
            prompt = built["rendered_prompt"] if built else EMAIL_GENERATION_PROMPT
        else:
            prompt = EMAIL_GENERATION_PROMPT

        user_content = f"Campaign Context: {campaign_context}\nStep Context: {step_context}\nInstructions: {instructions}"

        messages = [
            {"role": "system", "content": prompt},
            {"role": "user", "content": user_content}
        ]

        try:
            response_text = self.llm_client.get_completion(
                messages=messages,
                model=self.model,
                temperature=0.7,
                json_mode=True
            )

            # Sanitize response
            if "```" in response_text:
                response_text = response_text.replace("```json", "").replace("```", "").strip()

            parsed_data = json.loads(response_text)

            # Validate
            if not parsed_data.get("subject") or not parsed_data.get("body"):
                raise ValueError("LLM failed to generate complete email (missing subject or body)")

        except Exception as e:
            logger.warning(f"CampaignService: Primary email generation failed, retrying with fallback prompt: {e}")
            try:
                fallback_messages = [
                    {"role": "system", "content": EMAIL_GENERATION_FALLBACK_PROMPT},
                    {"role": "user", "content": user_content}
                ]
                response_text = self.llm_client.get_completion(
                    messages=fallback_messages,
                    model=self.model,
                    temperature=0.3,
                    json_mode=True
                )
                if "```" in response_text:
                    response_text = response_text.replace("```json", "").replace("```", "").strip()
                parsed_data = json.loads(response_text)
                if not parsed_data.get("subject") or not parsed_data.get("body"):
                    raise ValueError("Fallback email generation returned incomplete output")
                logger.info("CampaignService: Fallback email generation succeeded")
            except Exception as e2:
                logger.error(f"CampaignService: Fallback email generation also failed: {e2}", exc_info=True)
                raise e2

        # Async Log to ML Table (Fire and Forget)
        campaign_id = campaign_context.get("id") or campaign_context.get("campaign_id")
        if campaign_id:
            threading.Thread(
                target=self._log_generation,
                args=(campaign_id, prompt, parsed_data, "email"),
                daemon=True,
            ).start()
        return parsed_data

    def analyze_spam_risk(self, subject: str, body: str, email_id: str = None) -> Dict:
        """
        Analyzes an email for spam risk using LLM.
        Returns score, risk factors, and recommendations.
        If email_id is provided, persists result to MLSpamAnalysis.
        """
        prompt = EMAIL_SPAM_SCORE

        user_content = f"Email Subject: {subject}\nEmail Body: {body}"

        messages = [
            {"role": "system", "content": prompt},
            {"role": "user", "content": user_content}
        ]

        try:
            response_text = self.llm_client.get_completion(
                messages=messages,
                model=self.model,
                temperature=0.0,  # Deterministic for analysis
                json_mode=True
            )

            # Sanitize response
            if "```" in response_text:
                response_text = response_text.replace("```json", "").replace("```", "").strip()

            parsed_data = json.loads(response_text)

            # Validate required fields
            required_fields = ["provider", "score", "risk_factors", "recommendations"]
            for field in required_fields:
                if field not in parsed_data:
                    raise ValueError(f"Missing required field: {field}")

            # Persist to MLSpamAnalysis
            if email_id:
                try:
                    email_instance = CampaignEmail.objects.get(id=email_id)
                    MLSpamAnalysis.objects.create(
                        email=email_instance,
                        provider=parsed_data.get("provider"),
                        raw_response=parsed_data,
                        normalized_score=parsed_data.get("score"),
                        risk_factors=parsed_data.get("risk_factors")
                    )
                except CampaignEmail.DoesNotExist:
                    logger.warning(f"CampaignService: Email ID {email_id} not found. Skipping spam persistence.")
                except Exception as e:
                    logger.warning(f"Failed to persist Spam Analysis: {e}")
            else:
                 logger.info("CampaignService: No email_id provided. Skipping spam persistence.")

            return parsed_data

        except json.JSONDecodeError as e:
            logger.error(f"CampaignService: Spam Analysis JSON Error: {e}")
            raise ValueError("Failed to parse spam analysis response")
        except Exception as e:
            logger.error(f"CampaignService: Spam Analysis Failed: {e}", exc_info=True)
            raise e


    def _log_generation(self, campaign_id: str, prompt: str, output: Dict, generation_type: str = "campaign", status_note: str = ""):
        """
        Logs a generation event to MLGeneration.
        """
        try:
             MLGeneration.objects.create(
                 campaign_id=campaign_id,
                 type=generation_type,
                 prompt={"text": prompt},
                 output=output,
                 model_version=self.model
             )
        except Exception as e:
             logger.warning(f"Failed to log generation: {e}")

    def generate_subject_line(self, campaign_context: Dict, lead_attributes: Dict, instructions: str = "", template_id: str = None) -> str:
        """
        Generates a single AI subject line based on campaign context and lead attributes.
        One GPT call. Returns a plain string.
        If template_id is provided, uses that template (rendered with context data) as the system prompt.
        """
        if template_id:
            from .ai_prompt_template_service import AIPromptTemplateService
            merged = {**(campaign_context or {}), **(lead_attributes or {})}
            built = AIPromptTemplateService.build_context(template_id, merged)
            prompt = built["rendered_prompt"] if built else SUBJECT_LINE_GENERATION_PROMPT
        else:
            prompt = SUBJECT_LINE_GENERATION_PROMPT

        user_content = (
            f"Campaign Context: {json.dumps(campaign_context)}\n"
            f"Lead Attributes: {json.dumps(lead_attributes)}\n"
            f"Instructions: {instructions}"
        )

        messages = [
            {"role": "system", "content": prompt},
            {"role": "user", "content": user_content},
        ]

        try:
            response_text = self.llm_client.get_completion(
                messages=messages,
                model=self.model,
                temperature=0.8,
                json_mode=True,
            )

            if "```" in response_text:
                response_text = response_text.replace("```json", "").replace("```", "").strip()

            parsed = json.loads(response_text)
            subject = parsed.get("subject", "").strip()

            if not subject:
                raise ValueError("LLM returned empty subject line")

            return subject

        except Exception as e:
            logger.error(f"CampaignService: Subject Line Generation Failed: {e}", exc_info=True)
            raise e

    def generate_reply(self, original_email: Dict, prospect_reply: str,
                       campaign_context: Dict = None, lead_info: Dict = None,
                       tone: str = "professional", instructions: str = "") -> Dict:
        """
        Generates an AI reply to a prospect's response to a campaign email.
        """
        prompt = REPLY_GENERATION_PROMPT

        user_content = (
            f"Original Email: {json.dumps(original_email)}\n"
            f"Prospect Reply: {prospect_reply}\n"
            f"Campaign Context: {json.dumps(campaign_context or {})}\n"
            f"Lead Info: {json.dumps(lead_info or {})}\n"
            f"Tone: {tone}\n"
            f"Instructions: {instructions}"
        )

        messages = [
            {"role": "system", "content": prompt},
            {"role": "user", "content": user_content},
        ]

        try:
            response_text = self.llm_client.get_completion(
                messages=messages,
                model=self.model,
                temperature=0.9,
                json_mode=True,
            )

            if "```" in response_text:
                response_text = response_text.replace("```json", "").replace("```", "").strip()

            parsed = json.loads(response_text)

            if not parsed.get("body"):
                raise ValueError("LLM failed to generate reply body")

            campaign_id = campaign_context.get("id") or campaign_context.get(
                "campaign_id") if campaign_context else None
            if campaign_id:
                threading.Thread(
                    target=self._log_generation,
                    args=(campaign_id, prompt, parsed, "reply"),
                    daemon=True,
                ).start()

            return parsed

        except Exception as e:
            logger.error(f"CampaignService: Reply Generation Failed: {e}", exc_info=True)
            raise e

    def understand_reply(self, prospect_reply: str, original_email: Dict = None,
                         campaign_context: Dict = None, lead_info: Dict = None) -> Dict:
        """
        Uses LLM to deeply interpret the meaning and intent of a prospect's reply.
        Returns structured analysis: intent, sentiment, urgency, topics, questions, objections, etc.
        """
        user_content = (
            f"Prospect Reply: {prospect_reply}\n"
            f"Original Email: {json.dumps(original_email or {})}\n"
            f"Campaign Context: {json.dumps(campaign_context or {})}\n"
            f"Lead Info: {json.dumps(lead_info or {})}"
        )

        messages = [
            {"role": "system", "content": REPLY_UNDERSTANDING_PROMPT},
            {"role": "user", "content": user_content},
        ]

        try:
            response_text = self.llm_client.get_completion(
                messages=messages,
                model=self.model,
                temperature=0.0,
                json_mode=True,
            )

            if "```" in response_text:
                response_text = response_text.replace("```json", "").replace("```", "").strip()

            return json.loads(response_text)

        except Exception as e:
            logger.error(f"CampaignService: Reply Understanding Failed: {e}", exc_info=True)
            raise e

    def generate_contextual_followup(
        self,
        thread_messages: List[Dict],
        campaign_context: Dict = None,
        lead_info: Dict = None,
        tone: str = "professional",
        instructions: str = "",
    ) -> Dict[str, Any]:
        """
        Generates a context-aware follow-up email using the thread history passed inline.
        The LLM sees every prior outbound email and inbound reply so it never
        repeats itself and can address prospect objections.

        Args:
            thread_messages: List of dicts with keys: direction, subject, body, sent_at
                             direction is "outbound" (we sent) or "inbound" (prospect replied)

        Returns:
            dict: {"subject": "...", "body": "...", "reasoning": "..."}
        """
        if not thread_messages:
            raise ValueError("thread_messages is required and cannot be empty.")

        thread_text = self._format_thread_for_llm(thread_messages)

        user_content = (
            f"Thread History:\n{thread_text}\n\n"
            f"Campaign Context: {json.dumps(campaign_context or {})}\n"
            f"Lead Info: {json.dumps(lead_info or {})}\n"
            f"Tone: {tone}\n"
            f"Instructions: {instructions}"
        )

        messages = [
            {"role": "system", "content": CONTEXTUAL_FOLLOWUP_PROMPT},
            {"role": "user", "content": user_content},
        ]

        try:
            response_text = self.llm_client.get_completion(
                messages=messages,
                model=self.model,
                temperature=0.8,
                json_mode=True,
            )

            if "```" in response_text:
                response_text = response_text.replace("```json", "").replace("```", "").strip()

            parsed = json.loads(response_text)

            if not parsed.get("body"):
                raise ValueError("LLM returned empty follow-up body")

            return parsed

        except Exception as e:
            logger.error(f"CampaignService: Contextual follow-up generation failed: {e}", exc_info=True)
            raise e

    def _format_thread_for_llm(self, messages: List[Dict]) -> str:
        """Formats thread messages into a readable block for the LLM prompt."""
        lines = []
        for i, msg in enumerate(messages, 1):
            direction_label = "US (outbound)" if msg.get("direction") == "outbound" else "PROSPECT (inbound)"
            lines.append(f"--- Message {i} [{direction_label}] @ {msg.get('sent_at', '')} ---")
            if msg.get("subject"):
                lines.append(f"Subject: {msg['subject']}")
            lines.append(f"Body:\n{msg.get('body', '')}")
            lines.append("")
        return "\n".join(lines)
