"""
Audit Layer — decorator e helper para registro imutável de toda ação.
Toda mutação executada por qualquer agente deve passar aqui.
"""
from __future__ import annotations

import functools
import time
import uuid
from datetime import datetime
from typing import Any, Callable

from sqlalchemy import Column, DateTime, Float, Integer, String, Text, JSON
from sqlalchemy.dialects.postgresql import UUID

from app.core.logging import logger


# ---------------------------------------------------------------------------
# Runtime audit log (in-memory sink — persisted to DB by the caller's session)
# ---------------------------------------------------------------------------

async def record_action(
    session,
    *,
    agent_name: str,
    action_type: str,
    entity_type: str,
    entity_id: str | None,
    tenant_id: str,
    before_state: dict | None = None,
    after_state: dict | None = None,
    payload: dict | None = None,
    cost_usd: float = 0.0,
    duration_ms: int = 0,
    status: str = "success",
    error: str | None = None,
) -> str:
    """Persist one audit record. Returns audit_id."""
    from app.db.models import AuditLog

    audit_id = str(uuid.uuid4())
    record = AuditLog(
        id=audit_id,
        tenant_id=tenant_id,
        agent_name=agent_name,
        action_type=action_type,
        entity_type=entity_type,
        entity_id=entity_id or "",
        before_state=before_state or {},
        after_state=after_state or {},
        payload=payload or {},
        cost_usd=cost_usd,
        duration_ms=duration_ms,
        status=status,
        error=error,
        executed_at=datetime.utcnow(),
    )
    session.add(record)
    await session.flush()

    logger.info(
        "audit.recorded",
        audit_id=audit_id,
        agent=agent_name,
        action=action_type,
        entity=f"{entity_type}:{entity_id}",
        tenant=tenant_id,
        status=status,
    )
    return audit_id


def audited(action_type: str, entity_type: str = "unknown"):
    """
    Decorator for AgentBase methods that mutate state.
    Usage:
        @audited("BUDGET_CHANGE", "campaign")
        async def change_budget(self, campaign_id, new_budget):
            ...
    The decorated method receives `_audit_id` in kwargs if it wants it.
    """
    def decorator(fn: Callable):
        @functools.wraps(fn)
        async def wrapper(self, *args, **kwargs):
            start = time.monotonic()
            try:
                result = await fn(self, *args, **kwargs)
                elapsed_ms = int((time.monotonic() - start) * 1000)
                await record_action(
                    self._s,
                    agent_name=self.name,
                    action_type=action_type,
                    entity_type=entity_type,
                    entity_id=kwargs.get("entity_id") or (args[0] if args else None),
                    tenant_id=self._tenant_id,
                    payload={"args": str(args)[:500], "kwargs": str(kwargs)[:500]},
                    duration_ms=elapsed_ms,
                    status="success",
                )
                return result
            except Exception as exc:
                elapsed_ms = int((time.monotonic() - start) * 1000)
                await record_action(
                    self._s,
                    agent_name=self.name,
                    action_type=action_type,
                    entity_type=entity_type,
                    entity_id=kwargs.get("entity_id") or (args[0] if args else None),
                    tenant_id=self._tenant_id,
                    payload={"args": str(args)[:500]},
                    duration_ms=elapsed_ms,
                    status="failed",
                    error=str(exc)[:1000],
                )
                raise
        return wrapper
    return decorator
