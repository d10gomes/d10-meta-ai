from dataclasses import dataclass, field
from typing import Any, Dict, Optional
from enum import Enum


class ActionType(str, Enum):
    PAUSE_AD = "PAUSE_AD"
    ACTIVATE_AD = "ACTIVATE_AD"
    PAUSE_ADSET = "PAUSE_ADSET"
    ACTIVATE_ADSET = "ACTIVATE_ADSET"
    PAUSE_CAMPAIGN = "PAUSE_CAMPAIGN"
    SCALE_BUDGET_UP = "SCALE_BUDGET_UP"
    SCALE_BUDGET_DOWN = "SCALE_BUDGET_DOWN"
    DUPLICATE_CAMPAIGN = "DUPLICATE_CAMPAIGN"


@dataclass
class AgentAction:
    action_type: ActionType
    entity_type: str
    entity_id: str
    payload: Dict[str, Any] = field(default_factory=dict)
    tenant_id: Optional[str] = None
    rationale: Optional[str] = None
