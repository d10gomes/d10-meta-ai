"""Executor Agent — executes actions on Meta Ads API."""
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import logger
from app.db.models import AgentAction, Ad, Campaign
from app.domain.entities.action import ActionType
from app.domain.events.base import DomainEvent, EventTypes
from app.domain.events.bus import publish
from app.infrastructure.meta_api.client import MetaAdsClient
from app.infrastructure.repositories.meta_account_repository import MetaAccountRepository


class ExecutorService:
    def __init__(self, session: AsyncSession):
        self._session = session
        self._account_repo = MetaAccountRepository(session)

    async def execute_pending(self, tenant_id: str):
        result = await self._session.execute(
            select(AgentAction).where(
                AgentAction.tenant_id == tenant_id,
                AgentAction.status == "pending",
            ).limit(50)
        )
        actions = list(result.scalars().all())
        for action in actions:
            await self.execute(str(action.id))

    async def execute(self, action_id: str):
        result = await self._session.execute(
            select(AgentAction).where(AgentAction.id == action_id)
        )
        action = result.scalar_one_or_none()
        if not action:
            return

        try:
            client = await self._get_client_for_entity(action)
            await self._dispatch(action, client)
            action.status = "executed"
            action.executed_at = datetime.utcnow()
            await self._session.flush()
            await publish(DomainEvent(
                event_type=EventTypes.ACTION_EXECUTED,
                tenant_id=str(action.tenant_id),
                payload={"action_id": action_id, "action_type": action.action_type},
            ))
            logger.info("executor.executed", action_id=action_id, type=action.action_type)
        except Exception as exc:
            action.status = "failed"
            action.error = str(exc)
            await self._session.flush()
            await publish(DomainEvent(
                event_type=EventTypes.ACTION_FAILED,
                tenant_id=str(action.tenant_id),
                payload={"action_id": action_id, "error": str(exc)},
            ))
            logger.error("executor.failed", action_id=action_id, error=str(exc))

    async def _dispatch(self, action: AgentAction, client: MetaAdsClient):
        a = action.action_type
        eid = action.entity_id

        if a == ActionType.PAUSE_AD.value:
            await client.update_ad_status(eid, "PAUSED")
        elif a == ActionType.ACTIVATE_AD.value:
            await client.update_ad_status(eid, "ACTIVE")
        elif a == ActionType.SCALE_BUDGET_UP.value:
            await self._scale_budget(client, action, 1.20)
        elif a == ActionType.SCALE_BUDGET_DOWN.value:
            await self._scale_budget(client, action, 0.80)
        elif a == ActionType.DUPLICATE_CAMPAIGN.value:
            await client.duplicate_campaign(eid)
        else:
            logger.warning("executor.unknown_action", action_type=a)

    async def _scale_budget(self, client: MetaAdsClient, action: AgentAction, factor: float):
        result = await self._session.execute(
            select(Campaign).where(Campaign.meta_campaign_id == action.entity_id)
        )
        campaign = result.scalar_one_or_none()
        if not campaign or not campaign.daily_budget:
            return
        new_budget = int(campaign.daily_budget * factor * 100)  # in cents
        await client.update_campaign_budget(action.entity_id, new_budget)
        campaign.daily_budget = campaign.daily_budget * factor
        await self._session.flush()

    async def _get_client_for_entity(self, action: AgentAction) -> MetaAdsClient:
        accounts = await self._account_repo.get_by_tenant(str(action.tenant_id))
        if not accounts:
            raise ValueError("No Meta accounts found for tenant")
        acc = accounts[0]
        return MetaAdsClient(acc.access_token, acc.ad_account_id)
