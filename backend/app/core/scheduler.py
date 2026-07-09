"""Autonomous agent scheduler — APScheduler AsyncIO."""
from datetime import datetime, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from app.core.logging import logger

scheduler = AsyncIOScheduler(timezone="America/Sao_Paulo")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _record_run(agent_name: str, trigger: str = "scheduled"):
    """Create an AgentRun record and return its id."""
    from app.db.session import AsyncSessionLocal
    from app.db.models import AgentRun
    async with AsyncSessionLocal() as s:
        run = AgentRun(agent_name=agent_name, trigger=trigger, status="running")
        s.add(run)
        await s.commit()
        await s.refresh(run)
        return run.id


async def _finish_run(run_id: str, started_at: datetime, items: int = 0, error: str | None = None):
    from app.db.session import AsyncSessionLocal
    from app.db.models import AgentRun
    from sqlalchemy import select
    finished = datetime.utcnow()
    duration = (finished - started_at).total_seconds()
    async with AsyncSessionLocal() as s:
        result = await s.execute(select(AgentRun).where(AgentRun.id == run_id))
        run = result.scalar_one_or_none()
        if run:
            run.status = "failed" if error else "success"
            run.finished_at = finished
            run.duration_seconds = duration
            run.items_processed = items
            run.error = error
            await s.commit()


# ---------------------------------------------------------------------------
# Agent jobs
# ---------------------------------------------------------------------------

async def job_scanner():
    """Syncs campaigns/adsets/ads/metrics from Meta API for all active accounts."""
    agent = "scanner"
    started = datetime.utcnow()
    run_id = await _record_run(agent)
    logger.info(f"{agent}.scheduled_start")
    try:
        from app.agents.scanner.service import ScannerService
        from app.db.session import AsyncSessionLocal
        from app.infrastructure.repositories.meta_account_repository import MetaAccountRepository

        async with AsyncSessionLocal() as s:
            accounts = await MetaAccountRepository(s).get_all_active()
            account_ids = [str(a.id) for a in accounts]

        ok = 0
        for account_id in account_ids:
            async with AsyncSessionLocal() as s:
                try:
                    await ScannerService(s).scan_account(account_id)
                    await s.commit()
                    ok += 1
                except Exception as exc:
                    logger.error(f"{agent}.account_failed", account_id=account_id, error=str(exc))
                    await s.rollback()

        await _finish_run(run_id, started, items=ok)
        logger.info(f"{agent}.scheduled_done", accounts=ok)
    except Exception as exc:
        await _finish_run(run_id, started, error=str(exc))
        logger.error(f"{agent}.scheduled_error", error=str(exc))


async def job_doctor_and_decision():
    """Diagnoses all active tenants and creates actions from diagnoses."""
    agent = "doctor"
    started = datetime.utcnow()
    run_id = await _record_run(agent)
    logger.info(f"{agent}.scheduled_start")
    try:
        from app.db.session import AsyncSessionLocal
        from app.infrastructure.repositories.meta_account_repository import MetaAccountRepository
        from app.agents.doctor.service import DoctorService
        from app.agents.decision.service import DecisionService
        from sqlalchemy import select, text

        # Get distinct tenant IDs that have active accounts
        async with AsyncSessionLocal() as s:
            result = await s.execute(
                text("SELECT DISTINCT tenant_id FROM meta_accounts WHERE is_active = TRUE")
            )
            tenant_ids = [str(row[0]) for row in result.fetchall()]

        total_diagnoses = 0
        for tenant_id in tenant_ids:
            async with AsyncSessionLocal() as s:
                try:
                    diagnoses = await DoctorService(s).run(tenant_id)
                    await DecisionService(s).decide(diagnoses)
                    await s.commit()
                    total_diagnoses += len(diagnoses)
                except Exception as exc:
                    logger.error(f"{agent}.tenant_failed", tenant_id=tenant_id, error=str(exc))
                    await s.rollback()

        await _finish_run(run_id, started, items=total_diagnoses)
        logger.info(f"{agent}.scheduled_done", diagnoses=total_diagnoses)
    except Exception as exc:
        await _finish_run(run_id, started, error=str(exc))
        logger.error(f"{agent}.scheduled_error", error=str(exc))


