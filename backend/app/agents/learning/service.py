"""
Learning Agent — extrai lições estruturadas de campanhas e ações executadas.
Alimenta o Brain automaticamente. O sistema nunca perde conhecimento.

Roda após cada ciclo de otimização e após o encerramento de campanhas.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select, func, and_

from app.agents.base import AgentBase
from app.core import brain
from app.core.logging import logger
from app.db.models import Campaign, AdMetric, MetaAccount, AgentAction, AdSet, Ad, KnowledgeEntry


LEARNING_SYSTEM_PROMPT = """Você é o Learning Agent de uma plataforma de gestão de Meta Ads.
Sua missão é extrair lições estruturadas e permanentes de dados de performance.

Cada lição deve ser:
- Específica e acionável (não "melhorar CTR" mas "frequência acima de 3.5 reduz CTR em média 40%")
- Baseada em evidências dos dados
- Generalizável para outras campanhas

Tipos de lições:
- what_works: o que funcionou e por quê
- what_fails: o que não funcionou e por quê
- audience_insight: comportamento de audiência
- creative_insight: padrões de criativos
- budget_insight: padrões de alocação de budget

Responda em JSON:
{
  "lessons": [
    {
      "type": "what_works|what_fails|audience_insight|creative_insight|budget_insight",
      "title": "título curto",
      "lesson": "lição detalhada e acionável",
      "evidence": {"métrica": "valor que suporta a lição"},
      "context": {"nicho": "...", "objetivo": "..."},
      "confidence": 0.0-1.0,
      "applies_to": ["meta_ads", "lead_gen"]
    }
  ],
  "summary": "resumo do que foi aprendido neste ciclo"
}"""


class LearningService(AgentBase):
    name = "learning"

    async def run(self, tenant_id: str) -> dict[str, Any]:
        """Main learning cycle: extract lessons from recent performance data."""
        self._tenant_id = tenant_id

        since_30d = datetime.utcnow() - timedelta(days=30)
        since_7d = datetime.utcnow() - timedelta(days=7)

        # 1. Collect all recent agent insights and outcomes from KB
        analyst_insights = await self.read_knowledge(source_agent="analyst", only_unread=False, limit=5)
        doctor_insights = await self.read_knowledge(source_agent="doctor", only_unread=False, limit=5)
        creative_insights = await self.read_knowledge(source_agent="creative", only_unread=False, limit=3)
        budget_insights = await self.read_knowledge(source_agent="budget_optimizer", only_unread=False, limit=3)

        # 2. Fetch campaign performance data
        performance = await self._get_performance_data(tenant_id, since_30d)

        # 3. Fetch completed/executed actions and their outcomes
        action_outcomes = await self._get_action_outcomes(tenant_id, since_7d)

        # 4. Load existing lessons to avoid duplicates
        existing_lessons = brain.get_lessons("what_works", limit=10) + brain.get_lessons("what_fails", limit=10)
        existing_titles = {l.get("title", "") for l in existing_lessons}

        # 5. Claude extracts lessons
        all_summaries = "\n".join([
            e["summary"] for e in (analyst_insights + doctor_insights + creative_insights + budget_insights)
            if e.get("summary")
        ])

        raw = await self.ai_think(
            system_prompt=LEARNING_SYSTEM_PROMPT,
            user_message=f"""Extraia lições dos seguintes dados:

INSIGHTS DOS AGENTES (últimos 7 dias):
{all_summaries[:2000] or 'Nenhum insight disponível'}

PERFORMANCE DE CAMPANHAS (30 dias):
{json.dumps(performance[:10], ensure_ascii=False, indent=2)}

AÇÕES EXECUTADAS E RESULTADOS:
{json.dumps(action_outcomes[:10], ensure_ascii=False, indent=2)}

LIÇÕES JÁ EXISTENTES (evite duplicar):
{json.dumps(list(existing_titles), ensure_ascii=False)}

