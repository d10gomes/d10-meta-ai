from typing import List, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import MetaAccount


class MetaAccountRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def get_by_id(self, account_id: str) -> Optional[MetaAccount]:
        result = await self._session.execute(
            select(MetaAccount).where(MetaAccount.id == account_id)
        )
        return result.scalar_one_or_none()

    async def get_all_active(self) -> List[MetaAccount]:
        result = await self._session.execute(
            select(MetaAccount).where(MetaAccount.is_active == True)
        )
        return list(result.scalars().all())

    async def get_by_tenant(self, tenant_id: str) -> List[MetaAccount]:
        result = await self._session.execute(
            select(MetaAccount).where(
                MetaAccount.tenant_id == tenant_id,
                MetaAccount.is_active == True,
            )
        )
        return list(result.scalars().all())

    async def count_by_tenant(self, tenant_id: str) -> int:
        result = await self._session.execute(
            select(MetaAccount).where(MetaAccount.tenant_id == tenant_id)
        )
        return len(result.scalars().all())

    async def save(self, account: MetaAccount) -> MetaAccount:
        self._session.add(account)
        await self._session.flush()
        return account

    async def delete(self, account: MetaAccount):
        await self._session.delete(account)
        await self._session.flush()
