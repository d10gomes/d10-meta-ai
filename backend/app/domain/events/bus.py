"""In-process event bus with Redis pub/sub bridge for cross-service events."""
import json
from typing import Callable, Dict, List

from app.core.logging import logger
from app.domain.events.base import DomainEvent
from app.infrastructure.cache.redis_client import redis_client

_handlers: Dict[str, List[Callable]] = {}


def subscribe(event_type: str, handler: Callable):
    _handlers.setdefault(event_type, []).append(handler)


async def publish(event: DomainEvent):
    logger.info("event.published", type=event.event_type, tenant=event.tenant_id)
    # In-process dispatch
    for handler in _handlers.get(event.event_type, []):
        try:
            await handler(event)
        except Exception as exc:
            logger.error("event.handler_error", handler=handler.__name__, error=str(exc))
    # Publish to Redis for cross-service consumption
    await redis_client.publish(
        f"d10:events:{event.event_type}",
        json.dumps({
            "event_id": event.event_id,
            "event_type": event.event_type,
            "tenant_id": event.tenant_id,
            "payload": event.payload,
            "occurred_at": event.occurred_at.isoformat(),
        }),
    )
