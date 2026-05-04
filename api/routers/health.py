"""Gibson health check — Phase 0 deliverable."""

from fastapi import APIRouter
import api.database as db

router = APIRouter()


@router.get("/health")
async def health_check():
    """GET /api/health → {status, database, version}"""
    db_ok = False
    db_detail = "disconnected"
    if db._pool is not None:
        try:
            result = await db.fetchval("SELECT 1")
            db_ok = result == 1
            db_detail = "connected"
        except Exception as e:
            db_detail = f"error: {e}"
    else:
        db_detail = "pool not initialized — check DATABASE_URL in .env (use Supabase Session Pooler URI)"

    return {
        "status": "ok" if db_ok else "degraded",
        "database": db_detail,
        "version": "0.1.0",
    }
