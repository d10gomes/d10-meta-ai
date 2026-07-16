from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import get_current_user
from app.db.models import User, AdMetric, Ad, AdSet, Campaign, MetaAccount
from app.db.session import get_db

router = APIRouter()

# Mapeamento de marca → padrões de nome de campanha
BRAND_PATTERNS = {
    "Circo do Tiru": ["%circo%"],
    "MMABET":        ["%mmabet%"],
    "DonaldBet":     ["%donald%"],
}


@router.get("/summary")
async def get_summary(
    days: int = Query(7, ge=1, le=180),
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
    days: int = Query(30, ge=1, le=180),
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


@router.get("/brand-comparison")
async def brand_comparison(
    days: int = Query(60, ge=14, le=180),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Comparação por marca (Circo do Tiru, MMABET, DonaldBet) dividindo o período
    em duas metades iguais para diagnosticar: problema de pixel vs custo de mídia.

    Diagnóstico:
    - CPC estável + taxa_conversão caindo  → pixel não está batendo
    - CPC subindo  + taxa_conversão estável → custo de mídia inflado
    - Ambos piores                          → os dois problemas
    - Estável ou melhora                    → ok
    """
    now = datetime.utcnow()
    half = days // 2
    period1_start = now - timedelta(days=days)       # início do período todo
    period1_end   = now - timedelta(days=half)        # fim da primeira metade
    period2_start = now - timedelta(days=half)        # início da segunda metade
    period2_end   = now                              # hoje

    brands_result = []

    for brand_name, patterns in BRAND_PATTERNS.items():
        # Filtro de nome de campanha por padrões ILIKE
        brand_filter = or_(*[Campaign.name.ilike(p) for p in patterns])

        def _base_q(since, until):
            return (
                select(
                    func.sum(AdMetric.spend).label("spend"),
                    func.sum(AdMetric.clicks).label("clicks"),
                    func.sum(AdMetric.impressions).label("impressions"),
                    func.sum(AdMetric.conversions).label("conversions"),
                    func.avg(AdMetric.cpc).label("cpc"),
                    func.avg(AdMetric.ctr).label("ctr"),
                    func.avg(AdMetric.cpa).label("cpa"),
                    func.avg(AdMetric.cpm).label("cpm"),
                )
                .join(Ad, AdMetric.ad_id == Ad.id)
                .join(AdSet, Ad.adset_id == AdSet.id)
                .join(Campaign, AdSet.campaign_id == Campaign.id)
                .join(MetaAccount, Campaign.meta_account_id == MetaAccount.id)
                .where(
                    MetaAccount.tenant_id == current_user.tenant_id,
                    brand_filter,
                    AdMetric.date >= since,
                    AdMetric.date < until,
                )
            )

        r1 = (await db.execute(_base_q(period1_start, period1_end))).one()
        r2 = (await db.execute(_base_q(period2_start, period2_end))).one()

        def _row(r):
            spend   = float(r.spend or 0)
            clicks  = int(r.clicks or 0)
            conv    = int(r.conversions or 0)
            cpc     = float(r.cpc or 0)
            ctr     = float(r.ctr or 0)
            cpa     = float(r.cpa or 0)
            cpm     = float(r.cpm or 0)
            imp     = int(r.impressions or 0)
            conv_rate = round(conv / clicks * 100, 2) if clicks > 0 else 0
            return {
                "spend": round(spend, 2),
                "clicks": clicks,
                "impressions": imp,
                "conversions": conv,
                "cpc": round(cpc, 2),
                "ctr": round(ctr, 2),
                "cpa": round(cpa, 2),
                "cpm": round(cpm, 2),
                "conv_rate": conv_rate,
            }

        p1 = _row(r1)
        p2 = _row(r2)

        # ── Diagnóstico pixel vs custo ────────────────────────────────────────
        def _pct_change(old, new):
            if old == 0:
                return None
            return round((new - old) / old * 100, 1)

        cpc_change      = _pct_change(p1["cpc"], p2["cpc"])
        conv_rate_change = _pct_change(p1["conv_rate"], p2["conv_rate"])
        cpa_change      = _pct_change(p1["cpa"], p2["cpa"])
        clicks_change   = _pct_change(p1["clicks"], p2["clicks"])

        # Thresholds: variação > 15% é considerada significativa
        THRESHOLD = 15

        if cpc_change is None and conv_rate_change is None:
            verdict = "sem_dados"
            verdict_label = "Sem dados suficientes"
            verdict_color = "gray"
        elif (
            p2["conversions"] == 0 and p1["conversions"] > 0
        ) or (
            conv_rate_change is not None and conv_rate_change < -THRESHOLD
            and (cpc_change is None or abs(cpc_change) < THRESHOLD)
        ):
            verdict = "pixel"
            verdict_label = "Provável problema de pixel — cliques chegam, conversões não registram"
            verdict_color = "red"
        elif (
            cpc_change is not None and cpc_change > THRESHOLD
            and (conv_rate_change is None or abs(conv_rate_change) < THRESHOLD)
        ):
            verdict = "custo"
            verdict_label = "Custo de mídia inflado — audiência mais cara ou saturação"
            verdict_color = "orange"
        elif (
            cpc_change is not None and cpc_change > THRESHOLD
            and conv_rate_change is not None and conv_rate_change < -THRESHOLD
        ):
            verdict = "ambos"
            verdict_label = "Custo subiu E taxa de conversão caiu — verificar pixel e público"
            verdict_color = "red"
        elif (
            (cpc_change is None or cpc_change < THRESHOLD)
            and (conv_rate_change is None or conv_rate_change > -THRESHOLD)
        ):
            verdict = "ok"
            verdict_label = "Métricas estáveis — sem sinal de problema"
            verdict_color = "green"
        else:
            verdict = "atencao"
            verdict_label = "Variação detectada — monitorar"
            verdict_color = "yellow"

        # Timeline semanal para o gráfico
        timeline_q = await db.execute(
            select(
                func.date_trunc("week", AdMetric.date).label("week"),
                func.sum(AdMetric.spend).label("spend"),
                func.sum(AdMetric.clicks).label("clicks"),
                func.sum(AdMetric.conversions).label("conversions"),
                func.avg(AdMetric.cpc).label("cpc"),
                func.avg(AdMetric.ctr).label("ctr"),
                func.avg(AdMetric.cpa).label("cpa"),
            )
            .join(Ad, AdMetric.ad_id == Ad.id)
            .join(AdSet, Ad.adset_id == AdSet.id)
            .join(Campaign, AdSet.campaign_id == Campaign.id)
            .join(MetaAccount, Campaign.meta_account_id == MetaAccount.id)
            .where(
                MetaAccount.tenant_id == current_user.tenant_id,
                brand_filter,
                AdMetric.date >= period1_start,
            )
            .group_by(func.date_trunc("week", AdMetric.date))
            .order_by(func.date_trunc("week", AdMetric.date))
        )
        timeline = []
        for r in timeline_q.all():
            clicks_w = int(r.clicks or 0)
            conv_w   = int(r.conversions or 0)
            timeline.append({
                "week": r.week.date().isoformat(),
                "spend": round(float(r.spend or 0), 2),
                "clicks": clicks_w,
                "conversions": conv_w,
                "cpc": round(float(r.cpc or 0), 2),
                "ctr": round(float(r.ctr or 0), 2),
                "cpa": round(float(r.cpa or 0), 2),
                "conv_rate": round(conv_w / clicks_w * 100, 2) if clicks_w > 0 else 0,
            })

        brands_result.append({
            "brand": brand_name,
            "period1": {**p1, "label": f"Dias {days}–{half} atrás"},
            "period2": {**p2, "label": f"Dias {half}–0 (recente)"},
            "changes": {
                "cpc": cpc_change,
                "conv_rate": conv_rate_change,
                "cpa": cpa_change,
                "clicks": clicks_change,
            },
            "verdict": verdict,
            "verdict_label": verdict_label,
            "verdict_color": verdict_color,
            "timeline": timeline,
        })

    return {
        "period_days": days,
        "half_days": half,
        "generated_at": now.isoformat(),
        "brands": brands_result,
    }
