"""
Gibson API dependencies — request-scoped resources.
Store context extracted from JWT on every request.
"""

from fastapi import Depends, HTTPException, Header
from typing import Optional
from jose import jwt, JWTError

from api.config import settings


async def get_store_id(x_store_id: Optional[str] = Header(None)) -> str:
    """
    Extract store context from request header.
    Every Stock Item query MUST include store_id.
    In production, this comes from the JWT claim.
    For now, accept it as a header with fallback to DL.
    """
    if x_store_id:
        return x_store_id
    return settings.store_dl_id


async def get_employee_id(x_employee_id: Optional[str] = Header(None)) -> Optional[str]:
    """Extract employee context from request header."""
    return x_employee_id


async def verify_token(authorization: Optional[str] = Header(None)) -> dict:
    """
    Verify JWT token and extract claims.
    Returns decoded payload with store_id and user_id.
    Skips verification in development when no JWT_SECRET is set.
    """
    if not settings.jwt_secret:
        # Development mode — return default claims
        return {
            "user_id": "dev-user",
            "store_id": settings.store_dl_id,
            "role": "owner",
        }

    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid authorization header")

    token = authorization.replace("Bearer ", "")
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
        return payload
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")
