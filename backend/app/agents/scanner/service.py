"""Scanner Agent — reads campaigns, adsets, ads and metrics from Meta API."""
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import logger
from app.domain.entities.campaign import CampaignMetrics
from app.domain.events.base import DomainEvent, EventTypes
from app.domain.events.bus import publish
from app.infrastructure.meta_api.client import MetaAdsClient
from app.infrastructure.repositories.campaign_repository import CampaignRepository
from app.infrastructure.repositories.meta_account_repository import MetaAccountRepository


class ScannerService:
    def __init__(self, session: AsyncSession):
        self._session = session
        self._account_repo = MetaAccountRepository(session)
        self._campaign_repo = CampaignRepository(session)

    async def scan_all_active(self):
        from app.db.session import AsyncSessionLocal

        # Fetch account IDs in a short-lived session
        async with AsyncSessionLocal() as list_session:
            accounts = await MetaAccountRepository(list_session).get_all_active()
            account_ids = [str(a.id) for a in accounts]

        logger.info("scanner.start", accounts=len(account_ids))

        # Scan each account with its own session to avoid pooler state issues
        for account_id in account_ids:
            async with AsyncSessionLocal() as s:
                try:
                    await ScannerService(s).scan_account(account_id)
                    await s.commit()
                    logger.info("scanner.account_committed", account_id=account_id)
                except Exception as exc:
                    logger.error("scanner.account_failed", account_id=account_id, error=str(exc))
                    await s.rollback()

    async def scan_account(self, account_id: str):
        account = await self._account_repo.get_by_id(account_id)
        if not account:
            logger.warning("scanner.account_not_found", account_id=account_id)
            return

        client = MetaAdsClient(account.access_token, account.ad_account_id)
        try:
            await self._sync_campaigns(client, account)
            account.last_synced_at = datetime.utcnow()
            await self._session.flush()
            try:
                await publish(DomainEvent(
                    event_type=EventTypes.SCAN_COMPLETED,
                    tenant_id=str(account.tenant_id),
                    payload={"account_id": account_id},
                ))
            except Exception as pub_exc:
                logger.warning("scanner.publish_failed", account_id=account_id, error=str(pub_exc))
            logger.info("scanner.account_done", account_id=account_id)
        finally:
            await client.close()

    async def _sync_campaigns(self, client: MetaAdsClient, account):
        campaigns = await client.get_campaigns()
        for camp_data in campaigns:
            campaign = await self._campaign_repo.upsert_campaign({
                "meta_account_id": str(account.id),
                "meta_campaign_id": camp_data["id"],
                "name": camp_data.get("name"),
                "status": camp_data.get("status"),
                "objective": camp_data.get("objective"),
                "daily_budget": float(camp_data["daily_budget"]) if camp_data.get("daily_budget") else None,
                "lifetime_budget": float(camp_data["lifetime_budget"]) if camp_data.get("lifetime_budget") else None,
            })
            await self._sync_adsets(client, campaign)

    async def _sync_adsets(self, client: MetaAdsClient, campaign):
        adsets = await client.get_adsets(campaign.meta_campaign_id)
        for adset_data in adsets:
            adset = await self._campaign_repo.upsert_adset({
                "campaign_id": str(campaign.id),
                "meta_adset_id": adset_data["id"],
                "name": adset_data.get("name"),
                "status": adset_data.get("status"),
                "daily_budget": float(adset_data["daily_budget"]) if adset_data.get("daily_budget") else None,
                "targeting": adset_data.get("targeting"),
            })
            await self._sync_ads(client, adset)

    async def _sync_ads(self, client: MetaAdsClient, adset):
        ads = await client.get_ads(adset.meta_adset_id)
        for ad_data in ads:
            creative = ad_data.get("creative", {})
            ad = await self._campaign_repo.upsert_ad({
                "adset_id": str(adset.id),
                "meta_ad_id": ad_data["id"],
                "name": ad_data.get("name"),
                "status": ad_data.get("status"),
                "creative_id": creative.get("id"),
                "creative_type": creative.get("object_type"),
            })
            insights = await client.get_ad_insights(ad_data["id"])
            if insights:
                await self._save_metrics(ad, insights)

    async def _save_metrics(self, ad, insights: dict):
        imp = int(insights.get("impressions", 0))
        clicks = int(insights.get("clicks", 0))
        spend = float(insights.get("spend", 0))
        reach = int(insights.get("reach", 0))

        # Extract conversions and revenue from actions
        actions = {a["action_type"]: float(a["value"]) for a in insights.get("actions", [])}
        action_values = {a["action_type"]: float(a["value"]) for a in insights.get("action_values", [])}
        conversions = int(actions.get("purchase", actions.get("lead", 0)))
        revenue = action_values.get("purchase", 0.0)

        m = CampaignMetrics.compute(imp, clicks, spend, conversions, revenue, reach)

        await self._campaign_repo.upsert_metric({
            "ad_id": str(ad.id),
            "date": datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0),
            "impressions": m.impressions,
            "clicks": m.clicks,
            "spend": m.spend,
            "conversions": m.conversions,
            "revenue": m.revenue,
            "reach": m.reach,
            "ctr": m.ctr,
            "cpc": m.cpc,
            "cpm": m.cpm,
            "cpa": m.cpa,
            "roas": m.roas,
            "frequency": m.frequency,
        })
