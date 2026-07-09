from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import get_current_user
from app.db.models import User, AdMetric, Ad, AdSet, Campaign, MetaAccount
from app.db.session import get_db

router = APIRouter()


@router.get("/summary")
async def get_summary(
    days: int = Query(7, ge=1, le=90),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    since = datetime.utcnow() - timedelta(days=days)
    result = await db.execute(
        select(
            func.sum(AdMetric.spend).label("spend"),
            func.sum(AdMetric.clicks).label("clicks"),
            func.sum(AdMetric.impressions).label("impressions"),
            func.sum(AdMetric.conversions).label("conversions"),
            func.sum(AdMetric.revenue).label("revenue"),
            func.avg(AdMetric.ctr).label("ctr"),
            func.avg(AdMetric.cpa).label("cpa"),
            func.avg(AdMetric.roas).label("roas"),
            func.avg(AdMetric.cpm).label("cpm"),
            func.avg(AdMetric.frequency).label("frequency"),
        )
        .join(Ad, AdMetric.ad_id == Ad.id)
        .join(AdSet, Ad.adset_id == AdSet.id)
        .join(Campaign, AdSet.campaign_id == Campaign.id)
        .join(MetaAccount, Campaign.meta_account_id == MetaAccount.id)
        .where(MetaAccount.tenant_id == current_user.tenant_id, AdMetric.date >= since)
    )
    row = result.one()
    return {
        "period_days": days,
        "spend": round(row.spend or 0, 2),
        "clicks": row.clicks or 0,
        "impressions": row.impressions or 0,
        "conversions": row.conversions or 0,
        "revenue": round(row.revenue or 0, 2),
        "ctr": round(row.ctr or 0, 4),
        "cpa": round(row.cpa or 0, 2),
        "roas": round(row.roas or 0, 2),
        "cpm": round(row.cpm or 0, 2),
        "frequency": round(row.frequency or 0, 2),
    }


@router.get("/timeline")
async def get_timeline(
    days: int = Query(30, ge=1, le=90),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    since = datetime.utcnow() - timedelta(days=days)
    result = await db.execute(
        select(
            func.date_trunc("day", AdMetric.date).label("day"),
            func.sum(AdMetric.spend).label("spend"),
            func.sum(AdMetric.conversions).label("conversions"),
            func.avg(AdMetric.roas).label("roas"),
        )
        .join(Ad, AdMetric.ad_id == Ad.id)
        .join(AdSet, Ad.adset_id == AdSet.id)
        .join(Campaign, AdSet.campaign_id == Campaign.id)
        .join(MetaAccount, Campaign.meta_account_id == MetaAccount.id)
        .where(MetaAccount.tenant_id == current_user.tenant_id, AdMetric.date >= since)
        .group_by(func.date_trunc("day", AdMetric.date))
        .order_by(func.date_trunc("day", AdMetric.date))
    )
    rows = result.all()
    return [
        {
            "day": row.day.date().isoformat(),
            "spend": round(row.spend or 0, 2),
            "conversions": row.conversions or 0,
            "roas": round(row.roas or 0, 2),
        }
        for row in rows
    ]
