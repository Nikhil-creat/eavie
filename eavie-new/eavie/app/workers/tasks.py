import asyncio, uuid
import structlog
from sqlalchemy import update
from app.db.models import Job
from app.db.session import SessionLocal
from app.services.cnn_inference import get_engine
from app.workers.celery_app import celery

log = structlog.get_logger()

async def _set(job_id: str, **vals):
    async with SessionLocal() as s:
        await s.execute(update(Job).where(Job.id == uuid.UUID(job_id)).values(**vals))
        await s.commit()

def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()

@celery.task(bind=True, name="vision.batch", queue="vision", acks_late=True,
             autoretry_for=(OSError,), retry_backoff=True, max_retries=3)
def batch_vision(self, job_id: str, paths: list[str]):
    async def go():
        await _set(job_id, status="running", progress=0)
        res = await asyncio.to_thread(get_engine().predict_paths, paths)
        flagged = sum(r["defect"] for r in res)
        await _set(job_id, status="done", progress=100, result={"count": len(res), "defects": flagged, "items": res})
        return {"count": len(res), "defects": flagged}
    try:
        return _run(go())
    except Exception as e:
        log.error("batch_vision_failed", job=job_id, err=str(e))
        _run(_set(job_id, status="failed", error=str(e)[:500]))
        raise

@celery.task(bind=True, name="rag.ingest", queue="ingest", acks_late=True, max_retries=2)
def ingest_document(self, job_id: str, path: str, mime: str):
    from app.services.rag_engine import ingest_file
    async def go():
        await _set(job_id, status="running")
        n = await ingest_file(path, mime)  # parse -> chunk -> embed -> Qdrant upsert + BM25 index
        await _set(job_id, status="done", progress=100, result={"chunks": n})
        return n
    try:
        return _run(go())
    except Exception as e:
        _run(_set(job_id, status="failed", error=str(e)[:500]))
        raise
