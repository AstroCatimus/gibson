"""
Gibson — Bibliographic Intelligence System
Alexandria Book Co-op

FastAPI application entry point.
Serves the API and the PWA static files.
"""

import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import logging
import logging.handlers
import os
from pathlib import Path

from api.config import settings
from api.database import init_pool, close_pool


# ─── Logging setup ───────────────────────────────────────────
def setup_logging():
    """
    Configure Gibson's logging system.

    All gibson.* loggers write to logs/gibson.log (rotating, 5MB × 5 files).
    Also mirrors to the console so the terminal still shows output.
    Uvicorn's own request logs are left alone.
    """
    log_dir = Path(__file__).parent.parent / "logs"
    log_dir.mkdir(exist_ok=True)

    formatter = logging.Formatter(
        fmt="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Rotating file — 5 MB per file, keep 5 backups (~25 MB total)
    file_handler = logging.handlers.RotatingFileHandler(
        log_dir / "gibson.log",
        maxBytes=5 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    file_handler.setLevel(logging.DEBUG)

    # Console mirror
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    console_handler.setLevel(logging.INFO)

    # Attach both handlers to the gibson root logger.
    # All gibson.* child loggers inherit this automatically.
    gibson_logger = logging.getLogger("gibson")
    gibson_logger.setLevel(logging.DEBUG)
    gibson_logger.addHandler(file_handler)
    gibson_logger.addHandler(console_handler)
    gibson_logger.propagate = False  # don't double-log to the root logger


setup_logging()

# Import routers
from api.routers import (
    identification,
    pricing,
    catalogue,
    inventory,
    pos,
    research,
    ghostbook,
    shelfie,
    whatnot,
    customer,
    conversation,
    health,
    stores,
    defrag,
    imports,
    listings,
    deep_lookup,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events."""
    await init_pool()
    from api.routers.imports import queue_worker
    from api.workers.order_sync import order_sync_worker
    import_task = asyncio.create_task(queue_worker())
    sync_task   = asyncio.create_task(order_sync_worker())
    yield
    import_task.cancel()
    sync_task.cancel()
    await close_pool()


app = FastAPI(
    title="Gibson",
    description="Bibliographic Intelligence System — Alexandria Book Co-op",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── API Routes ──────────────────────────────────────────────

app.include_router(health.router, prefix="/api", tags=["health"])
app.include_router(identification.router, prefix="/api/identification", tags=["identification"])
app.include_router(pricing.router, prefix="/api/pricing", tags=["pricing"])
app.include_router(catalogue.router, prefix="/api/catalogue", tags=["catalogue"])
app.include_router(inventory.router, prefix="/api/inventory", tags=["inventory"])
app.include_router(pos.router, prefix="/api/pos", tags=["pos"])
app.include_router(research.router, prefix="/api/research", tags=["research"])
app.include_router(ghostbook.router, prefix="/api/ghostbook", tags=["ghostbook"])
app.include_router(shelfie.router, prefix="/api/shelfie", tags=["shelfie"])
app.include_router(whatnot.router, prefix="/api/whatnot", tags=["whatnot"])
app.include_router(customer.router, prefix="/api/customer", tags=["customer"])
app.include_router(conversation.router, prefix="/api/conversation", tags=["conversation"])
app.include_router(stores.router,       prefix="/api/stores",       tags=["stores"])
app.include_router(defrag.router,       prefix="/api/defrag",       tags=["defrag"])
app.include_router(imports.router,      prefix="/api/import",       tags=["import"])
app.include_router(listings.router,     prefix="/api/listings",     tags=["listings"])
app.include_router(deep_lookup.router,  prefix="/api",              tags=["deep-lookup"])

# ─── PWA Static Files ────────────────────────────────────────

pwa_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "pwa")
if os.path.isdir(pwa_path):
    app.mount("/static", StaticFiles(directory=pwa_path), name="pwa-static")

    @app.get("/")
    async def serve_pwa():
        """Serve the PWA index.html at root."""
        return FileResponse(os.path.join(pwa_path, "index.html"))

    @app.get("/manifest.json")
    async def serve_manifest():
        return FileResponse(os.path.join(pwa_path, "manifest.json"))

    @app.get("/service-worker.js")
    async def serve_sw():
        return FileResponse(os.path.join(pwa_path, "service-worker.js"))
