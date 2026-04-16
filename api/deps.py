# api/deps.py
from fastapi import Header, HTTPException
from core.config import settings


async def verify_token(authorization: str = Header(...)):
    if not settings.internal_secret:
        return
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or token != settings.internal_secret:
        raise HTTPException(status_code=401, detail="Unauthorized")