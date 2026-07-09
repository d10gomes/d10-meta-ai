"""RQ task definitions enqueued by scheduler and API endpoints."""
import asyncio
import redis
from rq import Queue

from app.core.config import settings

_conn = redis.from_url(settings.REDIS_URL)
high_q = Queue("high", connection=_conn)
default_q = Queue("default", connection=_conn)
low_q = Queue("low", connection=_conn)


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


# --- Scanner ---
def task_scan_account(account_id: str):
    from app.agents.scanner.service import ScannerService
    from app.db.session import AsyncSessionLocal

    async def _inner():
        async with AsyncSessionLocal() as session:
            svc = ScannerService(session)
            await svc.scan_account(account_id)

    _run(_inner())


# --- Doctor ---
def task_run_doctor(tenant_id: str):
    from app.agents.doctor.service import DoctorService
    from app.db.session import AsyncSessionLocal

    async def _inner():
        async with AsyncSessionLocal() as session:
            svc = DoctorService(session)
            await svc.run(tenant_id)

    _run(_inner())


# --- Executor ---
def task_execute_action(action_id: str):
    from app.agents.executor.service import ExecutorService
    from app.db.session import AsyncSessionLocal

    async def _inner():
        async with AsyncSessionLocal() as session:
            svc = ExecutorService(session)
            await svc.execute(action_id)

    _run(_inner())


# --- WhatsApp report ---
def task_send_whatsapp_report(tenant_id: str, report_type: str = "daily"):
    from app.agents.whatsapp.service import WhatsAppAgent
    from app.db.session import AsyncSessionLocal

    async def _inner():
        async with AsyncSessionLocal() as session:
            agent = WhatsAppAgent(session)
            await agent.send_report(tenant_id, report_type)

    _run(_inner())
