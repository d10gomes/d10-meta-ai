"""Maestro API — chat interface to the orchestrator."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import get_current_user, get_db
from app.db.models import User

router = APIRouter(prefix="/maestro", tags=["maestro"])


class OrchestrateRequest(BaseModel):
    objective: str


class ApproveRequest(BaseModel):
    action_id: str


class RejectRequest(BaseModel):
    action_id: str
    reason: str = ""


@router.post("/orchestrate")
async def orchestrate(
    body: OrchestrateRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Submit a natural language objective to the Maestro for orchestration."""
    from app.agents.maestro.service import MaestroService

    if not body.objective or len(body.objective.strip()) < 5:
        raise HTTPException(status_code=422, detail="Objetivo muito curto.")

    svc = MaestroService(db, str(user.tenant_id))
    result = await svc.orchestrate(body.objective.strip(), str(user.tenant_id))
    await db.commit()
    return result


@router.post("/simulate/{action_id}")
async def simulate_action(
    action_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Run simulation for a pending action."""
    from app.agents.simulation.service import SimulationService
    from sqlalchemy import select
    from app.db.models import AgentAction

    result = await db.execute(
        select(AgentAction).where(
            AgentAction.id == action_id,
            AgentAction.tenant_id == str(user.tenant_id),
        )
    )
    action = result.scalar_one_or_none()
    if not action:
        raise HTTPException(status_code=404, detail="Ação não encontrada.")

    svc = SimulationService(db, str(user.tenant_id))
    sim = await svc.simulate(action, str(user.tenant_id))
    await db.commit()
    return sim


@router.post("/approve")
async def approve_action(
    body: ApproveRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Approve a simulated action for execution."""
    from app.agents.simulation.service import SimulationService

    svc = SimulationService(db, str(user.tenant_id))
    result = await svc.approve(body.action_id, str(user.id), str(user.tenant_id))
    await db.commit()
    return result


@router.post("/reject")
async def reject_action(
    body: RejectRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Reject a proposed action."""
    from app.agents.simulation.service import SimulationService

    svc = SimulationService(db, str(user.tenant_id))
    result = await svc.reject(body.action_id, str(user.id), str(user.tenant_id), body.reason)
    await db.commit()
    return result


@router.get("/pending-approvals")
async def pending_approvals(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """List actions awaiting human approval."""
    from sqlalchemy import select
    from app.db.models import AgentAction

    result = await db.execute(
        select(AgentAction)
        .where(
            AgentAction.tenant_id == str(user.tenant_id),
            AgentAction.status.in_(["simulating", "pending"]),
            AgentAction.requires_approval == True,
        )
        .order_by(AgentAction.created_at.desc())
        .limit(50)
    )
    actions = result.scalars().all()
    return [
        {
            "id": str(a.id),
            "action_type": a.action_type,
            "entity_type": a.entity_type,
            "entity_id": a.entity_id,
            "payload": a.payload,
            "simulation": a.simulation_result,
            "status": a.status,
            "created_at": a.created_at.isoformat() if a.created_at else None,
        }
        for a in actions
    ]
