import json
from fastapi import APIRouter, Depends, HTTPException, Request, Security
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse
from app.core.redis import rate_limit
from app.core.security import get_current_user
from app.services.agentic_workflow import run_agent, stream_agent

router = APIRouter(prefix="/agent", tags=["agent"])

class AgentRequest(BaseModel):
    query: str = Field(min_length=3, max_length=4000)
    image_paths: list[str] = Field(default_factory=list, max_length=8)

class AgentResponse(BaseModel):
    answer: str
    score: float | None = None
    trace: list[str]
    sources: list[dict] = []
    vision: list[dict] = []

def _safe(paths: list[str]) -> list[str]:
    if any(not p.startswith("/data/uploads/") or ".." in p for p in paths):
        raise HTTPException(400, "image_paths must be under /data/uploads")
    return paths

@router.post("/run", response_model=AgentResponse)
async def run(req: AgentRequest, user=Security(get_current_user, scopes=["user"]), _=Depends(rate_limit)):
    st = await run_agent(req.query, _safe(req.image_paths))
    return AgentResponse(answer=st.get("answer", ""), score=st.get("score"), trace=st.get("trace", []),
                         sources=[{"text": d["text"][:300], "score": d.get("score")} for d in st.get("context", [])],
                         vision=st.get("vision", []))

@router.get("/stream")
async def stream(request: Request, query: str, user=Security(get_current_user, scopes=["user"]), _=Depends(rate_limit)):
    async def gen():
        try:
            async for ev in stream_agent(query):
                if await request.is_disconnected():
                    break
                d = ev["data"]
                yield {"event": ev["event"], "data": d if isinstance(d, str) else json.dumps(d)}
        except Exception as e:
            yield {"event": "error", "data": str(e)[:200]}
    return EventSourceResponse(gen(), headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"})
