"""
Simulation Layer — toda ação crítica passa por aqui antes de ser executada.
Simula impacto, gera estimativas, define plano de rollback e requer aprovação.

Ações críticas que EXIGEM simulação:
- Pausar campanha
- Reduzir budget > 20%
- Aumentar budget > 30%
- Mudar targeting de adset
- Pausar múltiplos anúncios

Ações seguras que podem executar diretamente:
- Ajuste de budget < 5%
- Geração de relatórios
- Alertas e notificações
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from sqlalchemy import select

from app.agents.base import AgentBase
from app.core.logging import logger
from app.db.models import AgentAction, AdMetric, Campaign, MetaAccount, AdSet, Ad
from sqlalchemy import and_, func
from datetime import timedelta


SIMULATION_THRESHOLDS = {
    "PAUSAR_CAMPANHA":     {"requires_simulation": True,  "requires_approval": True},
    "REDUZIR_BUDGET":      {"requires_simulation": True,  "requires_approval": lambda pct: abs(pct) > 20},
    "AUMENTAR_BUDGET":     {"requires_simulation": True,  "requires_approval": lambda pct: pct > 30},
    "REVISAR_CRIATIVO":    {"requires_simulation": False, "requires_approval": False},
    "AJUSTAR_BUDGET":      {"requires_simulation": True,  "requires_approval": lambda pct: abs(pct) > 15},
    "MONITORAR":           {"requires_simulation": False, "requires_approval": False},
    "PAUSAR_ADSET":        {"requires_simulation": True,  "requires_approval": True},
}

SIMULATION_SYSTEM_PROMPT = """Você é um simulador de impacto para campanhas de Meta Ads.
Dado uma ação proposta e os dados históricos da campanha, estime o impacto.

Seja conservador e realista. Use os dados históricos para fundamentar as estimativas.

Responda em JSON:
{
  "can_proceed": true/false,
  "risk_level": "low|medium|high|critical",
  "impact_estimate": {
    "roas_change_pct": número,
    "spend_change_pct": número,
    "conversions_change_pct": número,
    "estimated_daily_impact_brl": número
  },
  "risk_factors": ["fator 1", "fator 2"],
  "rollback_plan": {
    "steps": ["passo 1 para reverter", "passo 2"],
    "rollback_time_minutes": 5,
    "data_loss": false
  },
  "recommendation": "texto com recomendação final",
  "confidence": 0.0-1.0
}"""


class SimulationService(AgentBase):
    name = "simulation"

    async def simulate(self, action: AgentAction | dict, tenant_id: str) -> dict[str, Any]:
        """Run simulation for a proposed action. Returns simulation result."""
        self._tenant_id = tenant_id

        if isinstance(action, AgentAction):
            action_dict = {
                "id": str(action.id),
                "action_type": action.action_type,
                "entity_type": action.entity_type,
                "entity_id": action.entity_id,
                "payload": action.payload or {},
            }
        else:
            action_dict = action

        action_type = action_dict.get("action_type", "")
        thresholds = SIMULATION_THRESHOLDS.get(action_type, {
            "requires_simulation": True,
            "requires_approval": True,
        })

        # Determine if approval is needed
        pct = action_dict.get("payload", {}).get("variacao_pct", 0)
        approval_rule = thresholds.get("requires_approval", False)
        requires_approval = approval_rule(pct) if callable(approval_rule) else approval_rule

        # Get historical metrics for context
        entity_id = action_dict.get("entity_id")
        history = await self._get_entity_history(entity_id, action_dict.get("entity_type", "campaign"), tenant_id)

        # Claude estimates impact
        raw = await self.ai_think(
            system_prompt=SIMULATION_SYSTEM_PROMPT,
            user_message=f"""AÇÃO PROPOSTA:
Tipo: {action_type}
Alvo: {action_dict.get('entity_type')} {entity_id}
Parâmetros: {json.dumps(action_dict.get('payload', {}), ensure_ascii=False)}

HISTÓRICO DA ENTIDADE (últimos 14 dias):
{json.dumps(history, ensure_ascii=False, indent=2)}

