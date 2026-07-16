from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import get_current_user
from app.db.models import User, AgentAction
from app.db.session import get_db
from app.infrastructure.repositories.diagnosis_repository import DiagnosisRepository

router = APIRouter()


class ActionOut(BaseModel):
    id: str
    action_type: str
    entity_type: str | None
    entity_id: str | None
    status: str
    requires_approval: bool
    payload: dict | None
    executed_at: str | None
    approved_at: str | None
    error: str | None
    created_at: str


@router.get("/", response_model=List[ActionOut])
async def list_actions(
    pending_only: bool = Query(False),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    q = (
        select(AgentAction)
        .where(AgentAction.tenant_id == current_user.tenant_id)
        .order_by(AgentAction.created_at.desc())
        .limit(100)
    )
    if pending_only:
        q = q.where(
            AgentAction.requires_approval == True,
            AgentAction.status == "pending",
        )
    result = await db.execute(q)
    items = result.scalars().all()
    return [ActionOut(
        id=str(a.id),
        action_type=a.action_type,
        entity_type=a.entity_type,
        entity_id=a.entity_id,
        status=a.status,
        requires_approval=bool(a.requires_approval),
        payload=a.payload,
        executed_at=a.executed_at.isoformat() if a.executed_at else None,
        approved_at=a.approved_at.isoformat() if a.approved_at else None,
        error=a.error,
        created_at=a.created_at.isoformat(),
    ) for a in items]


@router.post("/{action_id}/approve")
async def approve_action(
    action_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(AgentAction).where(
            AgentAction.id == action_id,
            AgentAction.tenant_id == current_user.tenant_id,
        )
    )
    action = result.scalar_one_or_none()
    if not action:
        raise HTTPException(status_code=404, detail="Ação não encontrada")
    if action.status != "pending":
        raise HTTPException(status_code=400, detail=f"Ação já está com status '{action.status}'")

    action.status = "approved"
    action.approved_by = current_user.id
    action.approved_at = datetime.utcnow()
    await db.flush()
    await db.commit()
    return {"ok": True, "status": "approved"}


@router.post("/{action_id}/reject")
async def reject_action(
    action_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(AgentAction).where(
            AgentAction.id == action_id,
            AgentAction.tenant_id == current_user.tenant_id,
        )
    )
    action = result.scalar_one_or_none()
    if not action:
        raise HTTPException(status_code=404, detail="Ação não encontrada")
    if action.status != "pending":
        raise HTTPException(status_code=400, detail=f"Ação já está com status '{action.status}'")

    action.status = "rejected"
    action.approved_at = datetime.utcnow()
    await db.flush()
    await db.commit()
    return {"ok": True, "status": "rejected"}
