"""
Gibson database connection — async PostgreSQL via asyncpg.
Raw SQL only. No ORM. This is a standing decision.
"""

import asyncpg
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Optional

from api.config import settings

# Connection pool — initialized on app startup
_pool: Optional[asyncpg.Pool] = None


async def init_pool():
    """Create the connection pool. Called once at app startup.
    Supabase requires SSL — ssl='require' is non-negotiable.

    NOTE: Startup is non-fatal. If the DB is unreachable (e.g. IPv6-only
    Supabase direct host on an IPv4-only network), the server still starts
    and returns 503 on DB-dependent endpoints until the connection is fixed.
    Use the Supabase Session Pooler URL (Settings → Database → Connection
    string → Session pooler) which has IPv4 support.
    """
    global _pool
    import logging
    logger = logging.getLogger(__name__)
    try:
        import asyncio
        _pool = await asyncio.wait_for(
            asyncpg.create_pool(
                settings.database_url,
                min_size=2,
                max_size=settings.database_pool_size,
                ssl="require",
                command_timeout=10,
            ),
            timeout=15,  # Don't hang startup more than 15s
        )
        logger.info("✓ Database pool connected")
    except Exception as e:
        logger.error(
            f"✗ Database pool failed to connect: {e}\n"
            "  Fix: in Supabase dashboard → Settings → Database → Connection string\n"
            "  Copy the 'Session pooler' URI and set it as DATABASE_URL in .env\n"
            "  Format: postgresql://postgres.[project-ref]:[password]"
            "@aws-0-[region].pooler.supabase.com:5432/postgres"
        )
        _pool = None


async def close_pool():
    """Close the connection pool. Called at app shutdown."""
    global _pool
    if _pool:
        await _pool.close()
        _pool = None


def get_pool() -> asyncpg.Pool:
    """Get the active connection pool. Raises HTTP 503 if not connected."""
    if _pool is None:
        from fastapi import HTTPException
        raise HTTPException(
            status_code=503,
            detail=(
                "Database unavailable. Check DATABASE_URL in .env — "
                "use the Supabase Session Pooler URI (IPv4-compatible). "
                "Go to: Supabase dashboard → Settings → Database → Connection string → Session pooler"
            ),
        )
    return _pool


@asynccontextmanager
async def get_connection() -> AsyncGenerator[asyncpg.Connection, None]:
    """Acquire a connection from the pool."""
    pool = get_pool()
    async with pool.acquire() as conn:
        yield conn


@asynccontextmanager
async def get_transaction() -> AsyncGenerator[asyncpg.Connection, None]:
    """Acquire a connection with an active transaction."""
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            yield conn


async def execute(query: str, *args):
    """Execute a query and return status."""
    async with get_connection() as conn:
        return await conn.execute(query, *args)


async def fetch(query: str, *args) -> list[asyncpg.Record]:
    """Execute a query and return all rows."""
    async with get_connection() as conn:
        return await conn.fetch(query, *args)


async def fetchrow(query: str, *args) -> Optional[asyncpg.Record]:
    """Execute a query and return the first row."""
    async with get_connection() as conn:
        return await conn.fetchrow(query, *args)


async def fetchval(query: str, *args):
    """Execute a query and return a single value."""
    async with get_connection() as conn:
        return await conn.fetchval(query, *args)