async def job_executor():
    """Executes pending agent actions for all tenants."""
    agent = "executor"
    started = datetime.utcnow()
    run_id = await _record_run(agent)
    logger.info(f"{agent}.scheduled_start")
    try:
        from app.db.session import AsyncSessionLocal
        from app.agents.executor.service import ExecutorService
        from sqlalchemy import text

        async with AsyncSessionLocal() as s:
            result = await s.execute(
                text("SELECT DISTINCT tenant_id FROM agent_actions WHERE status = 'pending'")
            )
            tenant_ids = [str(row[0]) for row in result.fetchall()]

        total = 0
        for tenant_id in tenant_ids:
            async with AsyncSessionLocal() as s:
                try:
                    svc = ExecutorService(s)
                    await svc.execute_pending(tenant_id)
                    await s.commit()
                    total += 1
                except Exception as exc:
                    logger.error(f"{agent}.tenant_failed", tenant_id=tenant_id, error=str(exc))
                    await s.rollback()

        await _finish_run(run_id, started, items=total)
        logger.info(f"{agent}.scheduled_done")
    except Exception as exc:
        await _finish_run(run_id, started, error=str(exc))
        logger.error(f"{agent}.scheduled_error", error=str(exc))


async def job_whatsapp_daily():
    """Sends daily WhatsApp reports to all tenants."""
    agent = "whatsapp"
    started = datetime.utcnow()
    run_id = await _record_run(agent)
    logger.info(f"{agent}.scheduled_start")
    try:
        from app.db.session import AsyncSessionLocal
        from app.agents.whatsapp.service import WhatsAppAgent
        from sqlalchemy import text

        async with AsyncSessionLocal() as s:
            result = await s.execute(text("SELECT id FROM tenants WHERE is_active = TRUE"))
            tenant_ids = [str(row[0]) for row in result.fetchall()]

        sent = 0
        for tenant_id in tenant_ids:
            async with AsyncSessionLocal() as s:
                try:
                    await WhatsAppAgent(s).send_report(tenant_id, "daily")
                    await s.commit()
                    sent += 1
                except Exception as exc:
                    logger.error(f"{agent}.tenant_failed", tenant_id=tenant_id, error=str(exc))
                    await s.rollback()

        await _finish_run(run_id, started, items=sent)
        logger.info(f"{agent}.scheduled_done", sent=sent)
    except Exception as exc:
        await _finish_run(run_id, started, error=str(exc))
        logger.error(f"{agent}.scheduled_error", error=str(exc))


async def job_analyst():
    """Análise completa de performance para todos os tenants."""
    agent = "analyst"
    started = datetime.utcnow()
    run_id = await _record_run(agent)
    logger.info(f"{agent}.scheduled_start")
    try:
        from app.db.session import AsyncSessionLocal
        from app.agents.analyst.service import AnalystService
        from sqlalchemy import text

        async with AsyncSessionLocal() as s:
            result = await s.execute(text("SELECT id FROM tenants WHERE is_active = TRUE"))
            tenant_ids = [str(row[0]) for row in result.fetchall()]

        ok = 0
        for tenant_id in tenant_ids:
            async with AsyncSessionLocal() as s:
                try:
                    await AnalystService(s).run(tenant_id)
                    await s.commit()
                    ok += 1
                except Exception as exc:
                    logger.error(f"{agent}.tenant_failed", tenant_id=tenant_id, error=str(exc))
                    await s.rollback()

        await _finish_run(run_id, started, items=ok)
        logger.info(f"{agent}.scheduled_done", tenants=ok)
    except Exception as exc:
        await _finish_run(run_id, started, error=str(exc))
        logger.error(f"{agent}.scheduled_error", error=str(exc))


async def job_budget_optimizer():
    """Otimiza orçamentos de campanhas com base em ROAS/CPA."""
    agent = "budget_optimizer"
    started = datetime.utcnow()
    run_id = await _record_run(agent)
    logger.info(f"{agent}.scheduled_start")
    try:
        from app.db.session import AsyncSessionLocal
        from app.agents.budget_optimizer.service import BudgetOptimizerService
        from sqlalchemy import text

        async with AsyncSessionLocal() as s:
            result = await s.execute(text("SELECT id FROM tenants WHERE is_active = TRUE"))
            tenant_ids = [str(row[0]) for row in result.fetchall()]

        total_actions = 0
        for tenant_id in tenant_ids:
            async with AsyncSessionLocal() as s:
                try:
                    result = await BudgetOptimizerService(s).run(tenant_id)
                    await s.commit()
                    total_actions += len(result.get("actions", []))
                except Exception as exc:
                    logger.error(f"{agent}.tenant_failed", tenant_id=tenant_id, error=str(exc))
                    await s.rollback()

        await _finish_run(run_id, started, items=total_actions)
        logger.info(f"{agent}.scheduled_done", actions=total_actions)
    except Exception as exc:
        await _finish_run(run_id, started, error=str(exc))
        logger.error(f"{agent}.scheduled_error", error=str(exc))


