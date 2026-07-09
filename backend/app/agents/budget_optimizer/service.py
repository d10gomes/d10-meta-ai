"""
Budget Optimizer Agent — Papel: OTIMIZADOR DE ORÇAMENTO
- Lê decisões do Decision Agent e análises do Analyst
- Calcula redistribuição ótima de budget entre campanhas
- Usa Claude para raciocinar sobre a melhor alocação
- Mantém histórico de ajustes e seus impactos para aprender
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.base import AgentBase
from app.core.logging import logger
from app.db.models import Campaign, AdSet, Ad, AdMetric, MetaAccount, AgentAction


class BudgetOptimizerService(AgentBase):
    name = "budget_optimizer"

    SYSTEM_PROMPT = """Você é um especialista em otimização de orçamento para Meta Ads.
Sua função é redistribuir o budget de forma inteligente para maximizar o ROAS global.

Regras:
- Nunca reduza mais de 30% de um budget de uma vez
- Nunca aumente mais de 50% de uma vez
- Se ROAS < 1.0 por mais de 3 dias: pause ou reduza 30%
- Se ROAS > 3.0 por mais de 3 dias: aumente até 30%
- Mantenha pelo menos 20% do budget para testes
- Considere o histórico de ajustes anteriores

Responda em JSON com:
{
  "total_budget_atual": número,
  "recomendacoes": [
    {
      "campaign_id": "id",
      "campaign_name": "nome",
      "budget_atual": número,
      "budget_sugerido": número,
      "variacao_pct": número,
      "razao": "texto",
      "prioridade": "alta|media|baixa"
    }
  ],
  "resumo": "texto explicativo"
}"""

    async def run(self, tenant_id: str) -> dict[str, Any]:
        self._tenant_id = tenant_id

        # 1. Ler insights do Analyst e decisões do Decision
        analyst_data = await self.read_knowledge(
            source_agent="analyst", entry_type="insight", only_unread=False, limit=3
        )
        decision_data = await self.read_knowledge(
            source_agent="decision", entry_type="decision", only_unread=True, limit=10
        )

        # 2. Buscar dados de budget e ROAS por campanha (últimos 7 dias)
        since_7d = datetime.utcnow() - timedelta(days=7)
        campaign_data = await self._get_campaign_budgets_and_roas(tenant_id, since_7d)

        if not campaign_data:
            return {"message": "Sem campanhas com dados suficientes", "recommendations": []}

        # 3. Recuperar histórico de ajustes anteriores
        past_adjustments = await self.recall(memory_type="decision", limit=15)
        past_results = await self.recall(memory_type="outcome", limit=10)

        history_text = self._format_history(past_adjustments, past_results)
        analyst_summary = analyst_data[0]["summary"] if analyst_data else "Sem análise disponível"
        decision_summary = "\n".join([d["summary"] for d in decision_data]) if decision_data else "Sem decisões"

        # 4. Claude calcula redistribuição ótima
        raw_response = await self.ai_think(
            system_prompt=self.SYSTEM_PROMPT,
            user_message=f"""Otimize o budget das seguintes campanhas:

CAMPANHAS E PERFORMANCE:
{json.dumps(campaign_data, ensure_ascii=False, indent=2)}

ANÁLISE ATUAL DO SISTEMA:
{analyst_summary}

DECISÕES DO AGENTE DECISOR:
{decision_summary}

HISTÓRICO DE AJUSTES ANTERIORES:
{history_text}

Calcule a redistribuição ótima em JSON.""",
            max_tokens=2000,
        )

        recommendations = self._parse_recommendations(raw_response)

        # 5. Salvar cada recomendação na memória
        for rec in recommendations.get("recomendacoes", []):
            await self.remember(
                key=f"budget_adj_{rec.get('campaign_id', 'unknown')}_{datetime.utcnow().strftime('%Y%m%d')}",
                content=rec,
                memory_type="decision",
                importance=7,
                ttl_days=14,
            )

            # Criar AgentAction para o Executor
            if abs(rec.get("variacao_pct", 0)) > 5:
                action = AgentAction(
                    tenant_id=tenant_id,
                    action_type="AJUSTAR_BUDGET",
                    entity_type="campaign",
                    entity_id=rec.get("campaign_id"),
                    payload=rec,
                    status="pending",
                )
                self._s.add(action)

        await self._s.flush()

        # 6. Publicar resultados para o Executor e Reporter
        await self.publish_knowledge(
            topic="budget_optimization",
            entry_type="recommendation",
            content=recommendations,
            summary=recommendations.get("resumo", "Otimização de budget calculada"),
            confidence=0.85,
            ttl_hours=12,
        )

        logger.info("budget_optimizer.done", tenant_id=tenant_id,
                    recs=len(recommendations.get("recomendacoes", [])))
        return recommendations

    def _format_history(self, past_adj: list, past_res: list) -> str:
        if not past_adj:
            return "Nenhum ajuste anterior registrado."
        lines = []
        for adj in past_adj[:5]:
            c = adj["content"]
            lines.append(
                f"- {c.get('campaign_name', '?')}: {c.get('variacao_pct', 0):+.0f}% "
                f"(Budget: R${c.get('budget_atual', 0):.0f} → R${c.get('budget_sugerido', 0):.0f})"
            )
        return "\n".join(lines)

    def _parse_recommendations(self, raw: str) -> dict:
        try:
            start = raw.find("{")
            end = raw.rfind("}") + 1
            if start >= 0:
                return json.loads(raw[start:end])
        except Exception:
            pass
        return {"recomendacoes": [], "resumo": raw[:300]}

    async def _get_campaign_budgets_and_roas(self, tenant_id: str, since: datetime) -> list[dict]:
        result = await self._s.execute(
            select(
                Campaign.id,
                Campaign.name,
                Campaign.daily_budget,
                Campaign.lifetime_budget,
                func.sum(AdMetric.spend).label("spend_7d"),
                func.avg(AdMetric.roas).label("avg_roas"),
                func.avg(AdMetric.ctr).label("avg_ctr"),
                func.sum(AdMetric.conversions).label("conversions"),
            )
            .join(MetaAccount, Campaign.meta_account_id == MetaAccount.id)
            .join(AdSet, Campaign.id == AdSet.campaign_id)
            .join(Ad, AdSet.id == Ad.adset_id)
            .join(AdMetric, Ad.id == AdMetric.ad_id)
            .where(
                and_(
                    MetaAccount.tenant_id == tenant_id,
                    AdMetric.date >= since,
                )
            )
            .group_by(Campaign.id, Campaign.name, Campaign.daily_budget, Campaign.lifetime_budget)
            .having(func.sum(AdMetric.spend) > 0)
        )
        return [
            {
                "campaign_id": str(r.id),
                "campaign_name": r.name,
                "daily_budget": float(r.daily_budget or 0),
                "spend_7d": round(float(r.spend_7d or 0), 2),
                "avg_roas": round(float(r.avg_roas or 0), 2),
                "avg_ctr": round(float(r.avg_ctr or 0), 2),
                "conversions_7d": int(r.conversions or 0),
            }
            for r in result.all()
        ]