Estime o impacto desta ação em JSON.""",
            max_tokens=1000,
        )

        sim_result = self._parse_sim(raw)
        sim_result["action_id"] = action_dict.get("id")
        sim_result["action_type"] = action_type
        sim_result["requires_approval"] = requires_approval
        sim_result["simulated_at"] = datetime.utcnow().isoformat()
        sim_result["tenant_id"] = tenant_id

        # Save simulation to memory
        await self.remember(
            key=f"sim_{action_dict.get('id', 'unknown')}",
            content=sim_result,
            memory_type="observation",
            importance=7,
            ttl_days=30,
        )

        # Publish to KB so Decision/Executor can read
        await self.publish_knowledge(
            topic=f"simulation_{action_type}_{entity_id}",
            entry_type="recommendation",
            content=sim_result,
            summary=(
                f"Simulação {action_type}: risco {sim_result.get('risk_level', '?').upper()}, "
                f"impacto estimado ROAS {sim_result.get('impact_estimate', {}).get('roas_change_pct', 0):+.1f}%"
            ),
            confidence=sim_result.get("confidence", 0.7),
            ttl_hours=24,
        )

        logger.info(
            "simulation.done",
            action=action_type,
            risk=sim_result.get("risk_level"),
            can_proceed=sim_result.get("can_proceed"),
            requires_approval=requires_approval,
        )
        return sim_result

    async def approve(self, action_id: str, approved_by_user_id: str, tenant_id: str) -> dict:
        """Mark a simulated action as approved for execution."""
        self._tenant_id = tenant_id
        from sqlalchemy import update

        await self._s.execute(
            update(AgentAction)
            .where(AgentAction.id == action_id)
            .values(
                status="approved",
                approved_by=approved_by_user_id,
                approved_at=datetime.utcnow(),
            )
        )
        await self._s.flush()
        logger.info("simulation.approved", action_id=action_id, by=approved_by_user_id)
        return {"approved": True, "action_id": action_id}

    async def reject(self, action_id: str, rejected_by_user_id: str, tenant_id: str, reason: str = "") -> dict:
        """Reject a proposed action."""
        self._tenant_id = tenant_id
        from sqlalchemy import update

        await self._s.execute(
            update(AgentAction)
            .where(AgentAction.id == action_id)
            .values(status="rejected", error=reason or "Rejeitado pelo usuário")
        )
        await self._s.flush()
        logger.info("simulation.rejected", action_id=action_id, reason=reason)
        return {"rejected": True, "action_id": action_id}

    def _parse_sim(self, raw: str) -> dict:
        try:
            start = raw.find("{")
            end = raw.rfind("}") + 1
            if start >= 0:
                return json.loads(raw[start:end])
        except Exception:
            pass
        return {
            "can_proceed": False,
            "risk_level": "high",
            "impact_estimate": {},
            "risk_factors": ["Erro ao parsear simulação"],
            "rollback_plan": {"steps": [], "rollback_time_minutes": 5, "data_loss": False},
            "recommendation": raw[:300],
            "confidence": 0.3,
        }

    async def _get_entity_history(self, entity_id: str | None, entity_type: str, tenant_id: str) -> dict:
        if not entity_id or entity_type != "campaign":
            return {}
        since = datetime.utcnow() - timedelta(days=14)
        try:
            result = await self._s.execute(
                select(
                    func.sum(AdMetric.spend).label("total_spend"),
                    func.avg(AdMetric.roas).label("avg_roas"),
                    func.avg(AdMetric.ctr).label("avg_ctr"),
                    func.avg(AdMetric.cpa).label("avg_cpa"),
                    func.sum(AdMetric.conversions).label("total_conversions"),
                    func.avg(AdMetric.frequency).label("avg_frequency"),
                    Campaign.daily_budget,
                    Campaign.name,
                )
                .join(AdSet, Campaign.id == AdSet.campaign_id)
                .join(Ad, AdSet.id == Ad.adset_id)
                .join(AdMetric, Ad.id == AdMetric.ad_id)
                .join(MetaAccount, Campaign.meta_account_id == MetaAccount.id)
                .where(
                    and_(
                        Campaign.id == entity_id,
                        MetaAccount.tenant_id == tenant_id,
                        AdMetric.date >= since,
                    )
                )
                .group_by(Campaign.id, Campaign.name, Campaign.daily_budget)
            )
            row = result.one_or_none()
            if not row:
                return {}
            return {
                "campaign_name": row.name,
                "daily_budget": float(row.daily_budget or 0),
                "total_spend_14d": round(float(row.total_spend or 0), 2),
                "avg_roas": round(float(row.avg_roas or 0), 2),
                "avg_ctr": round(float(row.avg_ctr or 0), 3),
                "avg_cpa": round(float(row.avg_cpa or 0), 2),
                "total_conversions": int(row.total_conversions or 0),
                "avg_frequency": round(float(row.avg_frequency or 0), 2),
            }
        except Exception as exc:
            logger.warning("simulation.history_error", error=str(exc))
            return {}
