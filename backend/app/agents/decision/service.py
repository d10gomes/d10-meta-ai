"""
Decision Agent — Papel: TOMADOR DE DECISÕES
- Lê insights do Analyst e alertas da Knowledge Base
- Usa Claude para deliberar sobre qual ação tomar
- Lembra de decisões anteriores e seus resultados para aprender
- Publica decisões para o Executor implementar
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.base import AgentBase
from app.core.logging import logger
from app.db.models import AgentAction, Tenant


class DecisionService(AgentBase):
    name = "decision"

    SYSTEM_PROMPT = """Você é o agente decisor de uma plataforma de gestão de Meta Ads.
Você recebe análises de performance e alertas, e precisa decidir quais ações tomar.

Princípios:
- Seja conservador em mudanças: prefira ajustes graduais (±20%) a mudanças radicais
- Priorize parar campanhas que estão perdendo dinheiro (ROAS < 0.5)
- Só recomende aumentar budget em campanhas com ROAS > 2.0 por pelo menos 3 dias
- Aprenda com decisões passadas que não funcionaram — não repita erros

Para cada decisão, especifique:
- Ação: [PAUSAR_CAMPANHA / REDUZIR_BUDGET / AUMENTAR_BUDGET / REVISAR_CRIATIVO / MONITORAR]
- Alvo: nome/ID da campanha
- Magnitude: quanto (%) ou simplesmente monitorar
- Justificativa: por que essa decisão agora
- Confiança: 0.0 a 1.0

Responda em JSON válido com a chave "decisions" contendo lista de decisões."""

    async def run(self, tenant_id: str) -> dict[str, Any]:
        self._tenant_id = tenant_id

        # 1. Ler o que o Analyst publicou
        analyst_insights = await self.read_knowledge(
            source_agent="analyst",
            entry_type="insight",
            only_unread=True,
            limit=5,
        )
        alerts = await self.read_knowledge(
            entry_type="alert",
            only_unread=True,
            limit=20,
        )

        if not analyst_insights and not alerts:
            logger.info("decision.no_input", tenant_id=tenant_id)
            return {"decisions": [], "reason": "Sem novos insights para processar"}

        # 2. Recuperar decisões anteriores e seus resultados
        past_decisions = await self.recall(memory_type="decision", limit=10)
        past_outcomes = await self.recall(memory_type="outcome", limit=10)

        learning_context = self._build_learning_context(past_decisions, past_outcomes)

        # 3. Preparar contexto para Claude
        insights_text = "\n".join([
            f"[{e['source_agent']}] {e['summary']}" for e in analyst_insights
        ])
        alerts_text = "\n".join([
            f"[ALERTA {e['content'].get('severity','?').upper()}] {e['summary']}" for e in alerts
        ])

        # 4. Claude decide as ações
        raw_decision = await self.ai_think(
            system_prompt=self.SYSTEM_PROMPT,
            user_message=f"""Com base nos seguintes inputs, decida as ações necessárias:

INSIGHTS DO ANALISTA:
{insights_text or 'Nenhum insight novo'}

ALERTAS ATIVOS:
{alerts_text or 'Nenhum alerta'}

HISTÓRICO DE DECISÕES ANTERIORES E RESULTADOS:
{learning_context}

Tome decisões ponderadas considerando o histórico. Responda em JSON.""",
            max_tokens=1500,
        )

        # 5. Parsear decisões do Claude
        decisions = self._parse_decisions(raw_decision)

        # 6. Para cada decisão, salvar na memória e publicar para o Executor
        for dec in decisions:
            mem_key = f"decision_{dec.get('target_id', 'general')}_{datetime.utcnow().strftime('%Y%m%d%H')}"
            await self.remember(
                key=mem_key,
                content=dec,
                memory_type="decision",
                importance=8,
                ttl_days=14,
            )

            # Publicar para o Executor
            await self.publish_knowledge(
                topic=f"action_{dec.get('action', 'unknown')}",
                entry_type="decision",
                content=dec,
                summary=f"{dec.get('action')}: {dec.get('target')} — {dec.get('justification', '')[:100]}",
                confidence=dec.get("confidence", 0.7),
                ttl_hours=4,
            )

            # Registrar no banco como AgentAction
            if dec.get("confidence", 0) >= 0.7:
                await self._create_action(tenant_id, dec)

        result = {
            "tenant_id": tenant_id,
            "decisions_made": len(decisions),
            "decisions": decisions,
            "ran_at": datetime.utcnow().isoformat(),
        }
        logger.info("decision.done", tenant_id=tenant_id, decisions=len(decisions))
        return result

    def _build_learning_context(self, past_decisions: list, past_outcomes: list) -> str:
        if not past_decisions:
            return "Nenhuma decisão anterior registrada."
        lines = []
        for dec in past_decisions[:5]:
            c = dec["content"]
            lines.append(f"- {c.get('action')} em '{c.get('target')}' (confiança: {c.get('confidence')})")
        for out in past_outcomes[:5]:
            c = out["content"]
            lines.append(f"  → Resultado: {c.get('result', 'pendente')}")
        return "\n".join(lines)

    def _parse_decisions(self, raw: str) -> list[dict]:
        try:
            start = raw.find("{")
            end = raw.rfind("}") + 1
            if start >= 0 and end > start:
                data = json.loads(raw[start:end])
                return data.get("decisions", [])
        except Exception:
            pass
        # Fallback: retorna estrutura mínima
        return [{"action": "MONITORAR", "target": "geral", "justification": raw[:200], "confidence": 0.5}]

    async def _create_action(self, tenant_id: str, dec: dict):
        action = AgentAction(
            tenant_id=tenant_id,
            action_type=dec.get("action", "MONITORAR"),
            entity_type="campaign",
            entity_id=dec.get("target_id"),
            payload=dec,
            status="pending",
        )
        self._s.add(action)
        await self._s.flush()

    async def record_outcome(self, decision_key: str, result: str, impact: dict):
        """Called by Executor to report back results of executed actions."""
        await self.remember(
            key=f"outcome_{decision_key}_{datetime.utcnow().strftime('%Y%m%d')}",
            content={"decision_key": decision_key, "result": result, "impact": impact},
            memory_type="outcome",
            importance=9,
            ttl_days=60,
        )
