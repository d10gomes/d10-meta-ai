"""
Analyst Agent — Papel: ANALISTA DE PERFORMANCE
- Lê os dados brutos publicados pelo Scanner
- Usa Claude para identificar padrões, tendências e anomalias reais
- Publica insights na Knowledge Base para o Optimizer e Decision lerem
- Mantém memória do histórico de análises anteriores para comparação
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.base import AgentBase
from app.core.logging import logger
from app.db.models import Campaign, AdSet, Ad, AdMetric, MetaAccount, AgentInsight, Tenant


class AnalystService(AgentBase):
    name = "analyst"

    SYSTEM_PROMPT = """Você é um especialista sênior em Meta Ads com 10 anos de experiência.
Analise os dados de campanhas fornecidos e identifique:
1. Tendências de performance (melhora ou piora)
2. Anomalias (gastos anormais, CTR muito baixo, ROAS negativo)
3. Oportunidades de otimização específicas e acionáveis
4. Campanhas que precisam de atenção imediata

Responda SEMPRE em português brasileiro.
Seja direto e específico — mencione nomes de campanhas, valores exatos.
Priorize insights que podem gerar ação imediata."""

    async def run(self, tenant_id: str) -> dict[str, Any]:
        self._tenant_id = tenant_id

        # 1. Ler o que o Scanner publicou
        scanner_data = await self.read_knowledge(
            source_agent="scanner",
            entry_type="raw_data",
            only_unread=False,
            limit=10,
        )

        # 2. Buscar KPIs do banco diretamente
        since_7d = datetime.utcnow() - timedelta(days=7)
        since_30d = datetime.utcnow() - timedelta(days=30)
        kpis_7d = await self._aggregate_kpis(tenant_id, since_7d)
        kpis_30d = await self._aggregate_kpis(tenant_id, since_30d)
        top_campaigns = await self._top_campaigns(tenant_id, since_7d, limit=5)
        worst_campaigns = await self._worst_campaigns(tenant_id, since_7d, limit=5)

        # 3. Recuperar análises anteriores da memória para comparação
        past_analyses = await self.recall(memory_type="observation", limit=5)
        past_context = ""
        if past_analyses:
            last = past_analyses[0]["content"]
            past_context = f"""
Na última análise ({past_analyses[0]['created_at'][:10]}):
- ROAS médio: {last.get('avg_roas', 'N/A')}
- CTR médio: {last.get('avg_ctr', 'N/A')}%
- Gasto total 7d: R$ {last.get('total_spend_7d', 'N/A')}
- Principais problemas: {', '.join(last.get('top_issues', []))}
"""

        # 4. Chamar Claude para análise real
        if kpis_7d.get("total_spend", 0) > 0 or scanner_data:
            data_para_analise = {
                "periodo": "últimos 7 dias",
                "kpis_7d": kpis_7d,
                "kpis_30d": kpis_30d,
                "top_5_campanhas": top_campaigns,
                "piores_5_campanhas": worst_campaigns,
                "dados_scanner": [e["summary"] for e in scanner_data[:3]],
                "historico": past_context,
            }

            ai_analysis = await self.ai_think(
                system_prompt=self.SYSTEM_PROMPT,
                user_message=f"""Analise esses dados de Meta Ads e forneça insights acionáveis:

{json.dumps(data_para_analise, ensure_ascii=False, indent=2)}

