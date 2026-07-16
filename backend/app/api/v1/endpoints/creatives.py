from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import get_current_user
from app.db.models import User, Ad, AdSet, Campaign, AdMetric, MetaAccount
from app.db.session import get_db

router = APIRouter()


@router.get("")
async def list_creatives(
    days: int = Query(7, ge=1, le=180),
    sort: str = Query("roas", regex="^(roas|ctr|conversions|spend|cpa)$"),
    limit: int = Query(50, ge=1, le=200),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Retorna anúncios rankeados por performance."""
    since = datetime.utcnow() - timedelta(days=days)

    result = await db.execute(
        select(
            Ad.id,
            Ad.meta_ad_id,
            Ad.name,
            Ad.status,
            Ad.preview_url,
            Ad.thumbnail_url,
            Campaign.name.label("campaign_name"),
            Campaign.objective,
            AdSet.name.label("adset_name"),
            func.sum(AdMetric.spend).label("spend"),
            func.sum(AdMetric.impressions).label("impressions"),
            func.sum(AdMetric.clicks).label("clicks"),
            func.sum(AdMetric.conversions).label("conversions"),
            func.sum(AdMetric.revenue).label("revenue"),
            func.avg(AdMetric.ctr).label("ctr"),
            func.avg(AdMetric.cpa).label("cpa"),
            func.avg(AdMetric.roas).label("roas"),
            func.avg(AdMetric.frequency).label("frequency"),
            func.avg(AdMetric.cpm).label("cpm"),
            func.count(AdMetric.id).label("days_with_data"),
        )
        .join(AdSet, Ad.adset_id == AdSet.id)
        .join(Campaign, AdSet.campaign_id == Campaign.id)
        .join(MetaAccount, Campaign.meta_account_id == MetaAccount.id)
        .join(AdMetric, Ad.id == AdMetric.ad_id)
        .where(
            MetaAccount.tenant_id == current_user.tenant_id,
            AdMetric.date >= since,
            AdMetric.impressions > 0,
        )
        .group_by(
            Ad.id, Ad.meta_ad_id, Ad.name, Ad.status,
            Ad.preview_url, Ad.thumbnail_url,
            Campaign.name, Campaign.objective,
            AdSet.name,
        )
        .having(func.sum(AdMetric.spend) > 0)
    )

    rows = result.all()

    def score(row) -> float:
        """Score composto: ROAS * CTR / max(CPA, 1) — quanto maior melhor."""
        roas = float(row.roas or 0)
        ctr  = float(row.ctr or 0)
        cpa  = float(row.cpa or 1)
        conv = int(row.conversions or 0)
        if conv == 0:
            return 0.0
        return round((roas * ctr * conv) / max(cpa, 0.1), 4)

    items = []
    for row in rows:
        spend       = round(float(row.spend or 0), 2)
        impressions = int(row.impressions or 0)
        clicks      = int(row.clicks or 0)
        conversions = int(row.conversions or 0)
        revenue     = round(float(row.revenue or 0), 2)
        ctr         = round(float(row.ctr or 0), 4)
        cpa         = round(float(row.cpa or 0), 2)
        roas        = round(float(row.roas or 0), 2)
        frequency   = round(float(row.frequency or 0), 2)
        cpm         = round(float(row.cpm or 0), 2)

        # Grade A/B/C/D
        if roas >= 4.0 and ctr >= 2.0:
            grade = "S"
        elif roas >= 3.0 or ctr >= 2.0:
            grade = "A"
        elif roas >= 2.0 or ctr >= 1.0:
            grade = "B"
        elif roas >= 1.0:
            grade = "C"
        else:
            grade = "D"

        items.append({
            "id":            str(row.id),
            "meta_ad_id":    row.meta_ad_id,
            "name":          row.name or "Sem nome",
            "status":        row.status,
            "preview_url":   row.preview_url,
            "thumbnail_url": row.thumbnail_url,
            "campaign_name": row.campaign_name,
            "adset_name":    row.adset_name,
            "objective":     row.objective,
            "spend":         spend,
            "impressions":   impressions,
            "clicks":        clicks,
            "conversions":   conversions,
            "revenue":       revenue,
            "ctr":           ctr,
            "cpa":           cpa,
            "roas":          roas,
            "frequency":     frequency,
            "cpm":           cpm,
            "days_with_data": int(row.days_with_data or 0),
            "score":         score(row),
            "grade":         grade,
        })

    # Ordenação
    sort_map = {
        "roas":        lambda x: -(x["roas"] or 0),
        "ctr":         lambda x: -(x["ctr"] or 0),
        "conversions": lambda x: -(x["conversions"] or 0),
        "spend":       lambda x: -(x["spend"] or 0),
        "cpa":         lambda x: (x["cpa"] or 999),
        "score":       lambda x: -(x["score"] or 0),
    }
    items.sort(key=sort_map.get(sort, sort_map["roas"]))

    # Totais para o header
    total_spend       = round(sum(i["spend"] for i in items), 2)
    total_conversions = sum(i["conversions"] for i in items)
    total_revenue     = round(sum(i["revenue"] for i in items), 2)
    avg_roas          = round(total_revenue / total_spend, 2) if total_spend > 0 else 0
    winners           = [i for i in items if i["grade"] in ("S", "A")]
    losers            = [i for i in items if i["grade"] == "D" and i["conversions"] == 0 and i["spend"] > 50]

    return {
        "period_days": days,
        "total_ads": len(items),
        "total_spend": total_spend,
        "total_conversions": total_conversions,
        "total_revenue": total_revenue,
        "avg_roas": avg_roas,
        "winners_count": len(winners),
        "losers_count": len(losers),
        "items": items[:limit],
    }
