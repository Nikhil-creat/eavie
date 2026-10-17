from datetime import datetime, timedelta, timezone
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, SecurityScopes
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import settings
from app.db.models import User
from app.db.session import get_db

pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")
SCOPES = {"admin": ["admin", "analyst", "user"], "analyst": ["analyst", "user"], "user": ["user"]}
oauth2 = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", scopes={"admin": "all", "analyst": "analyst", "user": "basic"})
hash_pw, verify_pw = pwd.hash, pwd.verify

def _tok(sub: str, role: str, kind: str, delta: timedelta) -> str:
    exp = datetime.now(timezone.utc) + delta
    return jwt.encode({"sub": sub, "scopes": SCOPES[role], "type": kind, "exp": exp}, settings.SECRET_KEY, "HS256")

def access_token(u: User) -> str: return _tok(str(u.id), u.role, "access", timedelta(minutes=settings.ACCESS_MIN))
def refresh_token(u: User) -> str: return _tok(str(u.id), u.role, "refresh", timedelta(days=settings.REFRESH_DAYS))

async def get_current_user(scopes: SecurityScopes, token: str = Depends(oauth2), db: AsyncSession = Depends(get_db)) -> User:
    err = HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid credentials", {"WWW-Authenticate": "Bearer"})
    try:
        p = jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
        if p.get("type") != "access": raise err
    except JWTError: raise err
    for s in scopes.scopes:
        if s not in p.get("scopes", []): raise HTTPException(403, f"Missing scope: {s}")
    u = (await db.execute(select(User).where(User.id == p["sub"]))).scalar_one_or_none()
    if not u or not u.active: raise err
    return u
