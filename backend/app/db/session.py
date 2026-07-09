import ssl
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import NullPool

from app.core.config import settings

# Supabase requer SSL — passar o objeto SSLContext com verify desabilitado
_ssl_ctx = ssl.create_default_context()
_ssl_ctx.check_hostname = False
_ssl_ctx.verify_mode = ssl.CERT_NONE

def _make_engine():
    url = settings.DATABASE_URL
    return create_async_engine(
        url,
        poolclass=NullPool,
        echo=False,
        connect_args={
            "ssl": _ssl_ctx,
            "statement_cache_size": 0,  # required for pgbouncer/Supavisor pooler
        },
    )

engine = _make_engine()

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


class Base(DeclarativeBase):
    pass


async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
