"""Performance Monitor API — disparo manual + histórico de análises."""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import get_current_user, get_db
from app.db.models import User

router = APIRouter(prefix="/monitor", tags=["monitor"])


@router.post("/run")
async def run_monitor(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Dispara uma análise imediata sem esperar o horário agendado."""
    from app.agents.performance_monitor.service import PerformanceMonitor
    monitor = PerformanceMonitor(db)
    result = await monitor.run(str(user.tenant_id))
    return result


@router.get("/history")
async def monitor_history(
    limit: int = 20,
    user: User = Depends(get_current_user),
):
    """Retorna histórico das últimas análises salvas no Brain."""
    from app.core import brain
    lines = brain.read_lines("monitor/history", tenant_id=str(user.tenant_id), limit=limit)
    return {"history": list(reversed(lines))}
