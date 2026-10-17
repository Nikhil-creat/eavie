import json, os, uuid
from fastapi import APIRouter, Depends, File, HTTPException, Security, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.redis import get_redis, rate_limit
from app.core.security import get_current_user
from app.db.models import Job
from app.db.session import get_db
from app.services.cnn_inference import get_engine
from app.workers.tasks import batch_vision
router = APIRouter(tags=["vision"])
@router.post("/vision/predict")
async def predict(file: UploadFile = File(...), u=Security(get_current_user, scopes=["user"]), _=Depends(rate_limit)):
    return get_engine().predict_bytes(await file.read(), file.filename or "upload")
@router.post("/vision/batch", status_code=202)
async def batch(files: list[UploadFile] = File(...), u=Security(get_current_user, scopes=["analyst"]), db: AsyncSession = Depends(get_db)):
    if len(files) > 64: raise HTTPException(413, "max 64 images")
    paths = []
    for f in files:
        p = f"/data/uploads/{uuid.uuid4()}_{os.path.basename(f.filename or 'img')}"
        open(p, "wb").write(await f.read()); paths.append(p)
    j = Job(owner_id=u.id, kind="vision"); db.add(j); await db.commit()
    batch_vision.delay(str(j.id), paths)
    return {"job_id": str(j.id)}
@router.get("/jobs/{job_id}")
async def job(job_id: uuid.UUID, u=Security(get_current_user, scopes=["user"]), db: AsyncSession = Depends(get_db), r=Depends(get_redis)):
    c = await r.get(f"job:{job_id}")
    if c: return json.loads(c)
    j = await db.get(Job, job_id)
    if not j or (j.owner_id != u.id and u.role != "admin"): raise HTTPException(404, "not found")
    d = {"id": str(j.id), "status": j.status, "progress": j.progress, "result": j.result, "error": j.error}
    if j.status in ("done", "failed"): await r.setex(f"job:{job_id}", 300, json.dumps(d))
    return d
