from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import get_current_user
from app.db.models import User
from app.db.session import get_db
from app.agents.creative.service import CreativeService

router = APIRouter()


@router.get("/{meta_account_id}")
async def rank_creatives(
    meta_account_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    svc = CreativeService(db)
    return await svc.rank_creatives(meta_account_id)
