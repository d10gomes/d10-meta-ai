"""Creative Agent — ranks creatives by CTR, CPA and ROAS."""
from typing import List, Dict, Any
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Ad, AdMetric, AdSet, Campaign
from app.core.logging import logger


class CreativeService:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def rank_creatives(self, meta_account_id: str) -> List[Dict[str, Any]]:
        result = await self._session.execute(
            select(
                Ad.meta_ad_id,
                Ad.name,
                Ad.creative_id,
                Ad.creative_type,
                func.avg(AdMetric.ctr).label("avg_ctr"),
                func.avg(AdMetric.cpa).label("avg_cpa"),
                func.avg(AdMetric.roas).label("avg_roas"),
                func.sum(AdMetric.spend).label("total_spend"),
                func.sum(AdMetric.conversions).label("total_conversions"),
            )
            .join(AdSet, Ad.adset_id == AdSet.id)
            .join(Campaign, AdSet.campaign_id == Campaign.id)
            .join(AdMetric, Ad.id == AdMetric.ad_id)
            .where(Campaign.meta_account_id == meta_account_id)
            .group_by(Ad.meta_ad_id, Ad.name, Ad.creative_id, Ad.creative_type)
            .order_by(func.avg(AdMetric.roas).desc().nullslast())
        )
        rows = result.all()

        rankings = []
        for row in rows:
            score = self._compute_score(
                ctr=row.avg_ctr or 0,
                cpa=row.avg_cpa or 0,
                roas=row.avg_roas or 0,
            )
            rankings.append({
                "meta_ad_id": row.meta_ad_id,
                "name": row.name,
                "creative_id": row.creative_id,
                "creative_type": row.creative_type,
                "avg_ctr": round(row.avg_ctr or 0, 4),
                "avg_cpa": round(row.avg_cpa or 0, 2),
                "avg_roas": round(row.avg_roas or 0, 2),
                "total_spend": round(row.total_spend or 0, 2),
                "total_conversions": row.total_conversions or 0,
                "score": round(score, 2),
                "tier": self._tier(score),
            })

        logger.info("creative.ranked", account=meta_account_id, count=len(rankings))
        return sorted(rankings, key=lambda x: x["score"], reverse=True)

    def _compute_score(self, ctr: float, cpa: float, roas: float) -> float:
        """Composite score: higher CTR and ROAS good, lower CPA good."""
        ctr_score = min(ctr / 3.0, 1.0) * 40      # max 40 pts
        roas_score = min(roas / 4.0, 1.0) * 40     # max 40 pts
        cpa_score = max(0, 1 - (cpa / 200)) * 20   # max 20 pts (assumes CPA < R$200 is good)
        return ctr_score + roas_score + cpa_score

    def _tier(self, score: float) -> str:
        if score >= 70:
            return "winner"
        elif score >= 40:
            return "average"
        else:
            return "loser"
