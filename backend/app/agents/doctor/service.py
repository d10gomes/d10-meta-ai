"""
Doctor Agent — Papel: DIAGNÓSTICO PROFUNDO
- Especialista em detectar problemas específicos: fadiga de criativo,
  frequência alta, CPA fora de controle, targeting muito restrito
- Lê alertas do Analyst e dados brutos do Scanner
- Publica diagnósticos detalhados com causas raiz
- Lembra de diagnósticos anteriores para ver se problemas foram resolvidos
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.base import AgentBase
from app.core.logging import logger
from app.db.models import (
    Campaign, AdSet, Ad, AdMetric, MetaAccount, Diagnosis
)


class DoctorService(AgentBase):
    name = "doctor"

    SYSTEM_PROMPT = """Você é um médico de campanhas de Meta Ads — especialista em diagnósticos.
Sua função é identificar a CAUSA RAIZ dos problemas, não apenas os sintomas.

Diagnósticos que você faz:
- FADIGA DE CRIATIVO: frequência > 3.5 e CTR caindo semana a semana
- TARGETING SATURADO: alcance estagnado mas CPM subindo
- FUNIL QUEBRADO: cliques existem mas conversões não acontecem
- BUDGET DESPERDÍCIO: gasto alto, zero conversões por mais de 48h
- PROBLEMA DE LEILÃO: CPM muito acima da média do setor
- AUDIÊNCIA ESGOTADA: frequência alta + reach estagnado

Para cada diagnóstico:
- Identifique o problema exato
- Explique por que está acontecendo
- Dê 2-3 ações corretivas específicas

Responda em JSON:
{
  "diagnoses": [
    {
      "campaign_name": "nome",
      "campaign_id": "id",
      "issue_type": "tipo",
      "severity": "low|medium|high|critical",
      "root_cause": "causa raiz detalhada",
      "evidence": {"metrica": valor},
      "corrective_actions": ["ação 1", "ação 2"]
    }
  ],
  "health_score": 0-100,
  "summary": "resumo geral da saúde das campanhas"
}"""

    async def run(self, tenant_id: str) -> dict[str, Any]:
        self._tenant_id = tenant_id

        since_7d = datetime.utcnow() - timedelta(days=7)
        since_14d = datetime.utcnow() - timedelta(days=14)

        # 1. Ler alertas e insights já publicados
        alerts = await self.read_knowledge(entry_type="alert", only_unread=True, limit=20)
        raw_data = await self.read_knowledge(source_agent="scanner", only_unread=False, limit=5)

        # 2. Buscar métricas detalhadas por anúncio (frequência, CTR trend)
        detailed_metrics = await self._get_detailed_metrics(tenant_id, since_14d)

        # 3. Verificar diagnósticos anteriores que não foram resolvidos
        past_diagnoses = await self.recall(memory_type="observation", limit=20)
        unresolved = [d for d in past_diagnoses if not d["content"].get("resolved")]

        unresolved_text = ""
        if unresolved:
            unresolved_text = "PROBLEMAS ANTERIORES NÃO RESOLVIDOS:\n" + "\n".join([
                f"- {d['content'].get('issue_type')}: {d['content'].get('campaign_name')}"
                for d in unresolved[:5]
            ])

        # 4. Claude faz diagnóstico profundo
        raw_response = await self.ai_think(
            system_prompt=self.SYSTEM_PROMPT,
            user_message=f"""Faça um diagnóstico profundo das campanhas:

MÉTRICAS DETALHADAS (últimos 14 dias):
{json.dumps(detailed_metrics, ensure_ascii=False, indent=2)}

ALERTAS DO SISTEMA:
{json.dumps([a["summary"] for a in alerts], ensure_ascii=False)}

{unresolved_text}

Identifique causas raiz e prescreva ações corretivas em JSON.""",
            max_tokens=2000,
        )

        diagnosis_data = self._parse_diagnosis(raw_response)

        # 5. Salvar cada diagnóstico
        for diag in diagnosis_data.get("diagnoses", []):
            # Memória do doctor
            await self.remember(
                key=f"diag_{diag.get('campaign_id', 'unknown')}_{diag.get('issue_type', 'unknown')}",
                content={**diag, "resolved": False},
                memory_type="observation",
                importance=8 if diag.get("severity") in ("high", "critical") else 5,
                ttl_days=21,
            )

            # Diagnose no banco para o frontend
            db_diag = Diagnosis(
                tenant_id=tenant_id,
                entity_type="campaign",
                entity_id=diag.get("campaign_id"),
                issue_type=diag.get("issue_type", "UNKNOWN"),
                severity=diag.get("severity", "medium"),
                details=diag,
            )
            self._s.add(db_diag)

        await self._s.flush()

        # 6. Publicar diagnósticos na Knowledge Base
        await self.publish_knowledge(
            topic="campaign_health",
            entry_type="insight",
            content=diagnosis_data,
            summary=diagnosis_data.get("summary", "Diagnóstico concluído"),
            confidence=0.85,
            ttl_hours=24,
        )

        logger.info(
            "doctor.done",
            tenant_id=tenant_id,
            diagnoses=len(diagnosis_data.get("diagnoses", [])),
            health_score=diagnosis_data.get("health_score"),
        )
        return diagnosis_data

    def _parse_diagnosis(self, raw: str) -> dict:
        try:
            start = raw.find("{")
            end = raw.rfind("}") + 1
            if start >= 0:
                return json.loads(raw[start:end])
        except Exception:
            pass
        return {"diagnoses": [], "health_score": 50, "summary": raw[:300]}

    async def _get_detailed_metrics(self, tenant_id: str, since: datetime) -> list[dict]:
        result = await self._s.execute(
            select(
                Campaign.id,
                Campaign.name,
                func.avg(AdMetric.frequency).label("avg_frequency"),
                func.avg(AdMetric.ctr).label("avg_ctr"),
                func.avg(AdMetric.cpm).label("avg_cpm"),
                func.avg(AdMetric.cpa).label("avg_cpa"),
                func.sum(AdMetric.spend).label("total_spend"),
                func.sum(AdMetric.conversions).label("total_conversions"),
                func.sum(AdMetric.impressions).label("total_impressions"),
                func.avg(AdMetric.roas).label("avg_roas"),
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
            .group_by(Campaign.id, Campaign.name)
        )
        return [
            {
                "campaign_id": str(r.id),
                "campaign_name": r.name,
                "avg_frequency": round(float(r.avg_frequency or 0), 2),
                "avg_ctr": round(float(r.avg_ctr or 0), 3),
                "avg_cpm": round(float(r.avg_cpm or 0), 2),
                "avg_cpa": round(float(r.avg_cpa or 0), 2),
                "total_spend": round(float(r.total_spend or 0), 2),
                "total_conversions": int(r.total_conversions or 0),
                "avg_roas": round(float(r.avg_roas or 0), 2),
                "ctr_ok": float(r.avg_ctr or 0) >= 1.0,
                "frequency_ok": float(r.avg_frequency or 0) <= 3.5,
                "converting": int(r.total_conversions or 0) > 0,
            }
            for r in result.all()
        ]
