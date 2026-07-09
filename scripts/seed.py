"""Seed script — creates a demo tenant + admin user for local development."""
import asyncio
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.db.session import AsyncSessionLocal
from app.db.models import Tenant, User
from app.core.security import hash_password


async def seed():
    async with AsyncSessionLocal() as session:
        tenant = Tenant(name="D10 Demo", slug="d10-demo", max_meta_accounts=15)
        session.add(tenant)
        await session.flush()

        user = User(
            tenant_id=str(tenant.id),
            email="admin@d10.ai",
            hashed_password=hash_password("d10admin123"),
            name="Admin D10",
            role="admin",
        )
        session.add(user)
        await session.commit()

        print(f"✅ Tenant criado: {tenant.id}")
        print(f"✅ Admin criado: admin@d10.ai / d10admin123")


asyncio.run(seed())
