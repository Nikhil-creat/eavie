"""EAVIE stateful LangGraph agent: guardrail -> rag/vision -> evaluator -(self-correct loop)-> synthesizer (token streaming)."""
from __future__ import annotations
import time
from typing import Any, AsyncIterator, Literal, TypedDict
import structlog
from groq import AsyncGroq
from langgraph.config import get_stream_writer
from langgraph.graph import END, START, StateGraph
from app.core.config import settings
from app.services import guardrails
from app.services.cnn_inference import get_engine
from app.services.rag_engine import hybrid_search

log = structlog.get_logger()
MAX_LOOPS = 2

class AgentState(TypedDict, total=False):
    query: str
    image_paths: list[str]
    intent: Literal["rag", "vision", "both", "blocked"]
    context: list[dict[str, Any]]
    vision: list[dict[str, Any]]
    score: float
    retry: bool
    loops: int
    answer: str
    trace: list[str]

def _llm() -> AsyncGroq:
    return AsyncGroq(api_key=settings.GROQ_API_KEY)

def _t(s: AgentState, node: str) -> list[str]:
    return [*s.get("trace", []), node]

async def guardrail_node(s: AgentState) -> AgentState:
    v = guardrails.check_input(s["query"])
    if not v.ok:
        return {"intent": "blocked", "answer": f"Request blocked: {v.reason}", "trace": _t(s, "guardrail")}
    has_img = bool(s.get("image_paths"))
    intent = "both" if has_img and len(v.sanitized.split()) > 3 else "vision" if has_img else "rag"
    return {"query": v.sanitized, "intent": intent, "loops": 0, "trace": _t(s, "guardrail")}

async def rag_node(s: AgentState) -> AgentState:
    t0 = time.perf_counter()
    docs = await hybrid_search(s["query"], top_k=6)  # dense + BM25 -> RRF -> cross-encoder rerank
    log.info("rag_done", n=len(docs), ms=round((time.perf_counter() - t0) * 1000))
    return {"context": docs, "trace": _t(s, "rag")}

async def vision_node(s: AgentState) -> AgentState:
    res = await get_engine().predict_paths_async(s.get("image_paths", []))
    return {"vision": res, "trace": _t(s, "vision")}

async def evaluator_node(s: AgentState) -> AgentState:
    ctx, vis = s.get("context", []), s.get("vision", [])
    scores = []
    if s["intent"] in ("rag", "both"):
        scores.append(sum(d.get("score", 0) for d in ctx) / len(ctx) if ctx else 0.0)
    if s["intent"] in ("vision", "both"):
        scores.append(sum(v["confidence"] for v in vis) / len(vis) if vis else 0.0)
    score = sum(scores) / max(len(scores), 1)
    upd: AgentState = {"score": score, "retry": False, "trace": _t(s, f"evaluator({score:.2f})")}
    if score < settings.EVAL_THRESHOLD and s.get("loops", 0) < MAX_LOOPS and s["intent"] != "vision":
        r = await _llm().chat.completions.create(
            model=settings.GROQ_MODEL, temperature=0, max_tokens=60,
            messages=[{"role": "user", "content": f"Rewrite as a broader keyword-rich search query:\n{s['query']}"}])
        upd.update(query=r.choices[0].message.content.strip(), loops=s.get("loops", 0) + 1, retry=True)
    return upd

async def synthesizer_node(s: AgentState) -> AgentState:
    write = get_stream_writer()
    ctx = "\n\n".join(f"[{i+1}] {d['text']}" for i, d in enumerate(s.get("context", [])))
    vis = "\n".join(f"- {v['path']}: {v['label']} ({v['confidence']:.2f})" for v in s.get("vision", []))
    prompt = f"Answer using only the evidence; cite [n].\n\nQUESTION: {s['query']}\n\nDOCUMENTS:\n{ctx or 'none'}\n\nVISION:\n{vis or 'none'}"
    out: list[str] = []
    stream = await _llm().chat.completions.create(
        model=settings.GROQ_MODEL, stream=True, temperature=0.2, max_tokens=900,
        messages=[{"role": "system", "content": "You are EAVIE, an enterprise inspection and knowledge analyst."},
                  {"role": "user", "content": prompt}])
    async for chunk in stream:
        tok = chunk.choices[0].delta.content or ""
        if tok:
            out.append(tok)
            write({"token": tok})
    return {"answer": guardrails.validate_output("".join(out)), "trace": _t(s, "synthesizer")}

def build_graph():
    g = StateGraph(AgentState)
    for name, fn in [("guardrail", guardrail_node), ("rag", rag_node), ("vision", vision_node),
                     ("evaluator", evaluator_node), ("synth", synthesizer_node)]:
        g.add_node(name, fn)
    g.add_edge(START, "guardrail")
    g.add_conditional_edges("guardrail", lambda s: {"rag": "rag", "both": "rag", "vision": "vision"}.get(s["intent"], "end"),
                            {"rag": "rag", "vision": "vision", "end": END})
    g.add_conditional_edges("rag", lambda s: "vision" if s["intent"] == "both" and not s.get("vision") else "evaluator",
                            {"vision": "vision", "evaluator": "evaluator"})
    g.add_edge("vision", "evaluator")
    g.add_conditional_edges("evaluator", lambda s: "rag" if s.get("retry") else "synth", {"rag": "rag", "synth": "synth"})
    g.add_edge("synth", END)
    return g.compile()

graph = build_graph()

async def run_agent(query: str, image_paths: list[str] | None = None) -> AgentState:
    return await graph.ainvoke({"query": query, "image_paths": image_paths or [], "trace": []})

async def stream_agent(query: str, image_paths: list[str] | None = None) -> AsyncIterator[dict[str, Any]]:
    init = {"query": query, "image_paths": image_paths or [], "trace": []}
    async for mode, payload in graph.astream(init, stream_mode=["updates", "custom"]):
        if mode == "custom":
            yield {"event": "token", "data": payload["token"]}
            continue
        for node, upd in payload.items():
            yield {"event": "node", "data": node}
            if node == "guardrail" and upd.get("intent") == "blocked":
                yield {"event": "token", "data": upd["answer"]}
                yield {"event": "done", "data": {"trace": upd["trace"]}}
            if node == "synth":
                yield {"event": "done", "data": {"trace": upd["trace"]}}
