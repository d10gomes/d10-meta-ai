from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import get_current_user
from app.db.models import User, AdMetric, Ad, AdSet, Campaign, MetaAccount, AgentRun
from app.db.session import get_db

router = APIRouter()

# Mapeamento de marca → padrões de nome de campanha
BRAND_PATTERNS = {
    "Circo do Tiru": ["%circo%"],
    "MMABET":        ["%mmabet%"],
    "DonaldBet":     ["%donald%"],
}


async def _get_ad_ids_for_tenant(tenant_id: str, db: AsyncSession) -> list[str]:
    """Retorna todos os ad_ids que pertencem ao tenant — mesmo padrão que funciona em campaigns.py."""
    result = await db.execute(
        select(Ad.id)
        .select_from(Ad)
        .join(AdSet, Ad.adset_id == AdSet.id)
        .join(Campaign, AdSet.campaign_id == Campaign.id)
        .join(MetaAccount, Campaign.meta_account_id == MetaAccount.id)
        .where(MetaAccount.tenant_id == str(tenant_id))
    )
    return [str(row[0]) for row in result.fetchall()]


@router.get("/summary")
async def get_summary(
    days: int = Query(7, ge=1, le=180),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    since = datetime.utcnow() - timedelta(days=days)
    ad_ids = await _get_ad_ids_for_tenant(current_user.tenant_id, db)
    if not ad_ids:
        return {"period_days": days, "spend": 0, "clicks": 0, "impressions": 0,
                "conversions": 0, "revenue": 0, "ctr": 0, "cpa": 0, "roas": 0,
                "cpm": 0, "frequency": 0}

    result = await db.execute(
        select(
            func.sum(AdMetric.spend).label("spend"),
            func.sum(AdMetric.clicks).label("clicks"),
            func.sum(AdMetric.impressions).label("impressions"),
            func.sum(AdMetric.conversions).label("conversions"),
            func.sum(AdMetric.revenue).label("revenue"),
            func.avg(AdMetric.ctr).label("ctr"),
            func.avg(AdMetric.cpm).label("cpm"),
            func.avg(AdMetric.frequency).label("frequency"),
        )
        .where(AdMetric.ad_id.in_(ad_ids), AdMetric.date >= since)
    )
    row = result.one()
    spend = float(row.spend or 0)
    conversions = int(row.conversions or 0)
    revenue = float(row.revenue or 0)
    return {
        "period_days": days,
        "spend": round(spend, 2),
        "clicks": int(row.clicks or 0),
        "impressions": int(row.impressions or 0),
        "conversions": conversions,
        "revenue": round(revenue, 2),
        "ctr": round(float(row.ctr or 0), 4),
        "cpa": round(spend / conversions, 2) if conversions > 0 else 0,
        "roas": round(revenue / spend, 2) if spend > 0 else 0,
        "cpm": round(float(row.cpm or 0), 2),
        "frequency": round(float(row.frequency or 0), 2),
    }


@router.get("/timeline")
async def get_timeline(
    days: int = Query(30, ge=1, le=180),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    since = datetime.utcnow() - timedelta(days=days)
    ad_ids = await _get_ad_ids_for_tenant(current_user.tenant_id, db)
    if not ad_ids:
        return []

    result = await db.execute(
        select(
            func.date_trunc("day", AdMetric.date).label("day"),
            func.sum(AdMetric.spend).label("spend"),
            func.sum(AdMetric.conversions).label("conversions"),
            func.sum(AdMetric.revenue).label("revenue"),
        )
        .where(AdMetric.ad_id.in_(ad_ids), AdMetric.date >= since)
        .group_by(func.date_trunc("day", AdMetric.date))
        .order_by(func.date_trunc("day", AdMetric.date))
    )
    rows = result.all()
    return [
        {
            "day": row.day.date().isoformat(),
            "spend": round(float(row.spend or 0), 2),
            "conversions": int(row.conversions or 0),
            "roas": round(float(row.revenue or 0) / float(row.spend), 2) if row.spend else 0,
        }
        for row in rows
    ]


@router.get("/data-status")
async def data_status(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Retorna quantos dados existem no banco para o tenant — usado pelo dashboard para guiar o usuário."""
    # Conta contas Meta conectadas
    accounts_result = await db.execute(
        select(func.count(MetaAccount.id))
        .where(MetaAccount.tenant_id == current_user.tenant_id, MetaAccount.is_active == True)
    )
    accounts_count = accounts_result.scalar() or 0

    # Conta métricas dos últimos 30 dias usando ad_ids (mesmo padrão que funciona)
    since = datetime.utcnow() - timedelta(days=30)
    ad_ids = await _get_ad_ids_for_tenant(current_user.tenant_id, db)
    if ad_ids:
        metrics_result = await db.execute(
            select(func.count(AdMetric.id))
            .where(AdMetric.ad_id.in_(ad_ids), AdMetric.date >= since)
        )
        metrics_count = metrics_result.scalar() or 0
    else:
        metrics_count = 0

    # Última execução do scanner
    run_result = await db.execute(
        select(AgentRun)
        .where(AgentRun.agent_name == "scanner")
        .order_by(AgentRun.started_at.desc())
        .limit(1)
    )
    last_scan = run_result.scalar_one_or_none()

    return {
        "accounts_connected": accounts_count,
        "metrics_last_30d": metrics_count,
        "has_data": metrics_count > 0,
        "last_scanner_run": last_scan.started_at.isoformat() if last_scan else None,
        "last_scanner_status": last_scan.status if last_scan else None,
        "last_scanner_error": last_scan.error if last_scan else None,
    }


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

    # Pré-carrega ad_ids do tenant para queries posteriores
    all_ad_ids = await _get_ad_ids_for_tenant(current_user.tenant_id, db)

    async def _get_brand_ad_ids(patterns) -> list[str]:
        """Ad IDs filtrados por nome de campanha (padrão ILIKE)."""
        if not all_ad_ids:
            return []
        brand_filter = or_(*[Campaign.name.ilike(p) for p in patterns])
        result = await db.execute(
            select(Ad.id)
            .select_from(Ad)
            .join(AdSet, Ad.adset_id == AdSet.id)
            .join(Campaign, AdSet.campaign_id == Campaign.id)
            .where(Campaign.id.in_(
                select(Campaign.id)
                .join(MetaAccount, Campaign.meta_account_id == MetaAccount.id)
                .where(MetaAccount.tenant_id == str(current_user.tenant_id), brand_filter)
            ))
        )
        return [str(r[0]) for r in result.fetchall()]

    brands_result = []

    for brand_name, patterns in BRAND_PATTERNS.items():
        brand_ad_ids = await _get_brand_ad_ids(patterns)

        async def _agg(ad_ids, since, until):
            if not ad_ids:
                return None
            return (await db.execute(
                select(
                    func.sum(AdMetric.spend).label("spend"),
                    func.sum(AdMetric.clicks).label("clicks"),
                    func.sum(AdMetric.impressions).label("impressions"),
                    func.sum(AdMetric.conversions).label("conversions"),
                )
                .where(
                    AdMetric.ad_id.in_(ad_ids),
                    AdMetric.date >= since,
                    AdMetric.date < until,
                )
            )).one()

        r1 = await _agg(brand_ad_ids, period1_start, period1_end)
        r2 = await _agg(brand_ad_ids, period2_start, period2_end)

        def _row(r):
            if r is None:
                return {"spend": 0, "clicks": 0, "impressions": 0, "conversions": 0,
                        "cpc": 0, "ctr": 0, "cpa": 0, "cpm": 0, "conv_rate": 0}
            spend  = float(r.spend or 0)
            clicks = int(r.clicks or 0)
            imp    = int(r.impressions or 0)
            conv   = int(r.conversions or 0)
            cpc    = round(spend / clicks, 2) if clicks > 0 else 0
            ctr    = round(clicks / imp * 100, 2) if imp > 0 else 0
            cpa    = round(spend / conv, 2) if conv > 0 else 0
            cpm    = round(spend / imp * 1000, 2) if imp > 0 else 0
            conv_rate = round(conv / clicks * 100, 2) if clicks > 0 else 0
            return {
                "spend": round(spend, 2),
                "clicks": clicks,
                "impressions": imp,
                "conversions": conv,
                "cpc": cpc,
                "ctr": ctr,
                "cpa": cpa,
                "cpm": cpm,
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
            )
            .where(
                AdMetric.ad_id.in_(brand_ad_ids) if brand_ad_ids else (AdMetric.id == None),
                AdMetric.date >= period1_start,
            )
            .group_by(func.date_trunc("week", AdMetric.date))
            .order_by(func.date_trunc("week", AdMetric.date))
        )
        timeline = []
        for r in timeline_q.all():
            clicks_w = int(r.clicks or 0)
            conv_w   = int(r.conversions or 0)
            spend_w  = float(r.spend or 0)
            timeline.append({
                "week": r.week.date().isoformat(),
                "spend": round(spend_w, 2),
                "clicks": clicks_w,
                "conversions": conv_w,
                "cpc": round(spend_w / clicks_w, 2) if clicks_w > 0 else 0,
                "cpa": round(spend_w / conv_w, 2) if conv_w > 0 else 0,
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
