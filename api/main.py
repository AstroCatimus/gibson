"""
Gibson — Bibliographic Intelligence System
Alexandria Book Co-op

FastAPI application entry point.
Serves the API and the PWA static files.
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import os

from api.config import settings
from api.database import init_pool, close_pool

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
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events."""
    await init_pool()
    yield
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
