"""
Security utilities for JWT authentication
"""
import logging
from typing import Optional
from datetime import datetime

import httpx
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt, JWTError, jwk
from jose.constants import ALGORITHMS

from app.core.config import settings

logger = logging.getLogger(__name__)

security = HTTPBearer()

# Cache for JWKS
_jwks_cache: Optional[dict] = None
_jwks_cache_time: Optional[datetime] = None
JWKS_CACHE_DURATION = 3600  # 1 hour


async def get_jwks() -> dict:
    """Fetch JWKS from auth service with caching."""
    global _jwks_cache, _jwks_cache_time

    now = datetime.utcnow()
    if _jwks_cache and _jwks_cache_time:
        cache_age = (now - _jwks_cache_time).total_seconds()
        if cache_age < JWKS_CACHE_DURATION:
            return _jwks_cache

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(settings.jwks_url, timeout=10.0)
            response.raise_for_status()
            _jwks_cache = response.json()
            _jwks_cache_time = now
            logger.debug("JWKS cache refreshed")
            return _jwks_cache
    except Exception as e:
        logger.error(f"Failed to fetch JWKS: {e}")
        if _jwks_cache:
            logger.warning("Using stale JWKS cache")
            return _jwks_cache
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication service unavailable"
        )


async def verify_token(token: str) -> dict:
    """Verify JWT token using JWKS."""
    try:
        # Get unverified header to find the key ID
        unverified_header = jwt.get_unverified_header(token)
        kid = unverified_header.get("kid")

        if not kid:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token missing key ID"
            )

        # Get JWKS and find matching key
        jwks_data = await get_jwks()
        rsa_key = None
        for key in jwks_data.get("keys", []):
            if key.get("kid") == kid:
                rsa_key = key
                break

        if not rsa_key:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Public key not found"
            )

        # Verify and decode token
        public_key = jwk.construct(rsa_key)
        payload = jwt.decode(
            token,
            public_key,
            algorithms=[ALGORITHMS.RS256],
            audience=settings.jwt_audience,
            issuer=settings.jwt_issuer,
        )
        return payload

    except JWTError as e:
        logger.warning(f"JWT verification failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token"
        )


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> dict:
    """Get current user from JWT token."""
    token = credentials.credentials
    payload = await verify_token(token)

    return {
        "user_id": payload.get("sub"),
        "email": payload.get("email"),
        "roles": payload.get("roles", []),
        "tenant_id": payload.get("tenant_id"),
        "department": payload.get("department"),
        "clearance_level": payload.get("clearance_level", "internal"),
    }


async def require_sales_access(current_user: dict = Depends(get_current_user)) -> dict:
    """Require user to have sales access (any authenticated user)."""
    if not current_user.get("user_id"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required"
        )
    return current_user


async def require_admin(current_user: dict = Depends(get_current_user)) -> dict:
    """Require admin or super_admin role."""
    roles = current_user.get("roles", [])
    if "admin" not in roles and "super_admin" not in roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )
    return current_user
