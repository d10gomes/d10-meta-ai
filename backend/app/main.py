import asyncio
import sys

# Windows: forçar ProactorEventLoop para SSL funcionar com asyncpg
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router
import sqlalchemy
from app.core.config import settings
from app.core.logging import configure_logging, logger
from app.core.scheduler import scheduler, setup_scheduler
from app.db.session import engine, Base
from app.infrastructure.cache.redis_client import redis_client


async def _startup_scan():
    """Roda o scanner uma vez após o startup para garantir dados frescos."""
    try:
        from app.core.scheduler import job_scanner
        logger.info("startup_scan.starting")
        await job_scanner()
        logger.info("startup_scan.done")
    except Exception as exc:
        logger.warning("startup_scan.failed", error=str(exc))


async def _run_migrations():
    """Add new columns without Alembic — safe to run on every startup."""
    migrations = [
        "ALTER TABLE tenants ADD COLUMN IF NOT EXISTS telegram_chat_id VARCHAR(100)",
        "ALTER TABLE tenants ADD COLUMN IF NOT EXISTS whatsapp_number VARCHAR(30)",
    ]
    try:
        async with engine.begin() as conn:
            for sql in migrations:
                await conn.execute(sqlalchemy.text(sql))
        logger.info("migrations.done")
    except Exception as exc:
        logger.warning("migrations.failed", error=str(exc))


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    try:
        async with asyncio.timeout(5):
            async with engine.connect() as conn:
                await conn.execute(sqlalchemy.text("SELECT 1"))
        logger.info("db.connected")
    except Exception as exc:
        logger.warning("db.connection_warning", error=str(exc))
    await _run_migrations()
    try:
        async with asyncio.timeout(3):
            await redis_client.ping()
        logger.info("redis.connected")
    except Exception as exc:
        logger.warning("redis.connection_warning", error=str(exc))
    setup_scheduler()
    scheduler.start()
    logger.info("scheduler.started")
    # Dispara o scanner 30s após o início para popular dados imediatamente
    asyncio.get_event_loop().call_later(30, lambda: asyncio.create_task(_startup_scan()))
    yield
    scheduler.shutdown(wait=False)
    logger.info("scheduler.stopped")
    await redis_client.aclose()


app = FastAPI(
    title="D10 META AI",
    description="Plataforma inteligente de gestão e automação de Meta Ads",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix="/api/v1")


@app.get("/health")
async def health():
    return {"status": "ok", "service": "D10 META AI"}
