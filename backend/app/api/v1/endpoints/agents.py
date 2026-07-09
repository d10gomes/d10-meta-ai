"""Agent endpoints — manual triggers + status + run history."""
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, BackgroundTasks
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import require_role
from app.core.scheduler import (
    scheduler, job_scanner, job_doctor_and_decision, job_executor,
    job_whatsapp_daily, job_analyst, job_budget_optimizer, job_campaign_manager,
)
from app.db.models import User, AgentRun, AgentInsight
from app.db.session import get_db
from app.agents.creative.service import CreativeService

router = APIRouter()

# ---------------------------------------------------------------------------
# Agent metadata
# ---------------------------------------------------------------------------

AGENT_META = {
    "scanner": {
        "name": "Scanner Agent",
        "description": "Sincroniza campanhas, adsets, anúncios e métricas do Meta Ads",
        "icon": "🔍",
        "schedule": "A cada 6 horas",
        "cron": "0 0,6,12,18 * * *",
        "category": "infra",
    },
    "analyst": {
        "name": "Analyst Agent",
        "description": "Análise completa de performance: KPIs, rankings, alertas e recomendações estratégicas",
        "icon": "🧠",
        "schedule": "Diário às 07h00",
        "cron": "0 7 * * *",
        "category": "specialist",
    },
    "budget_optimizer": {
        "name": "Budget Optimizer",
        "description": "Redistribui orçamentos automaticamente: escala winners (ROAS > 3x), corta losers (ROAS < 0.8x)",
        "icon": "💰",
        "schedule": "A cada 6 horas",
        "cron": "0 1,7,13,19 * * *",
        "category": "specialist",
    },
    "campaign_manager": {
        "name": "Campaign Manager",
        "description": "Gerencia ciclo de vida: pausa losers, detecta saturação, identifica winners para escalar",
        "icon": "🎯",
        "schedule": "A cada 3 horas",
        "cron": "30 3,6,9,12,15,18,21,0 * * *",
        "category": "specialist",
    },
    "doctor": {
        "name": "Doctor Agent",
        "description": "Diagnostica problemas: CTR baixo, CPA alto, frequência alta, ROAS ruim",
        "icon": "🩺",
        "schedule": "A cada 6 horas",
        "cron": "30 0,6,12,18 * * *",
        "category": "infra",
    },
    "executor": {
        "name": "Executor Agent",
        "description": "Executa ações aprovadas: pausar anúncios, ajustar orçamentos, duplicar campanhas",
        "icon": "⚡",
        "schedule": "A cada hora",
        "cron": "0 * * * *",
        "category": "infra",
    },
    "whatsapp": {
        "name": "WhatsApp Agent",
        "description": "Envia relatório diário de performance via WhatsApp",
        "icon": "📱",
        "schedule": "Diário às 08h00",
        "cron": "0 8 * * *",
        "category": "infra",
    },
}


def _next_run(job_id: str) -> str | None:
    job = scheduler.get_job(job_id)
    if job and job.next_run_time:
        return job.next_run_time.isoformat()
    return None


# ---------------------------------------------------------------------------
# Status endpoint
# ---------------------------------------------------------------------------

@router.get("/status")
async def agents_status(
    current_user: User = Depends(require_role("admin", "manager", "viewer")),
    db: AsyncSession = Depends(get_db),
):
    """Returns status of all agents: last run, next run, health."""
    agents = []
    for agent_id, meta in AGENT_META.items():
        # Last run from DB
        result = await db.execute(
            select(AgentRun)
            .where(AgentRun.agent_name == agent_id)
            .order_by(AgentRun.started_at.desc())
            .limit(1)
        )
        last = result.scalar_one_or_none()

        agents.append({
            "id": agent_id,
            **meta,
            "next_run": _next_run(agent_id),
            "last_run": {
                "started_at": last.started_at.isoformat() if last else None,
                "finished_at": last.finished_at.isoformat() if last and last.finished_at else None,
                "status": last.status if last else "never",
                "duration_seconds": last.duration_seconds if last else None,
                "items_processed": last.items_processed if last else None,
                "error": last.error if last else None,
                "trigger": last.trigger if last else None,
            } if last else None,
        })

    return {"agents": agents, "scheduler_running": scheduler.running}


