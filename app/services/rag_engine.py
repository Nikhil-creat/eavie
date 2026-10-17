"""Hybrid RAG: Qdrant dense + BM25 -> RRF -> BGE cross-encoder."""
import asyncio, re, uuid
from functools import lru_cache
from pypdf import PdfReader
from qdrant_client import AsyncQdrantClient, models as qm
from rank_bm25 import BM25Okapi
from app.core.config import settings

COL = "eavie_chunks"
_corpus: list[dict] = []
_bm25: BM25Okapi | None = None
_tok = lambda s: re.findall(r"\w+", s.lower())

@lru_cache(1)
def _embedder():
    from sentence_transformers import SentenceTransformer
    return SentenceTransformer(settings.EMBED_MODEL)
@lru_cache(1)
def _reranker():
    from sentence_transformers import CrossEncoder
    return CrossEncoder(settings.RERANK_MODEL)
@lru_cache(1)
def _qdrant():
    return AsyncQdrantClient(location=settings.QDRANT_URL) if settings.QDRANT_URL == ":memory:" else AsyncQdrantClient(url=settings.QDRANT_URL)

async def _ensure():
    q = _qdrant()
    if not await q.collection_exists(COL):
        await q.create_collection(COL, vectors_config=qm.VectorParams(size=_embedder().get_sentence_embedding_dimension(), distance=qm.Distance.COSINE))

def _chunks(text: str, n=900, o=150): return [text[i:i + n] for i in range(0, max(len(text), 1), n - o)]

async def ingest_file(path: str, mime: str) -> int:
    global _bm25
    text = "\n".join(p.extract_text() or "" for p in PdfReader(path).pages) if mime == "application/pdf" else open(path, encoding="utf-8", errors="ignore").read()
    parts = _chunks(text)
    vecs = await asyncio.to_thread(_embedder().encode, parts, normalize_embeddings=True)
    await _ensure()
    pts = []
    for i, (t, v) in enumerate(zip(parts, vecs)):
        pid = str(uuid.uuid4()); _corpus.append({"id": pid, "text": t, "source": path})
        pts.append(qm.PointStruct(id=pid, vector=v.tolist(), payload={"text": t, "source": path, "idx": i}))
    await _qdrant().upsert(COL, pts)
    _bm25 = BM25Okapi([_tok(c["text"]) for c in _corpus])
    return len(parts)

def _rrf(*lists, k=60):
    sc: dict[str, float] = {}
    for l in lists:
        for r, d in enumerate(l): sc[d["id"]] = sc.get(d["id"], 0) + 1 / (k + r + 1)
    return sc

async def hybrid_search(query: str, top_k: int = 6) -> list[dict]:
    if not _corpus: return []
    await _ensure()
    qv = (await asyncio.to_thread(_embedder().encode, [query], normalize_embeddings=True))[0].tolist()
    hits = await _qdrant().search(COL, query_vector=qv, limit=20)
    dense = [{"id": str(h.id), "text": h.payload["text"]} for h in hits]
    s = _bm25.get_scores(_tok(query))
    lex = [_corpus[i] for i in sorted(range(len(s)), key=lambda i: -s[i])[:20] if s[i] > 0]
    fused = _rrf(dense, lex); byid = {d["id"]: d for d in dense + lex}
    cand = [byid[i] for i in sorted(fused, key=fused.get, reverse=True)[:20]]
    if not cand: return []
    rs = await asyncio.to_thread(_reranker().predict, [(query, c["text"]) for c in cand])
    import math
    out = sorted(({**c, "score": 1 / (1 + math.exp(-float(x)))} for c, x in zip(cand, rs)), key=lambda d: -d["score"])
    return out[:top_k]
