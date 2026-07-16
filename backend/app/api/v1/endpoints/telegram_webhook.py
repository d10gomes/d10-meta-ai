"""
Telegram Webhook — recebe callbacks de botões inline e processa aprovações/rejeições.
"""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import logger
from app.core.telegram import answer_callback, edit_message_after_decision
from app.db.models import AgentAction
from app.db.session import get_db

router = APIRouter(prefix="/telegram", tags=["telegram"])


@router.post("/webhook")
async def telegram_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    Endpoint chamado pelo Telegram quando o usuário clica em ✅ ou ❌.
    Não requer autenticação JWT — o Telegram não envia tokens.
    A segurança vem do token do bot embutido na URL do webhook.
    """
    try:
        body = await request.json()
    except Exception:
        return {"ok": True}

    callback_query = body.get("callback_query")
    if not callback_query:
        # Mensagem normal, não um callback de botão — ignora
        return {"ok": True}

    callback_id   = callback_query.get("id")
    data          = callback_query.get("data", "")
    message       = callback_query.get("message", {})
    chat_id       = str(message.get("chat", {}).get("id", ""))
    message_id    = message.get("message_id")

    # data é "approve:{uuid}" ou "reject:{uuid}"
    if ":" not in data:
        await answer_callback(callback_id, "❓ Comando inválido")
        return {"ok": True}

    command, action_id = data.split(":", 1)
    approved = command == "approve"

    # Busca a ação no banco
    result = await db.execute(
        select(AgentAction).where(AgentAction.id == action_id)
    )
    action = result.scalar_one_or_none()

    if not action:
        await answer_callback(callback_id, "❌ Ação não encontrada ou expirada")
        return {"ok": True}

    if action.status not in ("pending",):
        status_label = {
            "executed": "já executada",
            "approved": "já aprovada",
            "rejected": "já rejeitada",
            "failed": "falhou na execução",
        }.get(action.status, action.status)
        await answer_callback(callback_id, f"Esta ação já foi {status_label}.")
        return {"ok": True}

    # Aplica a decisão
    action.status = "approved" if approved else "rejected"
    action.approved_at = datetime.utcnow()
    await db.flush()
    await db.commit()

    # Feedback imediato no Telegram
    feedback = "✅ Aprovado! A ação será executada em breve." if approved else "❌ Rejeitado. Nenhuma mudança será feita."
    await answer_callback(callback_id, feedback)
    await edit_message_after_decision(chat_id, message_id, action.action_type, approved)

    logger.info(
        "telegram.webhook.decision",
        action_id=action_id,
        action_type=action.action_type,
        decision="approved" if approved else "rejected",
        chat_id=chat_id,
    )

    return {"ok": True}


@router.post("/set-webhook")
async def set_webhook(request: Request):
    """
    Registra a URL do webhook no Telegram.
    Chame uma vez após deploy para conectar o bot.
    Body: { "url": "https://seu-backend.railway.app/api/v1/telegram/webhook" }
    """
    import httpx
    from app.core.config import settings

    body = await request.json()
    webhook_url = body.get("url")
    if not webhook_url:
        return {"ok": False, "error": "url é obrigatória"}

    token = settings.TELEGRAM_BOT_TOKEN
    if not token:
        return {"ok": False, "error": "TELEGRAM_BOT_TOKEN não configurado"}

    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(
            f"https://api.telegram.org/bot{token}/setWebhook",
            json={"url": webhook_url, "allowed_updates": ["callback_query", "message"]},
        )
        data = resp.json()

    logger.info("telegram.webhook_set", url=webhook_url, result=data)
    return data
