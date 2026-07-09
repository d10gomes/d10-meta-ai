"""APScheduler main — run with: python -m app.scheduler.main"""
import asyncio
import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from app.core.config import settings
from app.core.logging import configure_logging, logger
from app.db.session import AsyncSessionLocal
from app.agents.scanner.service import ScannerService
from app.agents.doctor.service import DoctorService
from app.agents.executor.service import ExecutorService
from app.agents.whatsapp.service import WhatsAppAgent
from app.infrastructure.repositories.meta_account_repository import MetaAccountRepository


scheduler = AsyncIOScheduler(timezone="America/Sao_Paulo")


async def job_scan_all():
    logger.info("scheduler.scan_all.start")
    async with AsyncSessionLocal() as session:
        svc = ScannerService(session)
        await svc.scan_all_active()


async def job_doctor_all():
    logger.info("scheduler.doctor_all.start")
    async with AsyncSessionLocal() as session:
        repo = MetaAccountRepository(session)
        accounts = await repo.get_all_active()
        tenant_ids = list({str(a.tenant_id) for a in accounts})
        for tenant_id in tenant_ids:
            try:
                async with AsyncSessionLocal() as s2:
                    svc = DoctorService(s2)
                    diagnoses = await svc.run(tenant_id)
                    from app.agents.decision.service import DecisionService
                    decision_svc = DecisionService(s2)
                    await decision_svc.decide(diagnoses)
            except Exception as exc:
                logger.error("scheduler.doctor_failed", tenant=tenant_id, error=str(exc))


async def job_execute_pending():
    logger.info("scheduler.execute_pending.start")
    async with AsyncSessionLocal() as session:
        repo = MetaAccountRepository(session)
        accounts = await repo.get_all_active()
        tenant_ids = list({str(a.tenant_id) for a in accounts})
        for tenant_id in tenant_ids:
            try:
                async with AsyncSessionLocal() as s2:
                    svc = ExecutorService(s2)
                    await svc.execute_pending(tenant_id)
            except Exception as exc:
                logger.error("scheduler.execute_failed", tenant=tenant_id, error=str(exc))


async def job_daily_report():
    logger.info("scheduler.daily_report.start")
    async with AsyncSessionLocal() as session:
        repo = MetaAccountRepository(session)
        accounts = await repo.get_all_active()
        tenant_ids = list({str(a.tenant_id) for a in accounts})
        for tenant_id in tenant_ids:
            try:
                async with AsyncSessionLocal() as s2:
                    agent = WhatsAppAgent(s2)
                    await agent.send_report(tenant_id, "daily")
            except Exception as exc:
                logger.error("scheduler.report_failed", tenant=tenant_id, error=str(exc))


def setup_jobs():
    scheduler.add_job(
        job_scan_all,
        trigger=IntervalTrigger(minutes=settings.SCANNER_INTERVAL_MINUTES),
        id="scan_all",
        replace_existing=True,
        max_instances=1,
    )
    scheduler.add_job(
        job_doctor_all,
        trigger=IntervalTrigger(minutes=settings.DOCTOR_INTERVAL_MINUTES),
        id="doctor_all",
        replace_existing=True,
        max_instances=1,
    )
    scheduler.add_job(
        job_execute_pending,
        trigger=IntervalTrigger(minutes=10),
        id="execute_pending",
        replace_existing=True,
        max_instances=1,
    )
    cron_parts = settings.REPORT_CRON.split()
    scheduler.add_job(
        job_daily_report,
        trigger=CronTrigger(
            minute=cron_parts[0], hour=cron_parts[1],
            day=cron_parts[2], month=cron_parts[3], day_of_week=cron_parts[4],
        ),
        id="daily_report",
        replace_existing=True,
        max_instances=1,
    )


async def main():
    configure_logging()
    setup_jobs()
    scheduler.start()
    logger.info("scheduler.started")
    try:
        await asyncio.Event().wait()
    except (KeyboardInterrupt, SystemExit):
        scheduler.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
