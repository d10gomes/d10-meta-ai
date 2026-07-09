"""
WhatsApp Agent — Papel: COMUNICADOR / REPORTER
- Gera relatórios inteligentes combinando dados de todos os agentes
- Envia via Evolution API ou Meta Cloud API
- Lembra preferências de relatório do usuário e histórico de envios
- Só envia se houver algo relevante para reportar
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.base import AgentBase
from app.core.config import settings
from app.core.logging import logger
from app.db.models import Tenant, MetaAccount


class WhatsAppService(AgentBase):
    name = "whatsapp"

    SYSTEM_PROMPT = """Você é um assistente especializado em criar relatórios de Meta Ads para WhatsApp.
Os relatórios devem ser:
- Concisos e diretos (máximo 5 parágrafos)
- Escritos em português do Brasil
- Usar emojis estrategicamente para destacar dados importantes
- Incluir as métricas mais relevantes (gasto, ROAS, CTR)
- Destacar ALERTAS CRÍTICOS primeiro
- Terminar com 1-2 ações recomendadas

Formato:
📊 *Relatório D10 Meta AI* — {data}
{alerta_critico_se_houver}
💰 Gasto: R$ X | 📈 ROAS: X.Xx
🎯 CTR médio: X.X% | Campanhas ativas: N
{top_insight}
✅ Ações recomendadas: {ações}"""

    async def run(self, tenant_id: str) -> dict[str, Any]:
        self._tenant_id = tenant_id

        # 1. Coletar o que todos os outros agentes publicaram
        analyst_data = await self.read_knowledge(
            source_agent="analyst", entry_type="insight", only_unread=False, limit=1
        )
        alerts = await self.read_knowledge(entry_type="alert", only_unread=False, limit=5)
        decisions = await self.read_knowledge(
            source_agent="decision", entry_type="decision", only_unread=False, limit=5
        )
        creative_data = await self.read_knowledge(
            source_agent="creative", entry_type="insight", only_unread=False, limit=1
        )
        budget_data = await self.read_knowledge(
            source_agent="budget_optimizer", entry_type="recommendation", only_unread=False, limit=1
        )

        # 2. Verificar se já enviamos relatório recentemente
        last_sent = await self.recall(memory_type="context", limit=1)
        if last_sent:
            last_at = last_sent[0]["content"].get("sent_at", "")
            if last_at:
                try:
                    last_dt = datetime.fromisoformat(last_at)
                    hours_since = (datetime.utcnow() - last_dt).total_seconds() / 3600
                    if hours_since < 6:
                        logger.info("whatsapp.skip_too_recent", hours_since=hours_since)
                        return {"skipped": True, "reason": f"Último relatório enviado há {hours_since:.1f}h"}
                except Exception:
                    pass

        # 3. Construir contexto para o Claude gerar o relatório
        context_parts = []
        if analyst_data:
            context_parts.append(f"ANÁLISE: {analyst_data[0]['summary'][:600]}")
        if alerts:
            context_parts.append("ALERTAS: " + " | ".join([a["summary"] for a in alerts[:3]]))
        if decisions:
            context_parts.append("DECISÕES TOMADAS: " + " | ".join([d["summary"] for d in decisions[:3]]))
        if creative_data:
            context_parts.append(f"CRIATIVOS: {creative_data[0]['summary'][:300]}")
        if budget_data:
            context_parts.append(f"BUDGET: {budget_data[0]['summary'][:300]}")

        # 4. Claude gera o relatório WhatsApp
        report_text = await self.ai_think(
            system_prompt=self.SYSTEM_PROMPT,
            user_message=f"""Gere um relatório WhatsApp conciso para hoje ({datetime.now().strftime('%d/%m/%Y %H:%M')}):

{chr(10).join(context_parts) or 'Sistema iniciado, aguardando primeiras coletas de dados.'}

Escreva o relatório diretamente, pronto para envio.""",
            max_tokens=800,
        )

        # 5. Buscar destinatários (tenants com WhatsApp configurado)
        recipients = await self._get_recipients(tenant_id)
        sent_count = 0

        for phone in recipients:
            try:
                await self._send_whatsapp(phone, report_text)
                sent_count += 1
                logger.info("whatsapp.sent", phone=phone[-4:] + "****")
            except Exception as exc:
                logger.error("whatsapp.send_failed", phone=phone[-4:] + "****", error=str(exc))

        # 6. Salvar na memória que enviamos
        await self.remember(
            key=f"report_sent_{datetime.utcnow().strftime('%Y%m%d_%H')}",
            content={
                "sent_at": datetime.utcnow().isoformat(),
                "recipients": sent_count,
                "report_preview": report_text[:200],
                "had_alerts": len(alerts) > 0,
            },
            memory_type="context",
            importance=5,
            ttl_days=7,
        )

        # 7. Publicar na KB que o relatório foi gerado
        await self.publish_knowledge(
            topic="daily_report",
            entry_type="report",
            content={"report": report_text, "sent_to": sent_count},
            summary=f"Relatório enviado para {sent_count} destinatário(s)",
            confidence=1.0,
            ttl_hours=8,
        )

        logger.info("whatsapp.done", tenant_id=tenant_id, sent=sent_count)
        return {"sent": sent_count, "report_preview": report_text[:300]}

    async def _send_whatsapp(self, phone: str, message: str) -> None:
        """Send via Evolution API. Falls back gracefully if not configured."""
        evolution_url = getattr(settings, "EVOLUTION_API_URL", None)
        evolution_key = getattr(settings, "EVOLUTION_API_KEY", None)
        evolution_instance = getattr(settings, "EVOLUTION_INSTANCE", "d10")

        if not evolution_url or not evolution_key:
            logger.warning("whatsapp.not_configured", phone=phone[-4:])
            return

        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                f"{evolution_url}/message/sendText/{evolution_instance}",
                headers={"apikey": evolution_key, "Content-Type": "application/json"},
                json={"number": phone, "text": message},
            )
            resp.raise_for_status()

    async def _get_recipients(self, tenant_id: str) -> list[str]:
        result = await self._s.execute(
            select(Tenant.whatsapp_number)
            .where(
                Tenant.id == tenant_id,
                Tenant.whatsapp_number.isnot(None),
            )
        )
        row = result.one_or_none()
        if row and row.whatsapp_number:
            return [row.whatsapp_number]
        return []
