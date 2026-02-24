"""Client for sending audit events to api-audit service."""
import logging
from typing import Optional, Dict, Any
from uuid import UUID

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

AUDIT_TIMEOUT = 2.0  # seconds


async def send_audit_event(
    event_type: str,
    tenant_id: Optional[UUID] = None,
    user_id: Optional[UUID] = None,
    data: Optional[Dict[str, Any]] = None,
) -> bool:
    """Send an audit event to api-audit service (fire-and-forget).

    Returns True if recorded successfully, False on failure.
    Never raises - audit failures should not break main operations.
    """
    url = f"{settings.audit_service_url}/audit/events"
    payload = {
        "event_type": event_type,
        "tenant_id": str(tenant_id) if tenant_id else None,
        "user_id": str(user_id) if user_id else None,
        "data": data or {},
    }
    headers = {"X-Internal-Secret": settings.internal_api_secret}
    try:
        async with httpx.AsyncClient(timeout=AUDIT_TIMEOUT) as client:
            resp = await client.post(url, json=payload, headers=headers)
            if resp.status_code == 201:
                return True
            logger.warning("Audit API returned %s: %s", resp.status_code, resp.text)
            return False
    except Exception as e:
        logger.warning("Failed to send audit event: %s", e)
        return False
