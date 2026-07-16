"""
Campaign Manager Agent — Especialista em gestão de ciclo de vida de campanhas Meta Ads.

Monitora todos os anúncios ativos, usa Claude para raciocinar sobre contexto antes de agir,
detecta saturação de público e identifica winners para escalar.
Roda a cada 3 horas.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.base import AgentBase
from app.core.logging import logger
from app.db.models import Campaign, AdSet, Ad, AdMetric, MetaAccount
from app.infrastructure.meta_api.client import MetaAdsClient


CAMPAIGN_MANAGER_PROMPT = """Você é um gestor sênior de campanhas Meta Ads.

Sua função é avaliar cada anúncio individualmente e decidir a ação correta, considerando:
- O contexto completo (horário, dia da semana, histórico da conta)
- Padrões de sazonalidade (fins de semana costumam ter CPL maior mas conversões maiores)
- Estágio do anúncio (anúncio novo com 2 dias de dados não deve ser pausado por CTR ainda)
- Objetivo da campanha (purchase exige ROAS > 3x; signup exige CPL < R$2,50)

REGRAS DE OURO:
- Nunca pause um anúncio com menos de 48h rodando, mesmo com CTR ruim
- CTR < 0.35% com 3.000+ impressões e 5+ dias → PAUSAR
- R$80+ gastos sem nenhuma conversão em 5+ dias → PAUSAR
- Frequência > 5x → TROCAR CRIATIVO (não pausar a campanha)
- ROAS > 3.5x com R$30+ gastos → ESCALAR
- CTR > 2.5% → criativo vencedor, preservar

Para cada anúncio, decida:
- "PAUSAR": pausa imediata + motivo
- "ESCALAR": candidato a duplicar + motivo
- "MONITORAR": manter mas observar + o que olhar
- "TROCAR_CRIATIVO": não pausar mas renovar copy/imagem + sugestão

Responda em JSON:
{
  "decisions": [
    {
      "ad_id": "meta_id",
      "ad_name": "nome",
      "campaign": "nome da campanha",
      "action": "PAUSAR|ESCALAR|MONITORAR|TROCAR_CRIATIVO",
      "reason": "motivo específico com dados",
      "confidence": 0.0-1.0,
      "suggestion": "o que fazer a seguir (opcional)"
    }
  ],
  "summary": "resumo executivo do ciclo"
}"""


class CampaignManagerService(AgentBase):
    name = "campaign_manager"

    def __init__(self, session: AsyncSession, tenant_id: str = ""):
        super().__init__(session, tenant_id)
        self._s = session

    async def run(self, tenant_id: str) -> dict[str, Any]:
        self._tenant_id = tenant_id
        since = datetime.utcnow() - timedelta(days=7)
        accounts = await self._get_accounts(tenant_id)

        all_ads: list[dict] = []
        clients: dict[str, MetaAdsClient] = {}

        for account in accounts:
            try:
                ad_data = await self._get_ads_with_metrics(str(account.id), since)
                for ad in ad_data:
                    ad["_account_id"] = str(account.id)
                    ad["_access_token"] = account.access_token
                    ad["_ad_account_id"] = account.ad_account_id
                all_ads.extend(ad_data)
            except Exception as exc:
                logger.error("campaign_manager.account_error", account=account.name, error=str(exc))

        if not all_ads:
            return {"paused_ads": [], "winners": [], "saturated": [], "recommendations": [], "stats": {}}

        # Contexto de sazonalidade para o Claude
        now = datetime.now()
        weekday = now.strftime("%A")
        hour = now.hour
        season_ctx = (
            f"Hoje é {weekday}, {now.strftime('%d/%m/%Y')} às {hour:02d}h. "
            + ("Fim de semana — CPL tende a ser maior mas volume de cadastros também." if now.weekday() >= 5
               else "Dia útil — performance dentro do padrão.")
        )

        # Lições do Learning Agent
        from app.core import brain
        lessons = brain.get_lessons("what_works", limit=3) + brain.get_lessons("what_fails", limit=3)
        lessons_text = "\n".join(f"- {l.get('title')}: {l.get('lesson','')[:120]}" for l in lessons) or "Sem lições registradas ainda."

        # Claude raciocina sobre cada anúncio
        raw = await self.ai_think(
            system_prompt=CAMPAIGN_MANAGER_PROMPT,
            user_message=f"""CONTEXTO:
{season_ctx}

