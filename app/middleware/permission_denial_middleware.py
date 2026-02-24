"""Middleware to capture HTTP 403 responses and send permission denial audit events."""
import asyncio
import json
import logging
import re
from typing import Optional

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

logger = logging.getLogger(__name__)

SERVICE_NAME = "api-sales"

_PERMISSION_RE = re.compile(r"(?:permissions?|permission)[:\s]+(\w+:\w+)", re.IGNORECASE)


def _extract_permission(body_text: str) -> Optional[str]:
    """Try to extract the required permission from a 403 response body."""
    try:
        data = json.loads(body_text)
        detail = data.get("detail", "")
        if isinstance(detail, str):
            match = _PERMISSION_RE.search(detail)
            if match:
                return match.group(1)
    except (json.JSONDecodeError, AttributeError):
        pass
    return None


def _get_client_ip(request: Request) -> Optional[str]:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host
    return None


class PermissionDenialMiddleware(BaseHTTPMiddleware):
    """Capture 403 responses and send audit events to api-audit."""

    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)

        if response.status_code != 403:
            return response

        body_bytes = b""
        async for chunk in response.body_iterator:
            if isinstance(chunk, str):
                body_bytes += chunk.encode("utf-8")
            else:
                body_bytes += chunk

        permission = _extract_permission(body_bytes.decode("utf-8", errors="replace"))

        new_response = Response(
            content=body_bytes,
            status_code=response.status_code,
            headers=dict(response.headers),
            media_type=response.media_type,
        )

        asyncio.create_task(_send_denial_event(request, permission))

        return new_response


async def _send_denial_event(request: Request, permission: Optional[str]) -> None:
    """Send permission denial audit event. Never raises."""
    try:
        from app.services.audit_client import send_audit_event

        tenant_id = getattr(request.state, "tenant_id", None)
        user_id = None
        current_user = getattr(request.state, "current_user", None)
        if current_user and isinstance(current_user, dict):
            user_id = current_user.get("sub") or current_user.get("user_id")

        await send_audit_event(
            event_type="permission_denial",
            tenant_id=tenant_id,
            user_id=user_id,
            data={
                "service_name": SERVICE_NAME,
                "method": request.method,
                "path": request.url.path,
                "permission": permission,
                "ip_address": _get_client_ip(request),
                "user_agent": request.headers.get("User-Agent"),
            },
        )
    except Exception as e:
        logger.warning("Failed to send permission denial audit: %s", e)
