from typing import List
from pydantic import BaseModel
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import get_current_user
from app.db.models import User
from app.db.session import get_db
from app.infrastructure.repositories.diagnosis_repository import DiagnosisRepository

router = APIRouter()


class DiagnosisOut(BaseModel):
    id: str
    entity_type: str | None
    entity_id: str | None
    issue_type: str
    severity: str
    details: dict | None
    resolved: bool
    created_at: str


@router.get("/", response_model=List[DiagnosisOut])
async def list_diagnoses(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    repo = DiagnosisRepository(db)
    items = await repo.get_open_by_tenant(str(current_user.tenant_id))
    return [DiagnosisOut(
        id=str(d.id), entity_type=d.entity_type, entity_id=d.entity_id,
        issue_type=d.issue_type, severity=d.severity, details=d.details,
        resolved=d.resolved, created_at=d.created_at.isoformat(),
    ) for d in items]