Estruture sua resposta em:
## Situação Geral
## Alertas Urgentes (se houver)
## Top Oportunidades (3-5 ações concretas)
## Comparação com período anterior""",
                max_tokens=1500,
            )
        else:
            ai_analysis = "Sem dados suficientes para análise. Aguardando primeiras coletas do Scanner."

        # 5. Detectar alertas por regras (complemento ao Claude)
        alerts = self._rule_based_alerts(kpis_7d, worst_campaigns)

        # 6. Salvar na memória para comparações futuras
        await self.remember(
            key=f"analysis_{datetime.utcnow().strftime('%Y%m%d')}",
            content={
                "avg_roas": kpis_7d.get("avg_roas"),
                "avg_ctr": kpis_7d.get("avg_ctr"),
                "total_spend_7d": kpis_7d.get("total_spend"),
                "top_issues": [a["issue"] for a in alerts[:3]],
                "campaigns_analyzed": len(top_campaigns) + len(worst_campaigns),
            },
            memory_type="observation",
            importance=7,
            ttl_days=30,
        )

        # 7. Publicar na Knowledge Base para outros agentes
        await self.publish_knowledge(
            topic="performance_analysis",
            entry_type="insight",
            content={
                "ai_analysis": ai_analysis,
                "kpis_7d": kpis_7d,
                "kpis_30d": kpis_30d,
                "top_campaigns": top_campaigns,
                "worst_campaigns": worst_campaigns,
                "alerts": alerts,
            },
            summary=ai_analysis[:500] if ai_analysis else "Análise vazia",
            confidence=0.9,
            ttl_hours=24,
        )

        # Publicar alertas separadamente com alta prioridade
        for alert in alerts:
            await self.publish_knowledge(
                topic=f"alert_{alert['type']}",
                entry_type="alert",
                content=alert,
                summary=alert["message"],
                confidence=1.0,
                ttl_hours=12,
            )

        # 8. Salvar insight no banco para o frontend ver
        await self._save_insight(tenant_id, ai_analysis, kpis_7d, alerts)

        result = {
            "tenant_id": tenant_id,
            "ai_analysis": ai_analysis,
            "kpis_7d": kpis_7d,
            "alerts_count": len(alerts),
            "ran_at": datetime.utcnow().isoformat(),
        }
        logger.info("analyst.done", tenant_id=tenant_id, alerts=len(alerts))
        return result

    def _rule_based_alerts(self, kpis: dict, worst: list) -> list[dict]:
        alerts = []
        if kpis.get("avg_roas", 999) < 1.0 and kpis.get("total_spend", 0) > 0:
            alerts.append({
                "type": "negative_roas",
                "severity": "critical",
                "issue": "ROAS abaixo de 1.0",
                "message": f"ROAS médio {kpis['avg_roas']:.2f} — gastando mais do que recebendo",
            })
        if kpis.get("avg_ctr", 999) < 0.5 and kpis.get("total_spend", 0) > 0:
            alerts.append({
                "type": "low_ctr",
                "severity": "high",
                "issue": "CTR muito baixo",
                "message": f"CTR médio {kpis['avg_ctr']:.2f}% — criativos precisam de revisão",
            })
        for camp in worst[:2]:
            if camp.get("spend", 0) > 100 and camp.get("roas", 0) < 0.5:
                alerts.append({
                    "type": "drain_campaign",
                    "severity": "high",
                    "issue": f"Campanha drenando budget",
                    "message": f"'{camp.get('name')}' gastou R${camp['spend']:.0f} com ROAS {camp.get('roas', 0):.2f}",
                    "campaign_id": camp.get("id"),
                })
        return alerts

    async def _save_insight(self, tenant_id: str, analysis: str, kpis: dict, alerts: list):
        from sqlalchemy import String
        from sqlalchemy.sql.expression import bindparam
        insight = AgentInsight(
            tenant_id=tenant_id,
            agent_name=self.name,
            title=f"Análise de Performance — {datetime.now().strftime('%d/%m/%Y %H:%M')}",
            summary=analysis[:1000] if analysis else "Sem dados",
            details={
                "kpis": kpis,
                "alerts": alerts,
                "ai_powered": True,
            },
            actions_taken=len(alerts),
        )
        self._s.add(insight)
        await self._s.flush()

    async def _aggregate_kpis(self, tenant_id: str, since: datetime) -> dict:
        result = await self._s.execute(
            select(
                func.sum(AdMetric.spend).label("total_spend"),
                func.sum(AdMetric.revenue).label("total_revenue"),
                func.sum(AdMetric.impressions).label("total_impressions"),
                func.sum(AdMetric.clicks).label("total_clicks"),
                func.sum(AdMetric.conversions).label("total_conversions"),
                func.avg(AdMetric.roas).label("avg_roas"),
                func.avg(AdMetric.ctr).label("avg_ctr"),
                func.avg(AdMetric.cpc).label("avg_cpc"),
                func.avg(AdMetric.cpm).label("avg_cpm"),
            ).join(Ad, AdMetric.ad_id == Ad.id)
            .join(AdSet, Ad.adset_id == AdSet.id)
            .join(Campaign, AdSet.campaign_id == Campaign.id)
            .join(MetaAccount, Campaign.meta_account_id == MetaAccount.id)
            .where(
                and_(
                    MetaAccount.tenant_id == tenant_id,
                    AdMetric.date >= since,
                )
            )
        )
        row = result.one_or_none()
        if not row or not row.total_spend:
            return {"total_spend": 0, "total_revenue": 0, "avg_roas": 0, "avg_ctr": 0}

        spend = float(row.total_spend or 0)
        revenue = float(row.total_revenue or 0)
        return {
            "total_spend": round(spend, 2),
            "total_revenue": round(revenue, 2),
            "total_impressions": int(row.total_impressions or 0),
            "total_clicks": int(row.total_clicks or 0),
            "total_conversions": int(row.total_conversions or 0),
            "avg_roas": round(float(row.avg_roas or 0), 2),
            "avg_ctr": round(float(row.avg_ctr or 0), 2),
            "avg_cpc": round(float(row.avg_cpc or 0), 2),
            "avg_cpm": round(float(row.avg_cpm or 0), 2),
            "overall_roas": round(revenue / spend, 2) if spend > 0 else 0,
        }

    async def _top_campaigns(self, tenant_id: str, since: datetime, limit: int = 5) -> list[dict]:
        return await self._campaign_ranking(tenant_id, since, limit, order="desc")

    async def _worst_campaigns(self, tenant_id: str, since: datetime, limit: int = 5) -> list[dict]:
        return await self._campaign_ranking(tenant_id, since, limit, order="asc")

    async def _campaign_ranking(self, tenant_id: str, since: datetime, limit: int, order: str) -> list[dict]:
        col = func.avg(AdMetric.roas)
        order_col = col.desc() if order == "desc" else col.asc()
        result = await self._s.execute(
            select(
                Campaign.id,
                Campaign.name,
                func.sum(AdMetric.spend).label("spend"),
                func.sum(AdMetric.revenue).label("revenue"),
                func.avg(AdMetric.roas).label("roas"),
                func.avg(AdMetric.ctr).label("ctr"),
            )
            .join(AdSet, Campaign.id == AdSet.campaign_id)
            .join(Ad, AdSet.id == Ad.adset_id)
            .join(AdMetric, Ad.id == AdMetric.ad_id)
            .join(MetaAccount, Campaign.meta_account_id == MetaAccount.id)
            .where(
                and_(
                    MetaAccount.tenant_id == tenant_id,
                    AdMetric.date >= since,
                    AdMetric.spend > 0,
                )
            )
            .group_by(Campaign.id, Campaign.name)
            .order_by(order_col)
            .limit(limit)
        )
        return [
            {
                "id": str(r.id),
                "name": r.name,
                "spend": round(float(r.spend or 0), 2),
                "revenue": round(float(r.revenue or 0), 2),
                "roas": round(float(r.roas or 0), 2),
                "ctr": round(float(r.ctr or 0), 2),
            }
            for r in result.all()
        ]
