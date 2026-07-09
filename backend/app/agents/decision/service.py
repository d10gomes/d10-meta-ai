"""Decision Agent — transforms diagnoses into actions."""
from typing import List

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import logger
from app.domain.entities.action import AgentAction, ActionType
from app.domain.entities.diagnosis import Diagnosis, IssueType, IssueSeverity
from app.domain.events.base import DomainEvent, EventTypes
from app.domain.events.bus import publish
from app.infrastructure.repositories.diagnosis_repository import DiagnosisRepository


ISSUE_TO_ACTION: dict = {
    IssueType.NO_CONVERSIONS: ActionType.PAUSE_AD,
    IssueType.LOW_CTR: ActionType.PAUSE_AD,
    IssueType.HIGH_CPA: ActionType.SCALE_BUDGET_DOWN,
    IssueType.HIGH_FREQUENCY: ActionType.PAUSE_AD,
    IssueType.CREATIVE_SATURATION: ActionType.DUPLICATE_CAMPAIGN,
    IssueType.LOW_ROAS: ActionType.SCALE_BUDGET_DOWN,
    IssueType.HIGH_CPM: ActionType.SCALE_BUDGET_DOWN,
}

# Only auto-execute for CRITICAL/HIGH severity; LOW/MEDIUM need human approval
AUTO_EXECUTE_SEVERITIES = {IssueSeverity.CRITICAL, IssueSeverity.HIGH}


class DecisionService:
    def __init__(self, session: AsyncSession):
        self._session = session
        self._repo = DiagnosisRepository(session)

    async def decide(self, diagnoses: List[Diagnosis]) -> List[AgentAction]:
        actions: List[AgentAction] = []

        for diagnosis in diagnoses:
            action_type = ISSUE_TO_ACTION.get(diagnosis.issue_type)
            if not action_type:
                continue

            payload = self._build_payload(diagnosis, action_type)
            action = AgentAction(
                action_type=action_type,
                entity_type=diagnosis.entity_type,
                entity_id=diagnosis.entity_id,
                payload=payload,
                tenant_id=diagnosis.tenant_id,
                rationale=f"Auto-decision from diagnosis: {diagnosis.issue_type.value}",
            )
            actions.append(action)

            status = "pending"
            if diagnosis.severity in AUTO_EXECUTE_SEVERITIES:
                status = "pending"  # Executor will pick it up immediately

            await self._repo.save_action({
                "tenant_id": diagnosis.tenant_id,
                "action_type": action_type.value,
                "entity_type": action.entity_type,
                "entity_id": action.entity_id,
                "payload": payload,
                "status": status,
            })

            await publish(DomainEvent(
                event_type=EventTypes.ACTION_DECIDED,
                tenant_id=diagnosis.tenant_id or "",
                payload={
                    "action_type": action_type.value,
                    "entity_id": action.entity_id,
                    "severity": diagnosis.severity.value,
                },
            ))

        logger.info("decision.done", actions=len(actions))
        return actions

    def _build_payload(self, diagnosis: Diagnosis, action_type: ActionType) -> dict:
        payload = {"diagnosis_details": diagnosis.details}
        if action_type == ActionType.SCALE_BUDGET_DOWN:
            payload["budget_change_pct"] = -20
        elif action_type == ActionType.SCALE_BUDGET_UP:
            payload["budget_change_pct"] = 20
        return payload
