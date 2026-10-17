import time
import redis.asyncio as aioredis
from fastapi import Depends, HTTPException, Request
from app.core.config import settings

pool = aioredis.ConnectionPool.from_url(settings.REDIS_URL, decode_responses=True, max_connections=50)
def get_redis() -> aioredis.Redis: return aioredis.Redis(connection_pool=pool)

LEAKY = """local k=KEYS[1];local cap=tonumber(ARGV[1]);local rate=tonumber(ARGV[2]);local now=tonumber(ARGV[3])
local d=redis.call('HMGET',k,'lvl','ts');local lvl=tonumber(d[1]) or 0;local ts=tonumber(d[2]) or now
lvl=math.max(0,lvl-(now-ts)*rate)
if lvl+1>cap then redis.call('HMSET',k,'lvl',lvl,'ts',now);redis.call('EXPIRE',k,120);return 0 end
redis.call('HMSET',k,'lvl',lvl+1,'ts',now);redis.call('EXPIRE',k,120);return 1"""

async def rate_limit(request: Request, r: aioredis.Redis = Depends(get_redis)):
    ident = request.client.host if request.client else "anon"
    ok = await r.eval(LEAKY, 1, f"rl:{ident}", settings.RATE_CAPACITY, settings.RATE_LEAK_PER_SEC, time.time())
    if not ok: raise HTTPException(429, "Rate limit exceeded", {"Retry-After": "2"})
