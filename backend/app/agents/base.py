"""Base class giving every agent persistent memory + shared knowledge base access."""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select, update, delete, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import logger
from app.db.models import AgentMemory, KnowledgeEntry


class AgentBase:
    """
    All agents inherit from this class.
    Provides:
      - remember()     → store a memory specific to this agent
      - recall()       → retrieve own memories by key or type
      - publish_knowledge()  → write to the shared knowledge base
      - read_knowledge()     → read what OTHER agents have published
      - ai_think()     → call Claude to reason over data
    """

    name: str = "base"

    def __init__(self, session: AsyncSession, tenant_id: str):
        self._s = session
        self._tenant_id = tenant_id

    # ------------------------------------------------------------------
    # MEMORY — private to this agent
    # ------------------------------------------------------------------

    async def remember(
        self,
        key: str,
        content: Any,
        memory_type: str = "observation",
        importance: int = 5,
        ttl_days: int | None = None,
    ) -> None:
        """Store or update a memory entry for this agent."""
        expires_at = datetime.utcnow() + timedelta(days=ttl_days) if ttl_days else None

        existing = await self._s.execute(
            select(AgentMemory).where(
                AgentMemory.agent_name == self.name,
                AgentMemory.tenant_id == self._tenant_id,
                AgentMemory.key == key,
            )
        )
        row = existing.scalar_one_or_none()

        if row:
            row.content = content
            row.memory_type = memory_type
            row.importance = importance
            row.expires_at = expires_at
            row.updated_at = datetime.utcnow()
        else:
            self._s.add(AgentMemory(
                agent_name=self.name,
                tenant_id=self._tenant_id,
                memory_type=memory_type,
                key=key,
                content=content,
                importance=importance,
                expires_at=expires_at,
            ))
        await self._s.flush()

    async def recall(
        self,
        key: str | None = None,
        memory_type: str | None = None,
        min_importance: int = 1,
        limit: int = 20,
    ) -> list[dict]:
        """Retrieve memories, most important first."""
        filters = [
            AgentMemory.agent_name == self.name,
            AgentMemory.tenant_id == self._tenant_id,
            AgentMemory.importance >= min_importance,
            or_(AgentMemory.expires_at.is_(None), AgentMemory.expires_at > datetime.utcnow()),
        ]
        if key:
            filters.append(AgentMemory.key == key)
        if memory_type:
            filters.append(AgentMemory.memory_type == memory_type)

        result = await self._s.execute(
            select(AgentMemory)
            .where(and_(*filters))
            .order_by(AgentMemory.importance.desc(), AgentMemory.updated_at.desc())
            .limit(limit)
        )
        rows = result.scalars().all()

        # Update recall count
        for row in rows:
            row.recall_count += 1
            row.last_recalled_at = datetime.utcnow()
        await self._s.flush()

        return [
            {
                "key": r.key,
                "type": r.memory_type,
                "content": r.content,
                "importance": r.importance,
                "created_at": r.created_at.isoformat(),
            }
            for r in rows
        ]

    async def forget(self, key: str) -> None:
        await self._s.execute(
            delete(AgentMemory).where(
                AgentMemory.agent_name == self.name,
                AgentMemory.tenant_id == self._tenant_id,
                AgentMemory.key == key,
            )
        )
        await self._s.flush()

    # ------------------------------------------------------------------
    # KNOWLEDGE BASE — shared between all agents
    # ------------------------------------------------------------------

    async def publish_knowledge(
        self,
        topic: str,
        entry_type: str,
        content: Any,
        summary: str,
        confidence: float = 0.8,
        ttl_hours: int | None = 48,
    ) -> None:
        """Write a piece of knowledge for other agents to consume."""
        expires_at = datetime.utcnow() + timedelta(hours=ttl_hours) if ttl_hours else None

        self._s.add(KnowledgeEntry(
            tenant_id=self._tenant_id,
            source_agent=self.name,
            entry_type=entry_type,
            topic=topic,
            content=content,
            summary=summary,
            confidence=confidence,
            consumed_by=[],
            expires_at=expires_at,
        ))
        await self._s.flush()
        logger.info(
            "knowledge.published",
            agent=self.name,
            topic=topic,
            type=entry_type,
        )

    async def read_knowledge(
        self,
        topic: str | None = None,
        entry_type: str | None = None,
        source_agent: str | None = None,
        exclude_own: bool = True,
        only_unread: bool = True,
        limit: int = 30,
    ) -> list[dict]:
        """Read knowledge published by other agents."""
        filters: list = [
            KnowledgeEntry.tenant_id == self._tenant_id,
            or_(KnowledgeEntry.expires_at.is_(None), KnowledgeEntry.expires_at > datetime.utcnow()),
        ]
        if topic:
            filters.append(KnowledgeEntry.topic.ilike(f"%{topic}%"))
        if entry_type:
            filters.append(KnowledgeEntry.entry_type == entry_type)
        if source_agent:
            filters.append(KnowledgeEntry.source_agent == source_agent)
        if exclude_own:
            filters.append(KnowledgeEntry.source_agent != self.name)

        result = await self._s.execute(
            select(KnowledgeEntry)
            .where(and_(*filters))
            .order_by(KnowledgeEntry.created_at.desc())
            .limit(limit)
        )
        rows = result.scalars().all()

        entries = []
        for row in rows:
            consumed = row.consumed_by or []
            if only_unread and self.name in consumed:
                continue
            # Mark as consumed
            if self.name not in consumed:
                consumed.append(self.name)
                row.consumed_by = consumed
            entries.append({
                "id": row.id,
                "source_agent": row.source_agent,
                "entry_type": row.entry_type,
                "topic": row.topic,
                "summary": row.summary,
                "content": row.content,
                "confidence": row.confidence,
                "created_at": row.created_at.isoformat(),
            })

        await self._s.flush()
        return entries

    # ------------------------------------------------------------------
    # AI REASONING — Claude integration
    # ------------------------------------------------------------------

    async def ai_think(
        self,
        system_prompt: str,
        user_message: str,
        max_tokens: int = 1024,
    ) -> str:
        """
        Call Claude to reason over data. Returns the text response.
        Falls back to a structured placeholder if API key is missing.
        """
        import os
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            logger.warning("ai_think.no_api_key", agent=self.name)
            return f"[AI indisponível — adicione ANTHROPIC_API_KEY] Análise regra-base: {user_message[:200]}"

        try:
            import anthropic
            client = anthropic.AsyncAnthropic(api_key=api_key)
            message = await client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=max_tokens,
                system=system_prompt,
                messages=[{"role": "user", "content": user_message}],
            )
            return message.content[0].text
        except Exception as exc:
            logger.error("ai_think.failed", agent=self.name, error=str(exc))
            return f"[Erro AI: {exc}]"

    # ------------------------------------------------------------------
    # HELPERS
    # ------------------------------------------------------------------

    def _fmt_brl(self, value: float) -> str:
        return f"R$ {value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

    def _fmt_pct(self, value: float) -> str:
        return f"{value:.2f}%"
