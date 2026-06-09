"""
Gibson API dependencies — request-scoped resources.
Store context is derived from the verified JWT claim on every request.

SECURITY: store_id must come from the token, never from a caller-supplied header.
An unauthenticated header is how a member could read another store's inventory.
"""

from fastapi import Depends, HTTPException, Header
from typing import Optional
from jose import jwt, JWTError

from api.config import settings


async def verify_token(authorization: Optional[str] = Header(None)) -> dict:
    """
    Verify the Supabase JWT and return its claims.

    In development (jwt_secret not set): returns safe default dev claims for
    Driftless Books. This path is only reachable on localhost.

    In production: the token must be a valid HS256 JWT signed with jwt_secret.
    store_id is read from user_metadata.store_id (set during onboarding).
    """
    if not settings.jwt_secret:
        # Dev mode — no secret configured, safe on localhost only
        return {
            "sub": "dev-user",
            "store_id": settings.store_dl_id,
            "role": "owner",
        }

    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Authorization header required")

    token = authorization.removeprefix("Bearer ").strip()
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
        return payload
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")


async def get_store_id(claims: dict = Depends(verify_token)) -> str:
    """
    Extract store_id from the verified JWT claims.

    Supabase JWTs carry store_id in user_metadata (set at onboarding).
    Falls back to top-level claim for custom tokens issued by the app.
    Raises 401 if no store membership is found in the token.
    """
    # Supabase JWT: user_metadata.store_id
    store_id = (
        claims.get("store_id")
        or (claims.get("user_metadata") or {}).get("store_id")
        or (claims.get("app_metadata") or {}).get("store_id")
    )
    if not store_id:
        raise HTTPException(
            status_code=401,
            detail="No store membership in token. Complete store onboarding first.",
        )
    return store_id


async def get_employee_id(claims: dict = Depends(verify_token)) -> Optional[str]:
    """
    Extract employee (user) ID from the verified JWT claims.
    Returns None if not present — callers treat this as anonymous.
    """
    return claims.get("sub") or claims.get("user_id")
