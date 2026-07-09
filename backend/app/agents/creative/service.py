"""
Creative Agent — Papel: ANALISTA DE CRIATIVOS
- Avalia criativos por CTR, CPA e ROAS
- Detecta fadiga de criativo (frequência alta + CTR caindo)
- Recomenda novos ângulos de copy e imagem com base no que funciona
- Publica na KB quais criativos pausar e quais escalar
- Lembra padrões de criativos vencedores ao longo do tempo
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.base import AgentBase
from app.core.logging import logger
from app.db.models import Campaign, AdSet, Ad, AdMetric, MetaAccount, AgentInsight


class CreativeService(AgentBase):
    name = "creative"

    SYSTEM_PROMPT = """Você é um especialista em criativos de Meta Ads com olhar clínico para o que funciona e o que falha.

Sua análise cobre:
- VENCEDORES: criativos com CTR > 2%, ROAS > 3.0, baixa frequência (< 2.5)
- FATIGADOS: CTR caindo + frequência > 3.0 = hora de pausar
- OPORTUNIDADES: padrões dos vencedores que podem ser replicados

Para cada criativo, avalie:
1. Saúde atual (saudável / fatigado / parar agora)
2. Por que está performando assim
3. O que testar a seguir (ângulo de copy, formato, CTA)

Responda em JSON:
{
  "winners": [{"ad_id": "id", "ad_name": "nome", "why_winning": "motivo", "scale_recommendation": "texto"}],
  "fatigued": [{"ad_id": "id", "ad_name": "nome", "symptoms": ["sintoma1"], "action": "PAUSAR|RENOVAR"}],
  "patterns": ["padrão 1 identificado", "padrão 2"],
  "new_angles": ["ângulo de copy 1", "ângulo 2", "ângulo 3"],
  "summary": "resumo executivo"
}"""

    async def run(self, tenant_id: str) -> dict[str, Any]:
        self._tenant_id = tenant_id

        since_14d = datetime.utcnow() - timedelta(days=14)
        since_7d = datetime.utcnow() - timedelta(days=7)

        # 1. Buscar métricas por anúncio (criativo)
        ad_metrics = await self._get_ad_level_metrics(tenant_id, since_14d)

        if not ad_metrics:
            return {"message": "Sem métricas de anúncios disponíveis", "winners": [], "fatigued": []}

        # 2. Ler diagnósticos do Doctor para correlacionar fadiga
        doctor_data = await self.read_knowledge(
            source_agent="doctor", entry_type="insight", only_unread=False, limit=3
        )

        # 3. Recuperar padrões de criativos vencedores anteriores
        past_winners = await self.recall(memory_type="learning", limit=10)
        past_patterns = "\n".join([
            f"- {m['content'].get('pattern', '')}" for m in past_winners[:5] if m["content"].get("pattern")
        ]) or "Nenhum padrão registrado ainda."

        doctor_context = doctor_data[0]["summary"] if doctor_data else "Sem diagnóstico disponível"

        # 4. Claude analisa os criativos
        raw_response = await self.ai_think(
            system_prompt=self.SYSTEM_PROMPT,
            user_message=f"""Analise os criativos em execução:

MÉTRICAS POR ANÚNCIO (14 dias):
{json.dumps(ad_metrics[:30], ensure_ascii=False, indent=2)}

CONTEXTO DO DIAGNÓSTICO:
{doctor_context}

PADRÕES DE VENCEDORES ANTERIORES:
{past_patterns}