async def job_campaign_manager():
    """Gerencia ciclo de vida de campanhas — pausa losers, identifica winners."""
    agent = "campaign_manager"
    started = datetime.utcnow()
    run_id = await _record_run(agent)
    logger.info(f"{agent}.scheduled_start")
    try:
        from app.db.session import AsyncSessionLocal
        from app.agents.campaign_manager.service import CampaignManagerService
        from sqlalchemy import text

        async with AsyncSessionLocal() as s:
            result = await s.execute(text("SELECT id FROM tenants WHERE is_active = TRUE"))
            tenant_ids = [str(row[0]) for row in result.fetchall()]

        total_actions = 0
        for tenant_id in tenant_ids:
            async with AsyncSessionLocal() as s:
                try:
                    result = await CampaignManagerService(s).run(tenant_id)
                    await s.commit()
                    total_actions += result.get("stats", {}).get("paused_count", 0)
                except Exception as exc:
                    logger.error(f"{agent}.tenant_failed", tenant_id=tenant_id, error=str(exc))
                    await s.rollback()

        await _finish_run(run_id, started, items=total_actions)
        logger.info(f"{agent}.scheduled_done", actions=total_actions)
    except Exception as exc:
        await _finish_run(run_id, started, error=str(exc))
        logger.error(f"{agent}.scheduled_error", error=str(exc))


# ---------------------------------------------------------------------------
# Register all jobs
# ---------------------------------------------------------------------------

def setup_scheduler():
    # Scanner: a cada 6 horas (00h, 06h, 12h, 18h)
    scheduler.add_job(
        job_scanner,
        CronTrigger(hour="0,6,12,18", minute=0),
        id="scanner",
        name="Scanner Agent — Sincronizar Meta Ads",
        replace_existing=True,
        misfire_grace_time=300,
    )

    # Doctor + Decision: 30 min depois do scanner
    scheduler.add_job(
        job_doctor_and_decision,
        CronTrigger(hour="0,6,12,18", minute=30),
        id="doctor",
        name="Doctor Agent — Diagnosticar e Decidir",
        replace_existing=True,
        misfire_grace_time=300,
    )

    # Executor: a cada hora (executa ações pendentes)
    scheduler.add_job(
        job_executor,
        CronTrigger(minute=0),
        id="executor",
        name="Executor Agent — Executar Ações",
        replace_existing=True,
        misfire_grace_time=120,
    )

    # WhatsApp: todo dia às 08h00
    scheduler.add_job(
        job_whatsapp_daily,
        CronTrigger(hour=8, minute=0),
        id="whatsapp",
        name="WhatsApp Agent — Relatório Diário",
        replace_existing=True,
        misfire_grace_time=600,
    )

    # Analyst: todo dia às 07h00 (antes do expediente)
    scheduler.add_job(
        job_analyst,
        CronTrigger(hour=7, minute=0),
        id="analyst",
        name="Analyst Agent — Análise de Performance",
        replace_existing=True,
        misfire_grace_time=600,
    )

    # Budget Optimizer: a cada 6 horas (1h depois do scanner)
    scheduler.add_job(
        job_budget_optimizer,
        CronTrigger(hour="1,7,13,19", minute=0),
        id="budget_optimizer",
        name="Budget Optimizer — Otimizar Orçamentos",
        replace_existing=True,
        misfire_grace_time=300,
    )

    # Campaign Manager: a cada 3 horas
    scheduler.add_job(
        job_campaign_manager,
        CronTrigger(hour="3,6,9,12,15,18,21,0", minute=30),
        id="campaign_manager",
        name="Campaign Manager — Gerenciar Campanhas",
        replace_existing=True,
        misfire_grace_time=300,
    )

    logger.info("scheduler.configured", jobs=len(scheduler.get_jobs()))
