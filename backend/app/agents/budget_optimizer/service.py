"""
Budget Optimizer Agent — Especialista em otimização de orçamento Meta Ads.

Redistribui automaticamente orçamentos com base em ROAS, CPA e CTR.
Escala campanhas vencedoras, reduz em perdedoras, pausa queimadores.
Roda a cada 6 horas.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import logger
from app.db.models import Campaign, AdSet, Ad, AdMetric, MetaAccount
from app.infrastructure.meta_api.client import MetaAdsClient


# Regras de otimização
SCALE_UP_ROAS = 3.0        # ROAS >= 3x → aumentar orçamento
SCALE_DOWN_ROAS = 0.8      # ROAS <= 0.8x → reduzir orçamento
PAUSE_ROAS = 0.3           # ROAS <= 0.3x E gasto > R$80 → pausar campanha
PAUSE_NO_CONV_SPEND = 120  # Gasto > R$120 sem conversão → pausar
SCALE_UP_PCT = 0.25        # +25% no orçamento
SCALE_DOWN_PCT = 0.30      # -30% no orçamento
MIN_SPEND_TO_ACT = 20      # Mínimo de gasto (R$) para tomar decisão
MIN_DAILY_BUDGET = 500     # Mínimo de orçamento diário (centavos) = R$5
MAX_DAILY_BUDGET = 500000  # Máximo de orçamento diário (centavos) = R$5000


class BudgetOptimizerService:
    def __init__(self, session: AsyncSession):
        self._s = session

    async def run(self, tenant_id: str) -> dict[str, Any]:
        since = datetime.utcnow() - timedelta(days=3)  # 3 dias para ter dados suficientes
        accounts = await self._get_accounts(tenant_id)
        actions_taken = []

        for account in accounts:
            client = MetaAdsClient(account.access_token, account.ad_account_id)
            try:
                account_actions = await self._optimize_account(account, client, since, tenant_id)
                actions_taken.extend(account_actions)
            except Exception as exc:
                logger.error("budget_optimizer.account_error", account=account.name, error=str(exc))
            finally:
                await client.close()

        summary = self._build_summary(actions_taken)
        await self._save_insight(tenant_id, summary, actions_taken)
        logger.info("budget_optimizer.done", tenant_id=tenant_id, actions=len(actions_taken))
        return {"actions": actions_taken, "summary": summary}

    # ------------------------------------------------------------------

    async def _optimize_account(self, account, client: MetaAdsClient, since: datetime, tenant_id: str) -> list[dict]:
        actions = []

        campaigns_data = await self._get_campaign_metrics(str(account.id), since)

        for camp in campaigns_data:
            spend = camp["spend"]
            roas = camp["roas"]
            conversions = camp["conversions"]
            daily_budget = camp["daily_budget"]
            campaign_id = camp["meta_id"]
            name = camp["name"]

            if spend < MIN_SPEND_TO_ACT:
                continue

            # Pausar: zero conversões com muito gasto
            if conversions == 0 and spend > PAUSE_NO_CONV_SPEND:
                try:
                    await client.update_campaign_status(campaign_id, "PAUSED")
                    actions.append({
                        "type": "pause",
                        "campaign": name,
                        "reason": f"R${spend:.0f} gastos sem nenhuma conversão",
                        "before": "ACTIVE",
                        "after": "PAUSED",
                    })
                    await self._log_action(tenant_id, "PAUSE_CAMPAIGN", campaign_id, f"0 conversões, R${spend:.0f} gasto")
                except Exception as e:
                    logger.warning("budget_optimizer.pause_failed", campaign=name, error=str(e))

            # Pausar: ROAS crítico
            elif roas > 0 and roas < PAUSE_ROAS and spend > 80:
                try:
                    await client.update_campaign_status(campaign_id, "PAUSED")
                    actions.append({
                        "type": "pause",
                        "campaign": name,
                        "reason": f"ROAS {roas:.2f}x — prejuízo confirmado (gasto R${spend:.0f})",
                        "before": "ACTIVE",
                        "after": "PAUSED",
                    })
                    await self._log_action(tenant_id, "PAUSE_CAMPAIGN", campaign_id, f"ROAS {roas:.2f}x")
                except Exception as e:
                    logger.warning("budget_optimizer.pause_failed", campaign=name, error=str(e))

            # Escalar: ROAS excelente
            elif roas >= SCALE_UP_ROAS and daily_budget and daily_budget > 0:
                new_budget = int(daily_budget * (1 + SCALE_UP_PCT) * 100)
                new_budget = min(new_budget, MAX_DAILY_BUDGET)
                if new_budget > daily_budget * 100:
                    try:
                        await client.update_campaign_budget(campaign_id, new_budget)
                        actions.append({
                            "type": "scale_up",
                            "campaign": name,
                            "reason": f"ROAS {roas:.2f}x excelente — escalando orçamento",
                            "before": f"R${daily_budget:.2f}/dia",
                            "after": f"R${new_budget/100:.2f}/dia",
                        })
                        await self._log_action(tenant_id, "SCALE_BUDGET_UP", campaign_id, f"ROAS {roas:.2f}x, +{SCALE_UP_PCT*100:.0f}%")
                    except Exception as e:
                        logger.warning("budget_optimizer.scale_up_failed", campaign=name, error=str(e))

            # Reduzir: ROAS fraco
            elif 0 < roas < SCALE_DOWN_ROAS and daily_budget and daily_budget > 0:
                new_budget = int(daily_budget * (1 - SCALE_DOWN_PCT) * 100)
                new_budget = max(new_budget, MIN_DAILY_BUDGET)
                if new_budget < daily_budget * 100:
                    try:
                        await client.update_campaign_budget(campaign_id, new_budget)
                        actions.append({
                            "type": "scale_down",
                            "campaign": name,
                            "reason": f"ROAS {roas:.2f}x abaixo do aceitável — reduzindo orçamento",
                            "before": f"R${daily_budget:.2f}/dia",
                            "after": f"R${new_budget/100:.2f}/dia",
                        })
                        await self._log_action(tenant_id, "SCALE_BUDGET_DOWN", campaign_id, f"ROAS {roas:.2f}x, -{SCALE_DOWN_PCT*100:.0f}%")
                    except Exception as e:
                        logger.warning("budget_optimizer.scale_down_failed", campaign=name, error=str(e))

        return actions

    async def _get_campaign_metrics(self, account_id: str, since: datetime) -> list[dict]:
        r = await self._s.execute(
            select(
                Campaign.meta_campaign_id,
                Campaign.name,
                Campaign.daily_budget,
                Campaign.status,
                func.sum(AdMetric.spend).label("spend"),
                func.sum(AdMetric.conversions).label("conversions"),
                func.sum(AdMetric.revenue).label("revenue"),
                func.avg(AdMetric.roas).label("roas"),
            )
            .join(AdSet, Campaign.id == AdSet.campaign_id)
            .join(Ad, AdSet.id == Ad.adset_id)
            .join(AdMetric, Ad.id == AdMetric.ad_id)
            .where(
                Campaign.meta_account_id == account_id,
                Campaign.status == "ACTIVE",
                AdMetric.date >= since,
            )
            .group_by(Campaign.id, Campaign.meta_campaign_id, Campaign.name, Campaign.daily_budget, Campaign.status)
        )
        return [
            {
                "meta_id": row.meta_campaign_id,
                "name": row.name,
                "daily_budget": float(row.daily_budget) if row.daily_budget else None,
                "spend": float(row.spend or 0),
                "conversions": int(row.conversions or 0),
                "revenue": float(row.revenue or 0),
                "roas": float(row.roas or 0),
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

    def _build_summary(self, actions: list[dict]) -> str:
        if not actions:
            return "Nenhuma otimização necessária — todas as campanhas dentro dos parâmetros."
        paused = len([a for a in actions if a["type"] == "pause"])
        scaled_up = len([a for a in actions if a["type"] == "scale_up"])
        scaled_down = len([a for a in actions if a["type"] == "scale_down"])
        parts = []
        if paused: parts.append(f"{paused} campanha(s) pausada(s)")
        if scaled_up: parts.append(f"{scaled_up} campanha(s) escalada(s)")
        if scaled_down: parts.append(f"{scaled_down} campanha(s) com orçamento reduzido")
        return "Otimizações realizadas: " + ", ".join(parts) + "."

    async def _log_action(self, tenant_id: str, action_type: str, entity_id: str, reason: str):
        from app.db.models import AgentAction as AgentActionModel
        action = AgentActionModel(
            tenant_id=tenant_id,
            action_type=action_type,
            entity_type="campaign",
            entity_id=entity_id,
            payload={"reason": reason},
            status="executed",
        )
        self._s.add(action)

    async def _save_insight(self, tenant_id: str, summary: str, actions: list):
        import json
        from sqlalchemy import text, bindparam, String
        title = f"Otimização de Orçamento — {datetime.now().strftime('%d/%m/%Y %H:%M')}"
        details_json = json.dumps({"actions": actions}, ensure_ascii=False, default=str)
        await self._s.execute(
            text(
                "INSERT INTO agent_insights (tenant_id, agent_name, title, summary, details, actions_taken)"
                " VALUES (:tid, 'budget_optimizer', :title, :summary, to_jsonb(:details), :cnt)"
            ).bindparams(bindparam("details", type_=String())),
            {
                "tid": tenant_id,
                "title": title,
                "summary": summary,
                "details": details_json,
                "cnt": len(actions),
            },
        )
        await self._s.flush()
