from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict
import uuid


@dataclass
class DomainEvent:
    event_type: str
    payload: Dict[str, Any] = field(default_factory=dict)
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    occurred_at: datetime = field(default_factory=datetime.utcnow)
    tenant_id: str = ""


# Known event types
class EventTypes:
    SCAN_COMPLETED = "scan.completed"
    DIAGNOSIS_CREATED = "diagnosis.created"
    ACTION_DECIDED = "action.decided"
    ACTION_EXECUTED = "action.executed"
    ACTION_FAILED = "action.failed"
    REPORT_SENT = "report.sent"
