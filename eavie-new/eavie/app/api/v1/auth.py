from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from jose import JWTError, jwt
from pydantic import BaseModel, EmailStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import settings
from app.core.security import access_token, hash_pw, refresh_token, verify_pw
from app.db.models import AuditLog, User
from app.db.session import get_db
router = APIRouter(prefix="/auth", tags=["auth"])
class Reg(BaseModel): email: EmailStr; password: str
@router.post("/register", status_code=201)
async def register(b: Reg, db: AsyncSession = Depends(get_db)):
    if len(b.password) < 10: raise HTTPException(422, "password >= 10 chars")
    if (await db.execute(select(User).where(User.email == b.email))).scalar_one_or_none(): raise HTTPException(409, "exists")
    u = User(email=b.email, password_hash=hash_pw(b.password)); db.add(u); db.add(AuditLog(action="register", detail={"email": b.email}))
    await db.commit(); return {"id": str(u.id)}
@router.post("/login")
async def login(f: OAuth2PasswordRequestForm = Depends(), db: AsyncSession = Depends(get_db)):
    u = (await db.execute(select(User).where(User.email == f.username))).scalar_one_or_none()
    if not u or not verify_pw(f.password, u.password_hash): raise HTTPException(401, "bad credentials")
    return {"access_token": access_token(u), "refresh_token": refresh_token(u), "token_type": "bearer"}
@router.post("/refresh")
async def refresh(token: str, db: AsyncSession = Depends(get_db)):
    try: p = jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
    except JWTError: raise HTTPException(401, "invalid refresh")
    if p.get("type") != "refresh": raise HTTPException(401, "invalid refresh")
    u = (await db.execute(select(User).where(User.id == p["sub"]))).scalar_one()
    return {"access_token": access_token(u), "token_type": "bearer"}
