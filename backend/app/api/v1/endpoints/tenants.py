from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import require_role
from app.db.models import User, Tenant
from app.db.session import get_db

router = APIRouter()


@router.get("/me")
async def get_my_tenant(
    current_user: User = Depends(require_role("admin", "manager", "viewer")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Tenant).where(Tenant.id == current_user.tenant_id))
    tenant = result.scalar_one_or_none()
    if not tenant:
        return {}
    return {
        "id": str(tenant.id),
        "name": tenant.name,
        "slug": tenant.slug,
        "max_meta_accounts": tenant.max_meta_accounts,
        "is_active": tenant.is_active,
        "created_at": tenant.created_at.isoformat(),
    }
