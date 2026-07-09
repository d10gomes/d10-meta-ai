from typing import List, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Campaign, AdSet, Ad, AdMetric


class CampaignRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def upsert_campaign(self, data: dict) -> Campaign:
        result = await self._session.execute(
            select(Campaign).where(Campaign.meta_campaign_id == data["meta_campaign_id"])
        )
        campaign = result.scalar_one_or_none()
        if campaign:
            for k, v in data.items():
                setattr(campaign, k, v)
        else:
            campaign = Campaign(**data)
            self._session.add(campaign)
        await self._session.flush()
        return campaign

    async def upsert_adset(self, data: dict) -> AdSet:
        result = await self._session.execute(
            select(AdSet).where(AdSet.meta_adset_id == data["meta_adset_id"])
        )
        adset = result.scalar_one_or_none()
        if adset:
            for k, v in data.items():
                setattr(adset, k, v)
        else:
            adset = AdSet(**data)
            self._session.add(adset)
        await self._session.flush()
        return adset

    async def upsert_ad(self, data: dict) -> Ad:
        result = await self._session.execute(
            select(Ad).where(Ad.meta_ad_id == data["meta_ad_id"])
        )
        ad = result.scalar_one_or_none()
        if ad:
            for k, v in data.items():
                setattr(ad, k, v)
        else:
            ad = Ad(**data)
            self._session.add(ad)
        await self._session.flush()
        return ad

    async def upsert_metric(self, data: dict) -> AdMetric:
        result = await self._session.execute(
            select(AdMetric).where(
                AdMetric.ad_id == data["ad_id"],
                AdMetric.date == data["date"],
            )
        )
        metric = result.scalar_one_or_none()
        if metric:
            for k, v in data.items():
                setattr(metric, k, v)
        else:
            metric = AdMetric(**data)
            self._session.add(metric)
        await self._session.flush()
        return metric

    async def get_ads_with_metrics(self, meta_account_id: str) -> List[dict]:
        """Return ads joined with their latest metrics for a given account."""
        result = await self._session.execute(
            select(Ad, AdMetric, AdSet, Campaign)
            .join(AdSet, Ad.adset_id == AdSet.id)
            .join(Campaign, AdSet.campaign_id == Campaign.id)
            .join(AdMetric, Ad.id == AdMetric.ad_id, isouter=True)
            .where(Campaign.meta_account_id == meta_account_id)
            .order_by(AdMetric.date.desc())
        )
        return result.all()