LIÇÕES APRENDIDAS:
{lessons_text}

ANÚNCIOS ATIVOS (últimos 7 dias):
{json.dumps(
    [{k: v for k, v in ad.items() if not k.startswith('_')} for ad in all_ads[:40]],
    ensure_ascii=False, indent=2
)}

Avalie cada anúncio e decida a ação. Responda em JSON.""",
            max_tokens=2000,
        )

        decisions = self._parse_decisions(raw)

        # Executar ações de PAUSAR (confiança >= 0.8)
        paused_ads = []
        winners = []
        saturated = []
        recommendations = []

        for dec in decisions.get("decisions", []):
            action = dec.get("action", "MONITORAR")
            confidence = dec.get("confidence", 0)
            ad_meta_id = dec.get("ad_id")

            # Encontrar o anúncio correspondente para pegar o client
            ad_obj = next((a for a in all_ads if a["meta_id"] == ad_meta_id), None)

            if action == "PAUSAR" and confidence >= 0.8 and ad_obj:
                try:
                    client = MetaAdsClient(ad_obj["_access_token"], ad_obj["_ad_account_id"])
                    await client.update_ad_status(ad_meta_id, "PAUSED")
                    paused_ads.append({
                        "ad": dec.get("ad_name"),
                        "campaign": dec.get("campaign"),
                        "reason": dec.get("reason"),
                        "confidence": confidence,
                    })
                    await self._log_action(tenant_id, "PAUSE_AD", ad_meta_id, dec.get("reason", ""))
                    await client.close()
                except Exception as e:
                    logger.warning("campaign_manager.pause_failed", ad=dec.get("ad_name"), error=str(e))

            elif action == "PAUSAR" and confidence < 0.8:
                # Confiança baixa → apenas recomenda, não executa
                recommendations.append(f"⚠️ Considerar pausar '{dec.get('ad_name')}': {dec.get('reason')} (confiança {confidence:.0%})")

            elif action == "ESCALAR":
                winners.append({
                    "ad": dec.get("ad_name"),
                    "campaign": dec.get("campaign"),
                    "reason": dec.get("reason"),
                    "suggestion": dec.get("suggestion", "Duplicar e aumentar orçamento +20%"),
                })
                recommendations.append(f"🚀 Escalar '{dec.get('ad_name')}': {dec.get('reason')}")

            elif action == "TROCAR_CRIATIVO":
                saturated.append({
                    "ad": dec.get("ad_name"),
                    "campaign": dec.get("campaign"),
                    "reason": dec.get("reason"),
                    "suggestion": dec.get("suggestion", ""),
                })
                recommendations.append(f"🔄 Renovar criativo '{dec.get('ad_name')}': {dec.get('suggestion', dec.get('reason'))}")

        summary = decisions.get("summary", self._build_summary(paused_ads, winners, saturated))

        details = {
            "paused_ads": paused_ads,
            "winners": winners,
            "saturated": saturated,
            "recommendations": recommendations,
            "stats": {
                "paused_count": len(paused_ads),
                "winners_count": len(winners),
                "saturated_count": len(saturated),
                "ads_evaluated": len(all_ads),
            },
        }

        await self._save_insight(tenant_id, summary, details, len(paused_ads))

        # Publica na KB para outros agentes lerem
        await self.publish_knowledge(
            topic="campaign_management",
            entry_type="insight",
            content=details,
            summary=summary,
            confidence=0.9,
            ttl_hours=6,
        )

        logger.info("campaign_manager.done", tenant_id=tenant_id, paused=len(paused_ads), winners=len(winners))
        return details

    def _parse_decisions(self, raw: str) -> dict:
        try:
            start = raw.find("{")
            end = raw.rfind("}") + 1
            if start >= 0:
                return json.loads(raw[start:end])
        except Exception:
            pass
        return {"decisions": [], "summary": "Erro ao processar decisões do Claude."}

    async def _get_ads_with_metrics(self, account_id: str, since: datetime) -> list[dict]:
        r = await self._s.execute(
            select(
                Ad.meta_ad_id,
                Ad.name,
                Ad.status,
                Ad.created_at,
                Campaign.name.label("campaign"),
                func.sum(AdMetric.spend).label("spend"),
                func.sum(AdMetric.impressions).label("impressions"),
                func.sum(AdMetric.clicks).label("clicks"),
                func.sum(AdMetric.conversions).label("conversions"),
                func.avg(AdMetric.ctr).label("ctr"),
                func.avg(AdMetric.cpc).label("cpc"),
                func.avg(AdMetric.cpa).label("cpa"),
                func.avg(AdMetric.roas).label("roas"),
                func.avg(AdMetric.frequency).label("frequency"),
                func.count(AdMetric.id).label("days_with_data"),
            )
            .join(AdSet, Ad.adset_id == AdSet.id)
            .join(Campaign, AdSet.campaign_id == Campaign.id)
            .join(AdMetric, Ad.id == AdMetric.ad_id)
            .where(
                Campaign.meta_account_id == account_id,
                AdMetric.date >= since,
            )
            .group_by(Ad.id, Ad.meta_ad_id, Ad.name, Ad.status, Ad.created_at, Campaign.name)
        )
        return [
            {
                "meta_id": row.meta_ad_id,
                "name": row.name or "Sem nome",
                "status": row.status or "UNKNOWN",
                "campaign": row.campaign or "Sem campanha",
                "days_running": row.days_with_data or 0,
                "spend": float(row.spend or 0),
                "impressions": int(row.impressions or 0),
                "clicks": int(row.clicks or 0),
                "conversions": int(row.conversions or 0),
                "ctr": round(float(row.ctr or 0), 2),
                "cpc": round(float(row.cpc or 0), 2),
                "cpa": round(float(row.cpa or 0), 2),
                "roas": round(float(row.roas or 0), 2),
                "frequency": round(float(row.frequency or 0), 2),
            }
            for row in r.all()
        ]

    async def _get_accounts(self, tenant_id: str):
        r = await self._s.execute(
            select(MetaAccount).where(
                MetaAccount.tenant_id == tenant_id,
                MetaAccount.is_active == True,
            )
        )
        return r.scalars().all()

    def _build_summary(self, paused: list, winners: list, saturated: list) -> str:
        parts = []
        if paused:
            parts.append(f"{len(paused)} anúncio(s) pausado(s) por baixa performance")
        if winners:
            parts.append(f"{len(winners)} winner(s) identificado(s) para escalar")
        if saturated:
            parts.append(f"{len(saturated)} anúncio(s) com criativo saturado")
        if not parts:
            return "Gestão de campanhas: todos os anúncios dentro dos parâmetros."
        return "Gestão automática: " + "; ".join(parts) + "."

    async def _log_action(self, tenant_id: str, action_type: str, entity_id: str, reason: str):
        from app.db.models import AgentAction as AgentActionModel
        action = AgentActionModel(
            tenant_id=tenant_id,
            action_type=action_type,
            entity_type="ad",
            entity_id=entity_id,
            payload={"reason": reason},
            status="executed",
        )
        self._s.add(action)

    async def _save_insight(self, tenant_id: str, summary: str, details: dict, actions_taken: int):
        from sqlalchemy import text, bindparam, String
        title = f"Gestão de Campanhas — {datetime.now().strftime('%d/%m/%Y %H:%M')}"
        details_json = json.dumps(details, ensure_ascii=False, default=str)
        await self._s.execute(
            text(
                "INSERT INTO agent_insights (tenant_id, agent_name, title, summary, details, actions_taken)"
                " VALUES (:tid, 'campaign_manager', :title, :summary, to_jsonb(:details), :cnt)"
            ).bindparams(bindparam("details", type_=String())),
            {"tid": tenant_id, "title": title, "summary": summary, "details": details_json, "cnt": actions_taken},
        )
        await self._s.flush()
