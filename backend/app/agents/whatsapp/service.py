"""WhatsApp Agent — sends automatic reports via Evolution API / Meta Cloud API."""
from datetime import datetime, timedelta
from typing import List

import httpx
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import logger
from app.db.models import AdMetric, Ad, AdSet, Campaign, MetaAccount, WhatsAppReport, Tenant
from app.infrastructure.repositories.diagnosis_repository import DiagnosisRepository


class WhatsAppAgent:
    def __init__(self, session: AsyncSession):
        self._session = session
        self._diagnosis_repo = DiagnosisRepository(session)

    async def send_report(self, tenant_id: str, report_type: str = "daily"):
        tenant = await self._get_tenant(tenant_id)
        if not tenant:
            return

        body = await self._build_report(tenant_id, report_type, tenant.name)
        phone = settings.WHATSAPP_DEFAULT_NUMBER

        success = await self._send(phone, body)
        await self._save_record(tenant_id, phone, report_type, body, success)
        logger.info("whatsapp.report_sent", tenant=tenant_id, success=success)

    async def _build_report(self, tenant_id: str, report_type: str, tenant_name: str) -> str:
        since = datetime.utcnow() - timedelta(days=1 if report_type == "daily" else 7)

        result = await self._session.execute(
            select(
                func.sum(AdMetric.spend).label("spend"),
                func.sum(AdMetric.clicks).label("clicks"),
                func.sum(AdMetric.impressions).label("impressions"),
                func.sum(AdMetric.conversions).label("conversions"),
                func.avg(AdMetric.ctr).label("ctr"),
                func.avg(AdMetric.cpa).label("cpa"),
                func.avg(AdMetric.roas).label("roas"),
            )
            .join(Ad, AdMetric.ad_id == Ad.id)
            .join(AdSet, Ad.adset_id == AdSet.id)
            .join(Campaign, AdSet.campaign_id == Campaign.id)
            .join(MetaAccount, Campaign.meta_account_id == MetaAccount.id)
            .where(
                MetaAccount.tenant_id == tenant_id,
                AdMetric.date >= since,
            )
        )
        row = result.one()

        diagnoses = await self._diagnosis_repo.get_open_by_tenant(tenant_id)
        alerts = len(diagnoses)

        period = "📅 Hoje" if report_type == "daily" else "📅 Últimos 7 dias"

        return (
            f"*D10 META AI — Relatório {period}*\n"
            f"🏢 {tenant_name}\n\n"
            f"💰 Gasto: R$ {row.spend or 0:.2f}\n"
            f"👆 Cliques: {row.clicks or 0:,}\n"
            f"👁️ Impressões: {row.impressions or 0:,}\n"
            f"🎯 Conversões: {row.conversions or 0}\n"
            f"📊 CTR: {row.ctr or 0:.2f}%\n"
            f"💵 CPA: R$ {row.cpa or 0:.2f}\n"
            f"📈 ROAS: {row.roas or 0:.2f}x\n\n"
            f"⚠️ Alertas ativos: {alerts}\n"
            f"_Gerado por D10 META AI_"
        )

    async def _send(self, phone: str, message: str) -> bool:
        if not settings.WHATSAPP_API_URL or not settings.WHATSAPP_API_TOKEN:
            logger.warning("whatsapp.not_configured")
            return False
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.post(
                    f"{settings.WHATSAPP_API_URL}/message/sendText/{phone}",
                    headers={"apikey": settings.WHATSAPP_API_TOKEN},
                    json={"number": phone, "text": message},
                )
                return resp.status_code == 200
        except Exception as exc:
            logger.error("whatsapp.send_failed", error=str(exc))
            return False

    async def _save_record(self, tenant_id: str, phone: str, report_type: str, content: str, success: bool):
        record = WhatsAppReport(
            tenant_id=tenant_id,
            phone_number=phone,
            report_type=report_type,
            content=content,
            status="sent" if success else "failed",
            sent_at=datetime.utcnow() if success else None,
        )
        self._session.add(record)
        await self._session.flush()

    async def _get_tenant(self, tenant_id: str):
        result = await self._session.execute(
            select(Tenant).where(Tenant.id == tenant_id)
        )
        return result.scalar_one_or_none()
