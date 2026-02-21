"""
Security utilities for JWT authentication
"""
import logging
from typing import Optional, List, Tuple
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
        "permissions": payload.get("permissions", []),
        "tenant_id": payload.get("tenant_id"),
        "department": payload.get("department"),
        "clearance_level": payload.get("clearance_level", "internal"),
    }


def is_super_admin(current_user: dict) -> bool:
    """Check if user has super_admin role (cross-tenant access)."""
    user_roles = current_user.get("roles", [])
    return "super_admin" in user_roles


def get_user_tenant_id(current_user: dict) -> Optional[str]:
    """Get tenant_id from current user."""
    return current_user.get("tenant_id")


def check_tenant_access(
    resource_tenant_id: Optional[str],
    current_user: dict,
    allow_none: bool = False
) -> bool:
    """
    Check if user has access to a resource based on tenant_id.

    Args:
        resource_tenant_id: The tenant_id of the resource
        current_user: Current user dict from JWT
        allow_none: If True, allow access when resource has no tenant_id (legacy data)

    Returns:
        True if access is allowed, False otherwise
    """
    if is_super_admin(current_user):
        return True

    if resource_tenant_id is None:
        return allow_none

    user_tenant_id = get_user_tenant_id(current_user)
    if user_tenant_id is None:
        return False

    return str(resource_tenant_id) == str(user_tenant_id)


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


def require_permission(resource: str, action: str):
    """Resource x action permission check using JWT permissions array."""
    def permission_checker(
        current_user: dict = Depends(get_current_user),
    ) -> dict:
        required = f"{resource}:{action}"
        user_permissions = current_user.get("permissions", [])

        resource_wildcard = f"{resource}:*"
        global_wildcard = "*:*"

        if (
            required in user_permissions
            or resource_wildcard in user_permissions
            or global_wildcard in user_permissions
        ):
            return current_user

        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Permission denied: {required}",
        )
    return permission_checker


def require_any_permission(permissions: List[Tuple[str, str]]):
    """Allow access if user has ANY of the listed (resource, action) permissions."""
    def checker(current_user: dict = Depends(get_current_user)) -> dict:
        user_perms = set(current_user.get("permissions", []))
        required = {f"{r}:{a}" for r, a in permissions}
        if user_perms & required or "*:*" in user_perms:
            return current_user
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Permission denied",
        )
    return checker
