import time, uuid
import structlog
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from app.api.v1 import agent, auth, metrics, rag, vision
from app.api.v1.metrics import LAT, REQS
from app.core.logging import setup_logging, setup_tracing
from app.db.models import Base
from app.db.session import engine

@asynccontextmanager
async def lifespan(app):
    setup_logging()
    async with engine.begin() as c: await c.run_sync(Base.metadata.create_all)
    yield
    await engine.dispose()

app = FastAPI(title="EAVIE", version="2.0", lifespan=lifespan)
setup_tracing(app, engine)

@app.middleware("http")
async def telemetry(req: Request, call_next):
    rid = req.headers.get("x-request-id", str(uuid.uuid4()))
    structlog.contextvars.bind_contextvars(request_id=rid)
    t0 = time.perf_counter()
    res = await call_next(req)
    LAT.labels(req.url.path).observe(time.perf_counter() - t0)
    REQS.labels(req.method, req.url.path, res.status_code).inc()
    res.headers["x-request-id"] = rid
    structlog.contextvars.clear_contextvars()
    return res

@app.get("/healthz")
async def healthz(): return {"status": "ok"}
for r in (auth.router, agent.router, rag.router, vision.router, metrics.router):
    app.include_router(r, prefix="/api/v1")