Identifique vencedores, fatigados e novos ângulos em JSON.""",
            max_tokens=2000,
        )

        analysis = self._parse_analysis(raw_response)

        # 5. Salvar padrões dos vencedores na memória
        for winner in analysis.get("winners", []):
            await self.remember(
                key=f"winner_{winner.get('ad_id', 'unknown')}",
                content={
                    "ad_name": winner.get("ad_name"),
                    "why_winning": winner.get("why_winning"),
                    "pattern": winner.get("why_winning", ""),
                    "recorded_at": datetime.utcnow().isoformat(),
                },
                memory_type="learning",
                importance=9,
                ttl_days=60,
            )

        # 6. Salvar fatigados para evitar escalá-los por acidente
        for fatigued in analysis.get("fatigued", []):
            await self.remember(
                key=f"fatigued_{fatigued.get('ad_id', 'unknown')}",
                content={**fatigued, "flagged_at": datetime.utcnow().isoformat()},
                memory_type="observation",
                importance=7,
                ttl_days=14,
            )

        # 7. Publicar na KB para o Decision e Budget agentes
        await self.publish_knowledge(
            topic="creative_analysis",
            entry_type="insight",
            content=analysis,
            summary=analysis.get("summary", f"{len(analysis.get('winners', []))} vencedores, {len(analysis.get('fatigued', []))} fatigados"),
            confidence=0.85,
            ttl_hours=24,
        )

        # 8. Salvar insight no banco para o frontend
        insight = AgentInsight(
            tenant_id=tenant_id,
            agent_name=self.name,
            title=f"Análise de Criativos — {datetime.now().strftime('%d/%m/%Y')}",
            summary=analysis.get("summary", "")[:1000],
            details=analysis,
            actions_taken=len(analysis.get("fatigued", [])),
        )
        self._s.add(insight)
        await self._s.flush()

        logger.info(
            "creative.done",
            tenant_id=tenant_id,
            winners=len(analysis.get("winners", [])),
            fatigued=len(analysis.get("fatigued", [])),
        )
        return analysis

    def _parse_analysis(self, raw: str) -> dict:
        try:
            start = raw.find("{")
            end = raw.rfind("}") + 1
            if start >= 0:
                return json.loads(raw[start:end])
        except Exception:
            pass
        return {"winners": [], "fatigued": [], "patterns": [], "new_angles": [], "summary": raw[:300]}

    async def _get_ad_level_metrics(self, tenant_id: str, since: datetime) -> list[dict]:
        result = await self._s.execute(
            select(
                Ad.id,
                Ad.name,
                Ad.creative_type,
                Campaign.name.label("campaign_name"),
                func.avg(AdMetric.ctr).label("avg_ctr"),
                func.avg(AdMetric.cpm).label("avg_cpm"),
                func.avg(AdMetric.cpa).label("avg_cpa"),
                func.avg(AdMetric.roas).label("avg_roas"),
                func.avg(AdMetric.frequency).label("avg_frequency"),
                func.sum(AdMetric.spend).label("total_spend"),
                func.sum(AdMetric.impressions).label("total_impressions"),
                func.sum(AdMetric.clicks).label("total_clicks"),
                func.sum(AdMetric.conversions).label("total_conversions"),
            )
            .join(AdSet, Ad.adset_id == AdSet.id)
            .join(Campaign, AdSet.campaign_id == Campaign.id)
            .join(MetaAccount, Campaign.meta_account_id == MetaAccount.id)
            .join(AdMetric, Ad.id == AdMetric.ad_id)
            .where(
                and_(
                    MetaAccount.tenant_id == tenant_id,
                    AdMetric.date >= since,
                )
            )
            .group_by(Ad.id, Ad.name, Ad.creative_type, Campaign.name)
            .having(func.sum(AdMetric.spend) > 0)
            .order_by(func.avg(AdMetric.roas).desc())
        )
        return [
            {
                "ad_id": str(r.id),
                "ad_name": r.name,
                "creative_type": r.creative_type,
                "campaign_name": r.campaign_name,
                "avg_ctr": round(float(r.avg_ctr or 0), 3),
                "avg_cpm": round(float(r.avg_cpm or 0), 2),
                "avg_cpa": round(float(r.avg_cpa or 0), 2),
                "avg_roas": round(float(r.avg_roas or 0), 2),
                "avg_frequency": round(float(r.avg_frequency or 0), 2),
                "total_spend": round(float(r.total_spend or 0), 2),
                "total_clicks": int(r.total_clicks or 0),
                "total_conversions": int(r.total_conversions or 0),
                "ctr_status": "good" if float(r.avg_ctr or 0) >= 2.0 else "low",
                "fatigue_risk": float(r.avg_frequency or 0) > 3.0,
            }
            for r in result.all()
        ]
