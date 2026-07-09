"""
Analyst Agent — Especialista em análise de performance de Meta Ads.

Analisa todas as campanhas do tenant, calcula KPIs, identifica padrões,
detecta oportunidades e gera um relatório executivo detalhado em português.
Roda diariamente às 07h00.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import logger
from app.db.models import Campaign, AdSet, Ad, AdMetric, MetaAccount


class AnalystService:
    def __init__(self, session: AsyncSession):
        self._s = session

    # ------------------------------------------------------------------
    async def run(self, tenant_id: str) -> dict[str, Any]:
        """Full analysis pipeline. Returns the insight dict."""
        since_7d = datetime.utcnow() - timedelta(days=7)
        since_30d = datetime.utcnow() - timedelta(days=30)

        accounts = await self._get_accounts(tenant_id)
        if not accounts:
            return self._empty_report(tenant_id)

        kpis_7d = await self._aggregate_kpis(tenant_id, since_7d)
        kpis_30d = await self._aggregate_kpis(tenant_id, since_30d)
        top_campaigns = await self._top_campaigns(tenant_id, since_7d, limit=5)
        worst_campaigns = await self._worst_campaigns(tenant_id, since_7d, limit=5)
        account_breakdown = await self._account_breakdown(tenant_id, since_7d)
        alerts = await self._generate_alerts(tenant_id, since_7d)
        recommendations = self._build_recommendations(kpis_7d, top_campaigns, worst_campaigns, alerts)

        title = f"Análise de Performance — {datetime.now().strftime('%d/%m/%Y')}"
        summary = self._executive_summary(kpis_7d, kpis_30d, top_campaigns, alerts)

        details = {
            "period": "últimos 7 dias",
            "accounts_count": len(accounts),
            "kpis_7d": kpis_7d,
            "kpis_30d": kpis_30d,
            "variation_pct": self._variation(kpis_7d, kpis_30d),
            "top_campaigns": top_campaigns,
            "worst_campaigns": worst_campaigns,
            "account_breakdown": account_breakdown,
            "alerts": alerts,
            "recommendations": recommendations,
        }

        await self._save_insight(tenant_id, "analyst", title, summary, details)
        logger.info("analyst.done", tenant_id=tenant_id, alerts=len(alerts))
        return details

    # ------------------------------------------------------------------
    # Data fetchers
    # ------------------------------------------------------------------

    async def _get_accounts(self, tenant_id: str):
        r = await self._s.execute(
            select(MetaAccount).where(
                MetaAccount.tenant_id == tenant_id,
                MetaAccount.is_active == True,
            )
        )
        return r.scalars().all()

    async def _aggregate_kpis(self, tenant_id: str, since: datetime) -> dict:
        r = await self._s.execute(
            select(
                func.coalesce(func.sum(AdMetric.spend), 0).label("spend"),
                func.coalesce(func.sum(AdMetric.impressions), 0).label("impressions"),
                func.coalesce(func.sum(AdMetric.clicks), 0).label("clicks"),
                func.coalesce(func.sum(AdMetric.conversions), 0).label("conversions"),
                func.coalesce(func.sum(AdMetric.revenue), 0).label("revenue"),
                func.coalesce(func.avg(AdMetric.ctr), 0).label("ctr"),
                func.coalesce(func.avg(AdMetric.cpm), 0).label("cpm"),
                func.coalesce(func.avg(AdMetric.cpa), 0).label("cpa"),
                func.coalesce(func.avg(AdMetric.roas), 0).label("roas"),
                func.coalesce(func.avg(AdMetric.frequency), 0).label("frequency"),
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
        row = r.one()
        spend = float(row.spend)
        revenue = float(row.revenue)
        conversions = int(row.conversions)
        roas = round(revenue / spend, 2) if spend > 0 else 0.0

        return {
            "spend": round(spend, 2),
            "impressions": int(row.impressions),
            "clicks": int(row.clicks),
            "conversions": conversions,
            "revenue": round(revenue, 2),
            "ctr": round(float(row.ctr), 3),
            "cpm": round(float(row.cpm), 2),
            "cpa": round(float(row.cpa), 2),
            "roas": roas,
            "frequency": round(float(row.frequency), 2),
        }

    async def _top_campaigns(self, tenant_id: str, since: datetime, limit: int) -> list[dict]:
        r = await self._s.execute(
            select(
                Campaign.name,
                Campaign.meta_campaign_id,
                func.sum(AdMetric.spend).label("spend"),
                func.sum(AdMetric.conversions).label("conversions"),
                func.sum(AdMetric.revenue).label("revenue"),
                func.avg(AdMetric.roas).label("roas"),
                func.avg(AdMetric.ctr).label("ctr"),
                func.avg(AdMetric.cpa).label("cpa"),
            )
            .join(AdSet, Campaign.id == AdSet.campaign_id)
            .join(Ad, AdSet.id == Ad.adset_id)
            .join(AdMetric, Ad.id == AdMetric.ad_id)
            .join(MetaAccount, Campaign.meta_account_id == MetaAccount.id)
            .where(
                MetaAccount.tenant_id == tenant_id,
                AdMetric.date >= since,
                AdMetric.spend > 0,
            )
            .group_by(Campaign.id, Campaign.name, Campaign.meta_campaign_id)
            .order_by(func.avg(AdMetric.roas).desc().nullslast())
            .limit(limit)
        )
        return [
            {
                "name": row.name,
                "id": row.meta_campaign_id,
                "spend": round(float(row.spend or 0), 2),
                "conversions": int(row.conversions or 0),
                "revenue": round(float(row.revenue or 0), 2),
                "roas": round(float(row.roas or 0), 2),
                "ctr": round(float(row.ctr or 0), 3),
                "cpa": round(float(row.cpa or 0), 2),
                "grade": self._grade(float(row.roas or 0), float(row.ctr or 0), float(row.cpa or 0)),
            }
            for row in r.all()
        ]

    async def _worst_campaigns(self, tenant_id: str, since: datetime, limit: int) -> list[dict]:
        r = await self._s.execute(
            select(
                Campaign.name,
                Campaign.meta_campaign_id,
                func.sum(AdMetric.spend).label("spend"),
                func.sum(AdMetric.conversions).label("conversions"),
                func.avg(AdMetric.roas).label("roas"),
                func.avg(AdMetric.ctr).label("ctr"),
                func.avg(AdMetric.cpa).label("cpa"),
                func.avg(AdMetric.frequency).label("frequency"),
            )
            .join(AdSet, Campaign.id == AdSet.campaign_id)
            .join(Ad, AdSet.id == Ad.adset_id)
            .join(AdMetric, Ad.id == AdMetric.ad_id)
            .join(MetaAccount, Campaign.meta_account_id == MetaAccount.id)
            .where(
                MetaAccount.tenant_id == tenant_id,
                AdMetric.date >= since,
                AdMetric.spend > 10,
            )
            .group_by(Campaign.id, Campaign.name, Campaign.meta_campaign_id)
            .order_by(func.avg(AdMetric.roas).asc().nullsfirst())
            .limit(limit)
        )
        return [
            {
                "name": row.name,
                "id": row.meta_campaign_id,
                "spend": round(float(row.spend or 0), 2),
                "conversions": int(row.conversions or 0),
                "roas": round(float(row.roas or 0), 2),
                "ctr": round(float(row.ctr or 0), 3),
                "cpa": round(float(row.cpa or 0), 2),
                "frequency": round(float(row.frequency or 0), 2),
                "problem": self._diagnose_problem(float(row.roas or 0), float(row.ctr or 0), float(row.cpa or 0), float(row.frequency or 0), float(row.spend or 0), int(row.conversions or 0)),
            }
            for row in r.all()
        ]

    async def _account_breakdown(self, tenant_id: str, since: datetime) -> list[dict]:
        r = await self._s.execute(
            select(
                MetaAccount.name,
                MetaAccount.ad_account_id,
                func.sum(AdMetric.spend).label("spend"),
                func.sum(AdMetric.conversions).label("conversions"),
                func.sum(AdMetric.revenue).label("revenue"),
                func.avg(AdMetric.roas).label("roas"),
                func.count(func.distinct(Campaign.id)).label("campaigns"),
            )
            .join(Campaign, MetaAccount.id == Campaign.meta_account_id)
            .join(AdSet, Campaign.id == AdSet.campaign_id)
            .join(Ad, AdSet.id == Ad.adset_id)
            .join(AdMetric, Ad.id == AdMetric.ad_id)
            .where(
                MetaAccount.tenant_id == tenant_id,
                AdMetric.date >= since,
            )
            .group_by(MetaAccount.id, MetaAccount.name, MetaAccount.ad_account_id)
            .order_by(func.sum(AdMetric.spend).desc())
        )
        return [
            {
                "account": row.name,
                "spend": round(float(row.spend or 0), 2),
                "conversions": int(row.conversions or 0),
                "revenue": round(float(row.revenue or 0), 2),
                "roas": round(float(row.roas or 0), 2),
                "campaigns": int(row.campaigns or 0),
            }
            for row in r.all()
        ]

    async def _generate_alerts(self, tenant_id: str, since: datetime) -> list[dict]:
        alerts = []

        # Ads queimando dinheiro (gasto alto, 0 conversões)
        r = await self._s.execute(
            select(Ad.name, Campaign.name.label("campaign"), func.sum(AdMetric.spend).label("spend"))
            .join(AdMetric, Ad.id == AdMetric.ad_id)
            .join(AdSet, Ad.adset_id == AdSet.id)
            .join(Campaign, AdSet.campaign_id == Campaign.id)
            .join(MetaAccount, Campaign.meta_account_id == MetaAccount.id)
            .where(
                MetaAccount.tenant_id == tenant_id,
                AdMetric.date >= since,
                Ad.status == "ACTIVE",
            )
            .group_by(Ad.id, Ad.name, Campaign.name)
            .having(
                func.sum(AdMetric.spend) > 50,
                func.sum(AdMetric.conversions) == 0,
            )
        )
        for row in r.all():
            alerts.append({
                "type": "money_burner",
                "severity": "critical",
                "message": f"🔥 Anúncio '{row.name}' gastou R${float(row.spend):.0f} sem nenhuma conversão",
                "campaign": row.campaign,
            })

        # Frequência alta (fadiga de anúncio)
        r2 = await self._s.execute(
            select(Ad.name, Campaign.name.label("campaign"), func.avg(AdMetric.frequency).label("freq"))
            .join(AdMetric, Ad.id == AdMetric.ad_id)
            .join(AdSet, Ad.adset_id == AdSet.id)
            .join(Campaign, AdSet.campaign_id == Campaign.id)
            .join(MetaAccount, Campaign.meta_account_id == MetaAccount.id)
            .where(
                MetaAccount.tenant_id == tenant_id,
                AdMetric.date >= since,
                Ad.status == "ACTIVE",
            )
            .group_by(Ad.id, Ad.name, Campaign.name)
            .having(func.avg(AdMetric.frequency) > 4.0)
        )
        for row in r2.all():
            alerts.append({
                "type": "high_frequency",
                "severity": "high",
                "message": f"😫 Anúncio '{row.name}' com frequência {float(row.freq):.1f}x — público saturado, precisa de criativo novo",
                "campaign": row.campaign,
            })

        # CTR muito baixo
        r3 = await self._s.execute(
            select(Ad.name, Campaign.name.label("campaign"), func.avg(AdMetric.ctr).label("ctr"), func.sum(AdMetric.impressions).label("imps"))
            .join(AdMetric, Ad.id == AdMetric.ad_id)
            .join(AdSet, Ad.adset_id == AdSet.id)
            .join(Campaign, AdSet.campaign_id == Campaign.id)
            .join(MetaAccount, Campaign.meta_account_id == MetaAccount.id)
            .where(
                MetaAccount.tenant_id == tenant_id,
                AdMetric.date >= since,
                Ad.status == "ACTIVE",
            )
            .group_by(Ad.id, Ad.name, Campaign.name)
            .having(
                func.avg(AdMetric.ctr) < 0.5,
                func.sum(AdMetric.impressions) > 2000,
            )
        )
        for row in r3.all():
            alerts.append({
                "type": "low_ctr",
                "severity": "medium",
                "message": f"📉 Anúncio '{row.name}' com CTR {float(row.ctr):.2f}% ({int(row.imps):,} impressões) — criativo não está engajando",
                "campaign": row.campaign,
            })

        return alerts

    # ------------------------------------------------------------------
    # Intelligence / scoring
    # ------------------------------------------------------------------

    def _grade(self, roas: float, ctr: float, cpa: float) -> str:
        score = 0
        if roas >= 4: score += 3
        elif roas >= 2: score += 2
        elif roas >= 1: score += 1
        if ctr >= 2: score += 2
        elif ctr >= 1: score += 1
        if 0 < cpa < 50: score += 2
        elif cpa < 100: score += 1
        if score >= 6: return "S"
        if score >= 4: return "A"
        if score >= 2: return "B"
        return "C"

    def _diagnose_problem(self, roas: float, ctr: float, cpa: float, freq: float, spend: float, conversions: int) -> str:
        if conversions == 0 and spend > 30:
            return "Sem conversões — criativo ou público inadequado"
        if roas < 0.5 and spend > 20:
            return "ROAS negativo — prejuízo confirmado, pausar imediatamente"
        if freq > 4:
            return f"Frequência {freq:.1f}x — público esgotado, trocar criativo"
        if ctr < 0.3:
            return "CTR < 0.3% — anúncio não atrai cliques, revisar copy e imagem"
        if cpa > 200:
            return f"CPA R${cpa:.0f} — custo por conversão muito alto"
        return "Performance abaixo da média"

    def _variation(self, current: dict, previous: dict) -> dict:
        def pct(a, b):
            if b == 0:
                return None
            return round((a - b) / b * 100, 1)
        return {
            "spend": pct(current["spend"], previous["spend"]),
            "conversions": pct(current["conversions"], previous["conversions"]),
            "roas": pct(current["roas"], previous["roas"]),
            "ctr": pct(current["ctr"], previous["ctr"]),
        }

    def _build_recommendations(self, kpis: dict, top: list, worst: list, alerts: list) -> list[str]:
        recs = []

        critical = [a for a in alerts if a["severity"] == "critical"]
        if critical:
            recs.append(f"🚨 URGENTE: {len(critical)} anúncio(s) gastando dinheiro sem retorno — pausar hoje")

        if kpis["roas"] < 1 and kpis["spend"] > 0:
            recs.append("⛔ ROAS geral < 1x — a conta está no prejuízo. Revisar targeting e ofertas imediatamente")
        elif kpis["roas"] < 2:
            recs.append("⚠️ ROAS < 2x — performance abaixo do ideal. Focar orçamento nos top performers")
        elif kpis["roas"] >= 3:
            recs.append(f"✅ ROAS {kpis['roas']:.1f}x excelente — considerar aumentar orçamento nas campanhas vencedoras")

        if kpis["frequency"] > 3.5:
            recs.append(f"🔄 Frequência média {kpis['frequency']:.1f}x — renovar criativos para evitar fadiga do público")

        if kpis["ctr"] < 0.8:
            recs.append("📢 CTR geral baixo — testar novos criativos, headlines e chamadas para ação")

        high_roas = [c for c in top if c["roas"] >= 3]
        if high_roas:
            names = ", ".join(c["name"][:25] for c in high_roas[:2])
            recs.append(f"🚀 Escalar orçamento em: {names} (ROAS > 3x)")

        zero_conv = [c for c in worst if c["conversions"] == 0 and c["spend"] > 50]
        if zero_conv:
            names = ", ".join(c["name"][:25] for c in zero_conv[:2])
            recs.append(f"🛑 Pausar campanhas sem conversão: {names}")

        if not recs:
            recs.append("✅ Performance dentro do esperado — manter monitoramento contínuo")

        return recs

    def _executive_summary(self, k7: dict, k30: dict, top: list, alerts: list) -> str:
        status = "CRÍTICO" if k7["roas"] < 1 else "ATENÇÃO" if k7["roas"] < 2 else "BOM" if k7["roas"] < 3 else "EXCELENTE"
        criticos = len([a for a in alerts if a["severity"] == "critical"])
        best = top[0]["name"][:30] if top else "N/A"

        return (
            f"Status da conta: {status} | "
            f"Gasto 7d: R${k7['spend']:.0f} | "
            f"ROAS: {k7['roas']:.2f}x | "
            f"Conversões: {k7['conversions']} | "
            f"Alertas críticos: {criticos} | "
            f"Melhor campanha: {best}"
        )

    def _empty_report(self, tenant_id: str) -> dict:
        return {"error": "Nenhuma conta ativa encontrada", "tenant_id": tenant_id}

    async def _save_insight(self, tenant_id: str, agent_name: str, title: str, summary: str, details: dict):
        import json
        from sqlalchemy import text, bindparam, String
        details_json = json.dumps(details, ensure_ascii=False, default=str)
        await self._s.execute(
            text(
                "INSERT INTO agent_insights (tenant_id, agent_name, title, summary, details, actions_taken)"
                " VALUES (:tid, :agent, :title, :summary, to_jsonb(:details), 0)"
            ).bindparams(bindparam("details", type_=String())),
            {
                "tid": tenant_id,
                "agent": agent_name,
                "title": title,
                "summary": summary,
                "details": details_json,
            },
        )
        await self._s.flush()
