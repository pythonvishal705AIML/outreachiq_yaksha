from dataclasses import dataclass, field
from typing import Any


@dataclass
class AgentMessageResponse:
    reply: str
    current_flow: str | None = None
    past_flows: list[Any] = field(default_factory=list)
    future_flows: list[Any] = field(default_factory=list)
    campaign_status: str | None = None
    campaign_context: dict[str, Any] = field(default_factory=dict)
    slots: dict[str, Any] = field(default_factory=dict)
