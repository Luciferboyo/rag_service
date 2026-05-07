# api/deps.py
from fastapi import Header, HTTPException
from core.config import settings


async def verify_token(authorization: str | None = Header(None)):
    if not settings.internal_secret:
        return
    if not authorization:
        raise HTTPException(status_code=401, detail="Unauthorized")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or token != settings.internal_secret:
        raise HTTPException(status_code=401, detail="Unauthorized")