# ---------------------------------------------------------------------------
# Run history
# ---------------------------------------------------------------------------

@router.get("/runs")
async def agent_runs(
    agent: str | None = None,
    limit: int = 50,
    current_user: User = Depends(require_role("admin", "manager", "viewer")),
    db: AsyncSession = Depends(get_db),
):
    q = select(AgentRun).order_by(AgentRun.started_at.desc()).limit(limit)
    if agent:
        q = q.where(AgentRun.agent_name == agent)
    result = await db.execute(q)
    runs = result.scalars().all()
    return [
        {
            "id": r.id,
            "agent_name": r.agent_name,
            "trigger": r.trigger,
            "status": r.status,
            "started_at": r.started_at.isoformat() if r.started_at else None,
            "finished_at": r.finished_at.isoformat() if r.finished_at else None,
            "duration_seconds": r.duration_seconds,
            "items_processed": r.items_processed,
            "error": r.error,
        }
        for r in runs
    ]


# ---------------------------------------------------------------------------
# Manual triggers (also record a run)
# ---------------------------------------------------------------------------

@router.post("/scan")
async def trigger_scan(
    background_tasks: BackgroundTasks,
    current_user: User = Depends(require_role("admin", "manager")),
):
    async def _run():
        await job_scanner.__wrapped__() if hasattr(job_scanner, "__wrapped__") else await job_scanner()
    background_tasks.add_task(job_scanner)
    return {"status": "scan started"}


@router.post("/doctor")
async def trigger_doctor(
    background_tasks: BackgroundTasks,
    current_user: User = Depends(require_role("admin", "manager")),
):
    background_tasks.add_task(job_doctor_and_decision)
    return {"status": "doctor started"}


@router.post("/execute")
async def trigger_execute(
    background_tasks: BackgroundTasks,
    current_user: User = Depends(require_role("admin")),
):
    background_tasks.add_task(job_executor)
    return {"status": "executor started"}


@router.post("/report/whatsapp")
async def send_whatsapp_report(
    background_tasks: BackgroundTasks,
    report_type: str = "daily",
    current_user: User = Depends(require_role("admin")),
):
    background_tasks.add_task(job_whatsapp_daily)
    return {"status": "report queued"}


@router.post("/analyze")
async def trigger_analyst(
    background_tasks: BackgroundTasks,
    current_user: User = Depends(require_role("admin", "manager")),
):
    background_tasks.add_task(job_analyst)
    return {"status": "analyst started"}


@router.post("/optimize-budget")
async def trigger_budget_optimizer(
    background_tasks: BackgroundTasks,
    current_user: User = Depends(require_role("admin", "manager")),
):
    background_tasks.add_task(job_budget_optimizer)
    return {"status": "budget optimizer started"}


@router.post("/manage-campaigns")
async def trigger_campaign_manager(
    background_tasks: BackgroundTasks,
    current_user: User = Depends(require_role("admin", "manager")),
):
    background_tasks.add_task(job_campaign_manager)
    return {"status": "campaign manager started"}


@router.get("/insights")
async def get_insights(
    agent: str | None = None,
    limit: int = 20,
    current_user: User = Depends(require_role("admin", "manager", "viewer")),
    db: AsyncSession = Depends(get_db),
):
    """Returns agent insights/reports for the current tenant."""
    q = (
        select(AgentInsight)
        .where(AgentInsight.tenant_id == str(current_user.tenant_id))
        .order_by(AgentInsight.created_at.desc())
        .limit(limit)
    )
    if agent:
        q = q.where(AgentInsight.agent_name == agent)
    result = await db.execute(q)
    insights = result.scalars().all()
    return [
        {
            "id": i.id,
            "agent_name": i.agent_name,
            "title": i.title,
            "summary": i.summary,
            "details": i.details,
            "actions_taken": i.actions_taken,
            "created_at": i.created_at.isoformat() if i.created_at else None,
        }
        for i in insights
    ]


@router.get("/creatives/{meta_account_id}")
async def rank_creatives(
    meta_account_id: str,
    current_user: User = Depends(require_role("admin", "manager", "viewer")),
    db: AsyncSession = Depends(get_db),
):
    return await CreativeService(db).rank_creatives(meta_account_id)
