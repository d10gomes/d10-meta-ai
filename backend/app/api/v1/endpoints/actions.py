from typing import List
from pydantic import BaseModel
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import get_current_user
from app.db.models import User
from app.db.session import get_db
from app.infrastructure.repositories.diagnosis_repository import DiagnosisRepository

router = APIRouter()


class ActionOut(BaseModel):
    id: str
    action_type: str
    entity_type: str | None
    entity_id: str | None
    status: str
    executed_at: str | None
    created_at: str


@router.get("/", response_model=List[ActionOut])
async def list_actions(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    repo = DiagnosisRepository(db)
    items = await repo.get_actions_by_tenant(str(current_user.tenant_id))
    return [ActionOut(
        id=str(a.id), action_type=a.action_type, entity_type=a.entity_type,
        entity_id=a.entity_id, status=a.status,
        executed_at=a.executed_at.isoformat() if a.executed_at else None,
        created_at=a.created_at.isoformat(),
    ) for a in items]
