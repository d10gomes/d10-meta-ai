"""Autonomous agent scheduler — APScheduler AsyncIO.

Pipeline de execução (por tenant):
  00h,06h,12h,18h+00m → Scanner  (coleta dados do Meta)
  00h,06h,12h,18h+15m → Analyst  (analisa + publica na KB)
  00h,06h,12h,18h+25m → Doctor   (diagnóstico profundo)
  00h,06h,12h,18h+35m → Decision (decide ações)
  00h,06h,12h,18h+40m → Creative (avalia criativos)
  01h,07h,13h,19h+00m → BudgetOptimizer (redistribui budget)
  *h+50m              → Executor (executa ações pendentes)
  08h+00m             → WhatsApp (relatório diário)
"""
from datetime import datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from app.core.logging import logger

scheduler = AsyncIOScheduler(timezone="America/Sao_Paulo")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _get_tenant_ids() -> list[str]:
    from app.db.session import AsyncSessionLocal
    from sqlalchemy import text
    async with AsyncSessionLocal() as s:
        result = await s.execute(text("SELECT id FROM tenants WHERE is_active = TRUE"))
        return [str(row[0]) for row in result.fetchall()]


async def _record_run(agent_name: str, trigger: str = "scheduled") -> str:
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


async def _run_per_tenant(agent_cls, agent_name: str, method: str = "run"):
    """Generic runner: instantiates agent per tenant with its own session."""
    from app.db.session import AsyncSessionLocal
    started = datetime.utcnow()
    run_id = await _record_run(agent_name)
    tenant_ids = await _get_tenant_ids()
    ok = 0
    for tenant_id in tenant_ids:
        async with AsyncSessionLocal() as s:
            try:
                svc = agent_cls(s, tenant_id)
                await getattr(svc, method)(tenant_id)
                await s.commit()
                ok += 1
            except Exception as exc:
                logger.error(f"{agent_name}.tenant_failed", tenant_id=tenant_id, error=str(exc))
                await s.rollback()
    await _finish_run(run_id, started, items=ok)
    logger.info(f"{agent_name}.scheduled_done", tenants=ok)


# ---------------------------------------------------------------------------
# Individual job functions
# ---------------------------------------------------------------------------

async def job_scanner():
    logger.info("scanner.scheduled_start")
    from app.agents.scanner.service import ScannerService
    from app.db.session import AsyncSessionLocal
    from app.infrastructure.repositories.meta_account_repository import MetaAccountRepository

    started = datetime.utcnow()
    run_id = await _record_run("scanner")
    try:
        async with AsyncSessionLocal() as s:
            accounts = await MetaAccountRepository(s).get_all_active()
            account_data = [(str(a.id), str(a.tenant_id)) for a in accounts]

        ok = 0
        for account_id, tenant_id in account_data:
            async with AsyncSessionLocal() as s:
                try:
                    await ScannerService(s, tenant_id).scan_account(account_id)
                    await s.commit()
                    ok += 1
                except Exception as exc:
                    logger.error("scanner.account_failed", account_id=account_id, error=str(exc))
                    await s.rollback()

        await _finish_run(run_id, started, items=ok)
        logger.info("scanner.scheduled_done", accounts=ok)
    except Exception as exc:
        await _finish_run(run_id, started, error=str(exc))
        logger.error("scanner.scheduled_error", error=str(exc))


async def job_analyst():
    logger.info("analyst.scheduled_start")
    try:
        from app.agents.analyst.service import AnalystService
        await _run_per_tenant(AnalystService, "analyst")
    except Exception as exc:
        logger.error("analyst.scheduled_error", error=str(exc))


async def job_doctor():
    logger.info("doctor.scheduled_start")
    try:
        from app.agents.doctor.service import DoctorService
        await _run_per_tenant(DoctorService, "doctor")
    except Exception as exc:
        logger.error("doctor.scheduled_error", error=str(exc))


async def job_decision():
    logger.info("decision.scheduled_start")
    try:
        from app.agents.decision.service import DecisionService
        await _run_per_tenant(DecisionService, "decision")
    except Exception as exc:
        logger.error("decision.scheduled_error", error=str(exc))


async def job_creative():
    logger.info("creative.scheduled_start")
    try:
        from app.agents.creative.service import CreativeService
        await _run_per_tenant(CreativeService, "creative")
    except Exception as exc:
        logger.error("creative.scheduled_error", error=str(exc))


async def job_budget_optimizer():
    logger.info("budget_optimizer.scheduled_start")
    try:
        from app.agents.budget_optimizer.service import BudgetOptimizerService
        await _run_per_tenant(BudgetOptimizerService, "budget_optimizer")
    except Exception as exc:
        logger.error("budget_optimizer.scheduled_error", error=str(exc))


