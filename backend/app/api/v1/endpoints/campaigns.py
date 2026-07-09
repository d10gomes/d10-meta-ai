from typing import List, Optional
from pydantic import BaseModel
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import get_current_user
from app.db.models import User, Campaign, MetaAccount
from app.db.session import get_db

router = APIRouter()


class CampaignOut(BaseModel):
    id: str
    meta_campaign_id: str
    name: str | None
    status: str | None
    objective: str | None
    daily_budget: float | None


@router.get("/", response_model=List[CampaignOut])
async def list_campaigns(
    account_id: Optional[str] = Query(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    q = (
        select(Campaign)
        .join(MetaAccount, Campaign.meta_account_id == MetaAccount.id)
        .where(MetaAccount.tenant_id == current_user.tenant_id)
    )
    if account_id:
        q = q.where(Campaign.meta_account_id == account_id)
    result = await db.execute(q.limit(500))
    campaigns = result.scalars().all()
    return [CampaignOut(
        id=str(c.id), meta_campaign_id=c.meta_campaign_id,
        name=c.name, status=c.status, objective=c.objective,
        daily_budget=c.daily_budget,
    ) for c in campaigns]
