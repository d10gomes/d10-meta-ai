"""
Scanner Agent — Papel: COLETOR DE DADOS
- Busca campanhas, adsets, ads e métricas da API do Meta
- Salva tudo no banco
- Publica na Knowledge Base o estado atual das campanhas
- Lembra quais contas tiveram erros e com que frequência
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.base import AgentBase
from app.core.logging import logger
from app.domain.entities.campaign import CampaignMetrics
from app.domain.events.base import DomainEvent, EventTypes
from app.domain.events.bus import publish
from app.infrastructure.meta_api.client import MetaAdsClient
from app.infrastructure.repositories.campaign_repository import CampaignRepository
from app.infrastructure.repositories.meta_account_repository import MetaAccountRepository


class ScannerService(AgentBase):
    name = "scanner"

    def __init__(self, session: AsyncSession, tenant_id: str = ""):
        super().__init__(session, tenant_id)
        self._account_repo = MetaAccountRepository(session)
        self._campaign_repo = CampaignRepository(session)

    async def scan_all_active(self):
        from app.db.session import AsyncSessionLocal
        from sqlalchemy import select
        from app.db.models import Tenant

        async with AsyncSessionLocal() as s:
            result = await s.execute(select(Tenant).where(Tenant.is_active == True))
            tenants = result.scalars().all()

        async with AsyncSessionLocal() as list_session:
            accounts = await MetaAccountRepository(list_session).get_all_active()
            account_data = [(str(a.id), str(a.tenant_id)) for a in accounts]

        logger.info("scanner.start", accounts=len(account_data))

        for account_id, tenant_id in account_data:
            async with AsyncSessionLocal() as s:
                svc = ScannerService(s, tenant_id)
                try:
                    await svc.scan_account(account_id)
                    await s.commit()
                    logger.info("scanner.account_committed", account_id=account_id)
                except Exception as exc:
                    logger.error("scanner.account_failed", account_id=account_id, error=str(exc))
                    await s.rollback()
                    async with AsyncSessionLocal() as err_s:
                        err_svc = ScannerService(err_s, tenant_id)
                        await err_svc.remember(
                            key=f"account_{account_id}_error",
                            content={"error": str(exc), "timestamp": datetime.utcnow().isoformat()},
                            memory_type="outcome",
                            importance=8,
                            ttl_days=7,
                        )
                        await err_s.commit()

    async def scan_account(self, account_id: str) -> dict:
        account = await self._account_repo.get_by_id(account_id)
        if not account:
            return {}

        client = MetaAdsClient(account.access_token, account.ad_account_id)
        summary: dict[str, Any] = {
            "account_id": account_id,
            "ad_account_id": account.ad_account_id,
            "campaigns_found": 0,
            "adsets_found": 0,
            "ads_found": 0,
            "total_spend_today": 0.0,
            "scanned_at": datetime.utcnow().isoformat(),
        }

        try:
            campaign_summaries = await self._sync_campaigns(client, account, summary)
            account.last_synced_at = datetime.utcnow()
            await self._s.flush()

            await self.remember(
                key=f"last_scan_{account_id}",
                content=summary,
                memory_type="observation",
                importance=6,
                ttl_days=2,
            )

            await self.publish_knowledge(
                topic=f"account_{account_id}_campaigns",
                entry_type="raw_data",
                content={"summary": summary, "campaigns": campaign_summaries},
                summary=(
                    f"Conta {account.name or account_id}: "
                    f"{summary['campaigns_found']} campanhas, "
                    f"{summary['ads_found']} anúncios, "
                    f"R$ {summary['total_spend_today']:.2f} gasto hoje"
                ),
                confidence=1.0,
                ttl_hours=6,
            )

            try:
                await publish(DomainEvent(
                    event_type=EventTypes.SCAN_COMPLETED,
                    tenant_id=self._tenant_id,
                    payload={"account_id": account_id, "summary": summary},
                ))
            except Exception as pub_exc:
                logger.warning("scanner.publish_failed", error=str(pub_exc))

            logger.info("scanner.account_done", **summary)
            return summary
        finally:
            await client.close()

    async def _sync_campaigns(self, client, account, summary: dict) -> list[dict]:
        campaigns = await client.get_campaigns()
        campaign_summaries = []
        for camp_data in campaigns:
            try:
                summary["campaigns_found"] += 1
                campaign = await self._campaign_repo.upsert_campaign({
                    "meta_account_id": str(account.id),
                    "meta_campaign_id": camp_data["id"],
                    "name": camp_data.get("name"),
                    "status": camp_data.get("status"),
                    "objective": camp_data.get("objective"),
                    "daily_budget": float(camp_data["daily_budget"]) if camp_data.get("daily_budget") else None,
                    "lifetime_budget": float(camp_data["lifetime_budget"]) if camp_data.get("lifetime_budget") else None,
                })
                adset_data = await self._sync_adsets(client, campaign, summary)
                campaign_summaries.append({
                    "id": camp_data["id"],
                    "name": camp_data.get("name"),
                    "status": camp_data.get("status"),
                    "adsets": adset_data,
                })
            except Exception as exc:
                logger.warning("scanner.campaign_skipped", campaign_id=camp_data.get("id"), error=str(exc))
        return campaign_summaries

    async def _sync_adsets(self, client, campaign, summary: dict) -> list[dict]:
        adsets = await client.get_adsets(campaign.meta_campaign_id)
        adset_summaries = []
        for adset_data in adsets:
            summary["adsets_found"] += 1
            adset = await self._campaign_repo.upsert_adset({
                "campaign_id": str(campaign.id),
                "meta_adset_id": adset_data["id"],
                "name": adset_data.get("name"),
                "status": adset_data.get("status"),
                "daily_budget": float(adset_data["daily_budget"]) if adset_data.get("daily_budget") else None,
                "targeting": adset_data.get("targeting"),
            })
            ads = await self._sync_ads(client, adset, summary)
            adset_summaries.append({"id": adset_data["id"], "name": adset_data.get("name"), "ads": ads})
        return adset_summaries

    async def _sync_ads(self, client, adset, summary: dict) -> list[dict]:
        ads = await client.get_ads(adset.meta_adset_id)
        ad_summaries = []
        for ad_data in ads:
            summary["ads_found"] += 1
            creative = ad_data.get("creative", {})
            ad = await self._campaign_repo.upsert_ad({
                "adset_id": str(adset.id),
                "meta_ad_id": ad_data["id"],
                "name": ad_data.get("name"),
                "status": ad_data.get("status"),
                "creative_id": creative.get("id"),
                "creative_type": creative.get("object_type"),
            })
            # Busca insights diários dos últimos 30 dias
            daily_insights = await client.get_ad_insights_daily(ad_data["id"], days=30)
            total_spend = 0.0
            for day_insight in daily_insights:
                await self._save_metrics(ad, day_insight)
                total_spend += float(day_insight.get("spend", 0))
            summary["total_spend_today"] += total_spend
            if daily_insights:
                ad_summaries.append({"id": ad_data["id"], "spend": total_spend})
        return ad_summaries

    @staticmethod
    def _safe_float(v, max_val: float = 9_999_999.0) -> float:
        import math
        try:
            f = float(v)
        except (TypeError, ValueError):
            return 0.0
        if math.isnan(f) or math.isinf(f):
            return 0.0
        return min(max(f, -max_val), max_val)

    @staticmethod
    def _safe_int(v, max_val: int = 2_147_483_647) -> int:
        try:
            return min(int(float(v)), max_val)
        except (TypeError, ValueError):
            return 0

    async def _save_metrics(self, ad, insights: dict):
        imp = self._safe_int(insights.get("impressions", 0))
        clicks = self._safe_int(insights.get("clicks", 0))
        spend = self._safe_float(insights.get("spend", 0))
        reach = self._safe_int(insights.get("reach", 0))
        actions = {a["action_type"]: self._safe_float(a["value"]) for a in insights.get("actions", [])}
        action_values = {a["action_type"]: self._safe_float(a["value"]) for a in insights.get("action_values", [])}
        conversions = self._safe_int(actions.get("purchase", actions.get("lead", 0)))
        revenue = self._safe_float(action_values.get("purchase", 0.0))
        m = CampaignMetrics.compute(imp, clicks, spend, conversions, revenue, reach)
        # Usa a data retornada pela API Meta (campo "date_start"), senão usa hoje
        date_str = insights.get("date_start")
        if date_str:
            try:
                metric_date = datetime.strptime(date_str, "%Y-%m-%d").replace(
                    hour=0, minute=0, second=0, microsecond=0
                )
            except ValueError:
                metric_date = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        else:
            metric_date = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        await self._campaign_repo.upsert_metric({
            "ad_id": str(ad.id),
            "date": metric_date,
            "impressions": m.impressions, "clicks": m.clicks,
            "spend": self._safe_float(m.spend),
            "conversions": m.conversions, "revenue": self._safe_float(m.revenue),
            "reach": m.reach,
            "ctr": self._safe_float(m.ctr),
            "cpc": self._safe_float(m.cpc),
            "cpm": self._safe_float(m.cpm),
            "cpa": self._safe_float(m.cpa),
            "roas": self._safe_float(m.roas),
            "frequency": self._safe_float(m.frequency),
        })
