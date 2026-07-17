"""
Telegram notification helpers.
Envia mensagens com inline buttons ✅/❌ para aprovação de ações de agentes.
"""
from __future__ import annotations

import httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import logger

ACTION_LABELS: dict[str, str] = {
    "PAUSAR_CAMPANHA":     "Pausar Campanha",
    "PAUSAR_ADSET":        "Pausar Conjunto",
    "PAUSAR_AD":           "Pausar Anúncio",
    "REDUZIR_BUDGET":      "Reduzir Orçamento",
    "AUMENTAR_BUDGET":     "Aumentar Orçamento",
    "AJUSTAR_BUDGET":      "Ajustar Orçamento",
    "SCALE_BUDGET_UP":     "Escalar Orçamento ↑",
    "SCALE_BUDGET_DOWN":   "Reduzir Orçamento ↓",
    "MONITORAR":           "Monitorar",
}


async def _get_chat_id(session: AsyncSession, tenant_id: str) -> str | None:
    result = await session.execute(
        text("SELECT telegram_chat_id FROM tenants WHERE id = :tid LIMIT 1"),
        {"tid": tenant_id},
    )
    row = result.fetchone()
    return row[0] if row else None


async def send_action_approval_request(
    session: AsyncSession,
    tenant_id: str,
    action_id: str,
    action_type: str,
    entity_name: str,
    reason: str,
    details: dict | None = None,
) -> bool:
    """
    Envia mensagem no Telegram com botões ✅ Aprovar / ❌ Rejeitar.
    Retorna True se enviou com sucesso.
    """
    token = settings.TELEGRAM_BOT_TOKEN
    if not token:
        logger.warning("telegram.no_token")
        return False

    chat_id = await _get_chat_id(session, tenant_id)
    if not chat_id:
        logger.warning("telegram.no_chat_id", tenant_id=tenant_id)
        return False

    label = ACTION_LABELS.get(action_type, action_type)

    lines = [
        "🤖 *D10 Meta AI — Aprovação Necessária*",
        "",
        f"*Ação:* {label}",
        f"*Alvo:* {entity_name}",
        f"*Motivo:* {reason}",
    ]

    if details:
        if "new_budget" in details:
            lines.append(f"*Novo orçamento:* R$ {details['new_budget']:.2f}/dia")
        if "old_budget" in details:
            lines.append(f"*Orçamento atual:* R$ {details['old_budget']:.2f}/dia")
        if "confidence" in details:
            lines.append(f"*Confiança:* {int(details['confidence'] * 100)}%")

    lines += ["", "Escolha uma opção:"]
    text_msg = "\n".join(lines)

    payload = {
        "chat_id": chat_id,
        "text": text_msg,
        "parse_mode": "Markdown",
        "reply_markup": {
            "inline_keyboard": [[
                {"text": "✅ Aprovar", "callback_data": f"approve:{action_id}"},
                {"text": "❌ Rejeitar", "callback_data": f"reject:{action_id}"},
            ]]
        },
    }

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json=payload,
            )
            if not resp.is_success:
                logger.warning("telegram.send_failed", status=resp.status_code, body=resp.text[:200])
                return False

        logger.info("telegram.approval_sent", action_id=action_id, action_type=action_type)
        return True
    except Exception as exc:
        logger.warning("telegram.send_error", error=str(exc))
        return False


async def send_alert(chat_id: str, message: str, parse_mode: str = "Markdown") -> bool:
    """Envia alerta simples de texto para o chat_id informado."""
    token = settings.TELEGRAM_BOT_TOKEN
    if not token or not chat_id:
        return False
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": chat_id, "text": message, "parse_mode": parse_mode},
            )
            if not resp.is_success:
                logger.warning("telegram.alert_failed", status=resp.status_code)
                return False
        return True
    except Exception as exc:
        logger.warning("telegram.alert_error", error=str(exc))
        return False


async def answer_callback(callback_query_id: str, text: str) -> None:
    """Confirma o clique no botão para o Telegram (remove o loading)."""
    token = settings.TELEGRAM_BOT_TOKEN
    if not token:
        return
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            await client.post(
                f"https://api.telegram.org/bot{token}/answerCallbackQuery",
                json={"callback_query_id": callback_query_id, "text": text},
            )
    except Exception:
        pass


async def edit_message_after_decision(
    chat_id: str,
    message_id: int,
    action_type: str,
    approved: bool,
) -> None:
    """Edita a mensagem original removendo os botões e mostrando a decisão."""
    token = settings.TELEGRAM_BOT_TOKEN
    if not token:
        return
    label = ACTION_LABELS.get(action_type, action_type)
    status = "✅ *Aprovado*" if approved else "❌ *Rejeitado*"
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            await client.post(
                f"https://api.telegram.org/bot{token}/editMessageText",
                json={
                    "chat_id": chat_id,
                    "message_id": message_id,
                    "text": f"🤖 D10 Meta AI\n\n*{label}*\n{status}",
                    "parse_mode": "Markdown",
                    "reply_markup": {"inline_keyboard": []},
                },
            )
    except Exception:
        pass
