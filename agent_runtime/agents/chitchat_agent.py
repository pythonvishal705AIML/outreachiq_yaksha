from api.models import BusinessProfile
from api.services.chit_chat_handler import BrandChitChatHandler
from agent_runtime.clients.streaming import stream_completion
from api.prompts import CHIT_CHAT_PROMPT_TEMPLATE


class ChitChatAgent:
    def __init__(self, session):
        self.session = session
        try:
            profile = BusinessProfile.objects.get(account_id=session.tenant_id)
            brand_name = profile.name or "Your Assistant"
            brand_tone = profile.tone_preferences or "friendly"
        except BusinessProfile.DoesNotExist:
            brand_name = "Your Assistant"
            brand_tone = "friendly"
        self.handler = BrandChitChatHandler(brand_name=brand_name, brand_tone=brand_tone)
        self._brand_name = brand_name
        self._brand_tone = brand_tone if isinstance(brand_tone, str) else ", ".join(brand_tone)

    def handle(self, user_text: str, history: list[dict], agent_log=None) -> dict:
        if agent_log:
            agent_log.log_action(actor="chit_chat_agent", action="respond")
        text = self.handler.respond(user_text, history=history)
        return {
            "text": text or "Hi! How can I help you today?",
            "current_flow": "chit_chat",
            "past_flows": [],
            "future_flows": [],
        }

    def handle_stream(self, user_text: str, history: list[dict], agent_log=None):
        """
        Generator: yields text chunks as LLM generates them.
        Final yield is the full result dict.
        """
        system_prompt = CHIT_CHAT_PROMPT_TEMPLATE.format(
            brand_name=self._brand_name,
            brand_tone=self._brand_tone,
        )
        messages = [{"role": "system", "content": system_prompt}]
        if history:
            messages.extend(history)
        else:
            messages.append({"role": "user", "content": user_text})

        if agent_log:
            agent_log.log_llm_call(actor="chit_chat_agent", model="gpt-4o-mini")

        full_text = ""
        try:
            for chunk in stream_completion(messages, temperature=0.7, max_tokens=100):
                full_text += chunk
                yield {"type": "token", "text": chunk}
        except Exception as e:
            if agent_log:
                agent_log.log_error(actor="chit_chat_agent", error=str(e))
            full_text = full_text or f"Hello! I'm here to help you with {self._brand_name}."
            yield {"type": "token", "text": full_text}

        yield {
            "type": "result",
            "data": {
                "text": full_text,
                "current_flow": "chit_chat",
                "past_flows": [],
                "future_flows": [],
            },
        }
