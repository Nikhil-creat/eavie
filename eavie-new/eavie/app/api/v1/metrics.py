from fastapi import APIRouter, Response
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
REQS = Counter("eavie_requests_total", "Requests", ["method", "path", "status"])
LAT = Histogram("eavie_request_seconds", "Latency", ["path"])
router = APIRouter(tags=["metrics"])
@router.get("/metrics")
def metrics(): return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