Extraia apenas lições NOVAS e baseadas em evidências reais.""",
            max_tokens=2000,
        )

        result = self._parse_lessons(raw)
        lessons = result.get("lessons", [])

        # 6. Save new lessons to Brain
        saved = 0
        for lesson in lessons:
            if lesson.get("title") not in existing_titles:
                lesson["tenant_id"] = tenant_id
                lesson["extracted_at"] = datetime.utcnow().isoformat()
                brain.save_lesson(lesson)
                saved += 1

                # Also save to agent memory for quick recall
                await self.remember(
                    key=f"lesson_{lesson['type']}_{datetime.utcnow().strftime('%Y%m%d%H%M')}",
                    content=lesson,
                    memory_type="learning",
                    importance=int(lesson.get("confidence", 0.7) * 10),
                    ttl_days=90,
                )

        # 7. Publish to KB so CEO Agent / Reporting can summarize
        await self.publish_knowledge(
            topic="learning_cycle",
            entry_type="insight",
            content=result,
            summary=f"{saved} novas lições extraídas. {result.get('summary', '')}",
            confidence=0.9,
            ttl_hours=168,  # 7 days
        )

        logger.info("learning.done", tenant_id=tenant_id, lessons_extracted=len(lessons), saved=saved)
        return {"lessons_extracted": len(lessons), "saved": saved, "summary": result.get("summary", "")}

    def _parse_lessons(self, raw: str) -> dict:
        try:
            start = raw.find("{")
            end = raw.rfind("}") + 1
            if start >= 0:
                return json.loads(raw[start:end])
        except Exception:
            pass
        return {"lessons": [], "summary": raw[:200]}

    async def _get_performance_data(self, tenant_id: str, since: datetime) -> list[dict]:
        try:
            result = await self._s.execute(
                select(
                    Campaign.id,
                    Campaign.name,
                    func.sum(AdMetric.spend).label("spend"),
                    func.avg(AdMetric.roas).label("roas"),
                    func.avg(AdMetric.ctr).label("ctr"),
                    func.avg(AdMetric.cpa).label("cpa"),
                    func.sum(AdMetric.conversions).label("conversions"),
                    func.avg(AdMetric.frequency).label("frequency"),
                )
                .join(MetaAccount, Campaign.meta_account_id == MetaAccount.id)
                .join(AdSet, Campaign.id == AdSet.campaign_id)
                .join(Ad, AdSet.id == Ad.adset_id)
                .join(AdMetric, Ad.id == AdMetric.ad_id)
                .where(and_(MetaAccount.tenant_id == tenant_id, AdMetric.date >= since))
                .group_by(Campaign.id, Campaign.name)
                .having(func.sum(AdMetric.spend) > 0)
                .order_by(func.sum(AdMetric.spend).desc())
            )
            return [
                {
                    "campaign": r.name,
                    "spend": round(float(r.spend or 0), 2),
                    "roas": round(float(r.roas or 0), 2),
                    "ctr": round(float(r.ctr or 0), 3),
                    "cpa": round(float(r.cpa or 0), 2),
                    "conversions": int(r.conversions or 0),
                    "frequency": round(float(r.frequency or 0), 2),
                    "profitable": float(r.roas or 0) >= 2.0,
                }
                for r in result.all()
            ]
        except Exception as exc:
            logger.warning("learning.performance_error", error=str(exc))
            return []

    async def _get_action_outcomes(self, tenant_id: str, since: datetime) -> list[dict]:
        try:
            result = await self._s.execute(
                select(AgentAction)
                .where(
                    and_(
                        AgentAction.tenant_id == tenant_id,
                        AgentAction.created_at >= since,
                        AgentAction.status.in_(["completed", "failed"]),
                    )
                )
                .limit(20)
            )
            return [
                {
                    "action": a.action_type,
                    "entity": f"{a.entity_type}:{a.entity_id}",
                    "status": a.status,
                    "payload": a.payload,
                }
                for a in result.scalars().all()
            ]
        except Exception as exc:
            logger.warning("learning.actions_error", error=str(exc))
            return []
