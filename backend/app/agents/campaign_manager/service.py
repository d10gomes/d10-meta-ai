"""
Campaign Manager Agent — Especialista em gestão de ciclo de vida de campanhas Meta Ads.

Monitora todos os anúncios ativos, pausa losers, identifica winners para duplicação,
detecta saturação de público e gerencia o ciclo de vida completo das campanhas.
Roda a cada 3 horas.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import logger
from app.db.models import Campaign, AdSet, Ad, AdMetric, MetaAccount
from app.infrastructure.meta_api.client import MetaAdsClient


# Limites para ação imediata
PAUSE_CTR_THRESHOLD = 0.35       # CTR < 0.35% + muitas impressões → pausar
PAUSE_CTR_MIN_IMPS = 3000        # Mínimo de impressões para agir no CTR
PAUSE_NO_CONV_SPEND = 80         # Gasto sem conversão que justifica pausa
PAUSE_FREQUENCY = 5.0            # Frequência > 5 → anúncio saturado
WINNER_ROAS = 3.5                # ROAS > 3.5x → candidato a duplicar/escalar
WINNER_CTR = 2.5                 # CTR > 2.5% → criativo vencedor
WINNER_MIN_SPEND = 30            # Mínimo de gasto para considerar winner


class CampaignManagerService:
    def __init__(self, session: AsyncSession):
        self._s = session

    async def run(self, tenant_id: str) -> dict[str, Any]:
        since = datetime.utcnow() - timedelta(days=7)
        accounts = await self._get_accounts(tenant_id)

        paused_ads = []
        winners = []
        saturated = []
        recommendations = []

        for account in accounts:
            client = MetaAdsClient(account.access_token, account.ad_account_id)
            try:
                ad_data = await self._get_ads_with_metrics(str(account.id), since)

                for ad in ad_data:
                    # --- Pausar anúncio: CTR muito baixo ---
                    if (
                        ad["status"] == "ACTIVE"
                        and ad["ctr"] < PAUSE_CTR_THRESHOLD
                        and ad["impressions"] > PAUSE_CTR_MIN_IMPS
                        and ad["spend"] > 10
                    ):
                        try:
                            await client.update_ad_status(ad["meta_id"], "PAUSED")
                            paused_ads.append({
                                "ad": ad["name"],
                                "campaign": ad["campaign"],
                                "reason": f"CTR {ad['ctr']:.2f}% com {ad['impressions']:,} impressões — criativo não engaja",
                                "spend_saved": f"R${ad['spend']:.0f} redirecionados",
                            })
                            await self._log_action(tenant_id, "PAUSE_AD", ad["meta_id"], f"CTR {ad['ctr']:.2f}%")
                        except Exception as e:
                            logger.warning("campaign_manager.pause_failed", ad=ad["name"], error=str(e))

                    # --- Pausar anúncio: sem conversão com gasto alto ---
                    elif (
                        ad["status"] == "ACTIVE"
                        and ad["conversions"] == 0
                        and ad["spend"] > PAUSE_NO_CONV_SPEND
                    ):
                        try:
                            await client.update_ad_status(ad["meta_id"], "PAUSED")
                            paused_ads.append({
                                "ad": ad["name"],
                                "campaign": ad["campaign"],
                                "reason": f"R${ad['spend']:.0f} gastos sem uma única conversão",
                                "spend_saved": f"R${ad['spend']:.0f} de desperdício eliminado",
                            })
                            await self._log_action(tenant_id, "PAUSE_AD", ad["meta_id"], "0 conversões")
                        except Exception as e:
                            logger.warning("campaign_manager.pause_failed", ad=ad["name"], error=str(e))

                    # --- Detectar saturação de público ---
                    elif ad["status"] == "ACTIVE" and ad["frequency"] > PAUSE_FREQUENCY:
                        saturated.append({
                            "ad": ad["name"],
                            "campaign": ad["campaign"],
                            "frequency": ad["frequency"],
                            "action": "Trocar criativo ou expandir público-alvo",
                        })
                        recommendations.append(
                            f"🔄 '{ad['name']}' com frequência {ad['frequency']:.1f}x — público esgotado, renovar criativo"
                        )

                    # --- Identificar winners ---
                    if (
                        ad["roas"] >= WINNER_ROAS
                        and ad["spend"] >= WINNER_MIN_SPEND
                    ):
                        grade = "S" if ad["roas"] >= 5 and ad["ctr"] >= 3 else "A"
                        winners.append({
                            "ad": ad["name"],
                            "campaign": ad["campaign"],
                            "roas": ad["roas"],
                            "ctr": ad["ctr"],
                            "spend": ad["spend"],
                            "conversions": ad["conversions"],
                            "grade": grade,
                            "action": "🚀 Duplicar e escalar orçamento",
                        })

            except Exception as exc:
                logger.error("campaign_manager.account_error", account=account.name, error=str(exc))
            finally:
                await client.close()

        # Recomendações automáticas
        if winners:
            top = winners[0]
            recommendations.insert(0, f"🏆 Top winner: '{top['ad']}' ROAS {top['roas']:.1f}x — duplicar esta campanha agora")

        if len(paused_ads) > 0:
            recommendations.append(f"✅ {len(paused_ads)} anúncio(s) pausado(s) — orçamento redirecionado aos winners")

        summary = self._build_summary(paused_ads, winners, saturated)
        details = {
            "paused_ads": paused_ads,
            "winners": winners,
            "saturated": saturated,
            "recommendations": recommendations,
            "stats": {
                "paused_count": len(paused_ads),
                "winners_count": len(winners),
                "saturated_count": len(saturated),
            },
        }
        await self._save_insight(tenant_id, summary, details, len(paused_ads))
        logger.info("campaign_manager.done", tenant_id=tenant_id, paused=len(paused_ads), winners=len(winners))
        return details

    # ------------------------------------------------------------------

    async def _get_ads_with_metrics(self, account_id: str, since: datetime) -> list[dict]:
        r = await self._s.execute(
            select(
                Ad.meta_ad_id,
                Ad.name,
                Ad.status,
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
            )
            .join(AdSet, Ad.adset_id == AdSet.id)
            .join(Campaign, AdSet.campaign_id == Campaign.id)
            .join(AdMetric, Ad.id == AdMetric.ad_id)
            .where(
                Campaign.meta_account_id == account_id,
                AdMetric.date >= since,
            )
            .group_by(Ad.id, Ad.meta_ad_id, Ad.name, Ad.status, Campaign.name)
        )
        return [
            {
                "meta_id": row.meta_ad_id,
                "name": row.name or "Sem nome",
                "status": row.status or "UNKNOWN",
                "campaign": row.campaign or "Sem campanha",
                "spend": float(row.spend or 0),
                "impressions": int(row.impressions or 0),
                "clicks": int(row.clicks or 0),
                "conversions": int(row.conversions or 0),
                "ctr": float(row.ctr or 0),
                "cpc": float(row.cpc or 0),
                "cpa": float(row.cpa or 0),
                "roas": float(row.roas or 0),
                "frequency": float(row.frequency or 0),
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
            parts.append(f"{len(saturated)} anúncio(s) com público saturado")
        if not parts:
            return "Gestão de campanhas: nenhuma ação necessária — todos os anúncios dentro dos parâmetros."
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
        import json
        from sqlalchemy import text, bindparam, String
        title = f"Gestão de Campanhas — {datetime.now().strftime('%d/%m/%Y %H:%M')}"
        details_json = json.dumps(details, ensure_ascii=False, default=str)
        await self._s.execute(
            text(
                "INSERT INTO agent_insights (tenant_id, agent_name, title, summary, details, actions_taken)"
                " VALUES (:tid, 'campaign_manager', :title, :summary, to_jsonb(:details), :cnt)"
            ).bindparams(bindparam("details", type_=String())),
            {
                "tid": tenant_id,
                "title": title,
                "summary": summary,
                "details": details_json,
                "cnt": actions_taken,
            },
        )
        await self._s.flush()
