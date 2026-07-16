from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional

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
        "telegram_chat_id": tenant.telegram_chat_id,
        "whatsapp_number": tenant.whatsapp_number,
        "created_at": tenant.created_at.isoformat(),
    }


class TenantSettingsUpdate(BaseModel):
    telegram_chat_id: Optional[str] = None
    whatsapp_number: Optional[str] = None


@router.patch("/me/settings")
async def update_settings(
    body: TenantSettingsUpdate,
    current_user: User = Depends(require_role("admin", "manager")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Tenant).where(Tenant.id == current_user.tenant_id))
    tenant = result.scalar_one_or_none()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant não encontrado")

    if body.telegram_chat_id is not None:
        tenant.telegram_chat_id = body.telegram_chat_id.strip() or None
    if body.whatsapp_number is not None:
        tenant.whatsapp_number = body.whatsapp_number.strip() or None

    await db.flush()
    return {"ok": True, "telegram_chat_id": tenant.telegram_chat_id, "whatsapp_number": tenant.whatsapp_number}
