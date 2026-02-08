import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from services.qdrant import ensure_collection, is_healthy
from routers import search, webhook

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting up — ensuring Qdrant collection exists")
    ensure_collection()
    logger.info("Startup complete")
    yield


app = FastAPI(title="Estimate RAG API", lifespan=lifespan)
app.include_router(search.router)
app.include_router(webhook.router)


@app.get("/api/v1/health")
async def health():
    qdrant_ok = is_healthy()
    return {
        "status": "ok" if qdrant_ok else "degraded",
        "qdrant": "connected" if qdrant_ok else "disconnected",
    }
