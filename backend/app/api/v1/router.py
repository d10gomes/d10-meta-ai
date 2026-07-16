from fastapi import APIRouter

from app.api.v1.endpoints import (
    auth, tenants, meta_accounts, campaigns,
    diagnoses, actions, creatives, reports, agents,
)
from app.api.v1.endpoints import maestro, media, monitor, telegram_webhook

api_router = APIRouter()

api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(tenants.router, prefix="/tenants", tags=["tenants"])
api_router.include_router(meta_accounts.router, prefix="/meta-accounts", tags=["meta-accounts"])
api_router.include_router(campaigns.router, prefix="/campaigns", tags=["campaigns"])
api_router.include_router(diagnoses.router, prefix="/diagnoses", tags=["diagnoses"])
api_router.include_router(actions.router, prefix="/actions", tags=["actions"])
api_router.include_router(creatives.router, prefix="/creatives", tags=["creatives"])
api_router.include_router(reports.router, prefix="/reports", tags=["reports"])
api_router.include_router(agents.router, prefix="/agents", tags=["agents"])
api_router.include_router(maestro.router)
api_router.include_router(media.router)
api_router.include_router(monitor.router)
api_router.include_router(telegram_webhook.router)