async def job_executor():
    logger.info("executor.scheduled_start")
    started = datetime.utcnow()
    run_id = await _record_run("executor")
    try:
        from app.db.session import AsyncSessionLocal
        from app.agents.executor.service import ExecutorService
        from sqlalchemy import text

        async with AsyncSessionLocal() as s:
            result = await s.execute(
                text("SELECT DISTINCT tenant_id FROM agent_actions WHERE status = 'pending'")
            )
            tenant_ids = [str(row[0]) for row in result.fetchall()]

        ok = 0
        for tenant_id in tenant_ids:
            async with AsyncSessionLocal() as s:
                try:
                    await ExecutorService(s).execute_pending(tenant_id)
                    await s.commit()
                    ok += 1
                except Exception as exc:
                    logger.error("executor.tenant_failed", tenant_id=tenant_id, error=str(exc))
                    await s.rollback()

        await _finish_run(run_id, started, items=ok)
        logger.info("executor.scheduled_done", tenants=ok)
    except Exception as exc:
        await _finish_run(run_id, started, error=str(exc))
        logger.error("executor.scheduled_error", error=str(exc))


async def job_whatsapp():
    logger.info("whatsapp.scheduled_start")
    try:
        from app.agents.whatsapp.service import WhatsAppService
        await _run_per_tenant(WhatsAppService, "whatsapp")
    except Exception as exc:
        logger.error("whatsapp.scheduled_error", error=str(exc))


async def job_learning():
    logger.info("learning.scheduled_start")
    try:
        from app.agents.learning.service import LearningService
        await _run_per_tenant(LearningService, "learning")
    except Exception as exc:
        logger.error("learning.scheduled_error", error=str(exc))


# ---------------------------------------------------------------------------
# Register all jobs
# ---------------------------------------------------------------------------

def setup_scheduler():
    # 1. Scanner — coleta dados brutos (00h, 06h, 12h, 18h)
    scheduler.add_job(
        job_scanner,
        CronTrigger(hour="0,6,12,18", minute=0),
        id="scanner",
        name="Scanner — Sincronizar Meta Ads",
        replace_existing=True,
        misfire_grace_time=300,
    )

    # 2. Analyst — analisa e publica na KB (15 min depois do scanner)
    scheduler.add_job(
        job_analyst,
        CronTrigger(hour="0,6,12,18", minute=15),
        id="analyst",
        name="Analyst — Análise de Performance",
        replace_existing=True,
        misfire_grace_time=300,
    )

    # 3. Doctor — diagnóstico profundo (25 min depois do scanner)
    scheduler.add_job(
        job_doctor,
        CronTrigger(hour="0,6,12,18", minute=25),
        id="doctor",
        name="Doctor — Diagnóstico de Campanhas",
        replace_existing=True,
        misfire_grace_time=300,
    )

    # 4. Decision — toma decisões baseadas em diagnósticos e análises
    scheduler.add_job(
        job_decision,
        CronTrigger(hour="0,6,12,18", minute=35),
        id="decision",
        name="Decision — Tomar Decisões",
        replace_existing=True,
        misfire_grace_time=300,
    )

    # 5. Creative — avalia criativos
    scheduler.add_job(
        job_creative,
        CronTrigger(hour="0,6,12,18", minute=40),
        id="creative",
        name="Creative — Análise de Criativos",
        replace_existing=True,
        misfire_grace_time=300,
    )

    # 6. Budget Optimizer — redistribui budgets (1h depois do scanner)
    scheduler.add_job(
        job_budget_optimizer,
        CronTrigger(hour="1,7,13,19", minute=0),
        id="budget_optimizer",
        name="Budget Optimizer — Redistribuir Budgets",
        replace_existing=True,
        misfire_grace_time=300,
    )

    # 7. Executor — executa ações pendentes (a cada hora, no minuto 50)
    scheduler.add_job(
        job_executor,
        CronTrigger(minute=50),
        id="executor",
        name="Executor — Executar Ações Pendentes",
        replace_existing=True,
        misfire_grace_time=120,
    )

    # 8. WhatsApp — relatório diário às 08h00
    scheduler.add_job(
        job_whatsapp,
        CronTrigger(hour=8, minute=0),
        id="whatsapp",
        name="WhatsApp — Relatório Diário",
        replace_existing=True,
        misfire_grace_time=600,
    )

    # 9. Learning — extrai lições às 23h00 (depois dos dados do dia)
    scheduler.add_job(
        job_learning,
        CronTrigger(hour=23, minute=0),
        id="learning",
        name="Learning — Extrair Lições do Dia",
        replace_existing=True,
        misfire_grace_time=600,
    )

    logger.info("scheduler.configured", jobs=len(scheduler.get_jobs()))
