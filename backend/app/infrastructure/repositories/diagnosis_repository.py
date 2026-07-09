from typing import List
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Diagnosis, AgentAction, AgentEvent


class DiagnosisRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def save_diagnosis(self, data: dict) -> Diagnosis:
        obj = Diagnosis(**data)
        self._session.add(obj)
        await self._session.flush()
        return obj

    async def get_open_by_tenant(self, tenant_id: str) -> List[Diagnosis]:
        result = await self._session.execute(
            select(Diagnosis).where(
                Diagnosis.tenant_id == tenant_id,
                Diagnosis.resolved == False,
            ).order_by(Diagnosis.created_at.desc())
        )
        return list(result.scalars().all())

    async def save_action(self, data: dict) -> AgentAction:
        obj = AgentAction(**data)
        self._session.add(obj)
        await self._session.flush()
        return obj

    async def save_event(self, data: dict) -> AgentEvent:
        obj = AgentEvent(**data)
        self._session.add(obj)
        await self._session.flush()
        return obj

    async def get_actions_by_tenant(self, tenant_id: str, limit: int = 50) -> List[AgentAction]:
        result = await self._session.execute(
            select(AgentAction)
            .where(AgentAction.tenant_id == tenant_id)
            .order_by(AgentAction.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())
