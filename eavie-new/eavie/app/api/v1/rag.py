import os, uuid
from fastapi import APIRouter, Depends, File, Security, UploadFile
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.redis import rate_limit
from app.core.security import get_current_user
from app.db.models import Job
from app.db.session import get_db
from app.services.rag_engine import hybrid_search
from app.workers.tasks import ingest_document
router = APIRouter(prefix="/rag", tags=["rag"])
class Q(BaseModel): query: str; top_k: int = 5
@router.post("/query")
async def query(b: Q, u=Security(get_current_user, scopes=["user"]), _=Depends(rate_limit)):
    return {"results": await hybrid_search(b.query, b.top_k)}
@router.post("/ingest", status_code=202)
async def ingest(file: UploadFile = File(...), u=Security(get_current_user, scopes=["analyst"]), db: AsyncSession = Depends(get_db)):
    path = f"/data/uploads/{uuid.uuid4()}_{os.path.basename(file.filename)}"
    open(path, "wb").write(await file.read())
    j = Job(owner_id=u.id, kind="ingest"); db.add(j); await db.commit()
    ingest_document.delay(str(j.id), path, file.content_type or "text/plain")
    return {"job_id": str(j.id)}
