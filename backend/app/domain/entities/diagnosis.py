from dataclasses import dataclass, field
from typing import Any, Dict, Optional
from enum import Enum


class IssueSeverity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class IssueType(str, Enum):
    LOW_CTR = "LOW_CTR"
    HIGH_CPA = "HIGH_CPA"
    HIGH_FREQUENCY = "HIGH_FREQUENCY"
    NO_CONVERSIONS = "NO_CONVERSIONS"
    CREATIVE_SATURATION = "CREATIVE_SATURATION"
    LOW_ROAS = "LOW_ROAS"
    HIGH_CPM = "HIGH_CPM"
    BUDGET_EXHAUSTED = "BUDGET_EXHAUSTED"


@dataclass
class Diagnosis:
    entity_type: str
    entity_id: str
    issue_type: IssueType
    severity: IssueSeverity
    details: Dict[str, Any] = field(default_factory=dict)
    tenant_id: Optional[str] = None
