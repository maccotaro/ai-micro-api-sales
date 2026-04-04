"""
Internal Chat Tools Router

Internal API endpoints for cross-service tool calls (e.g., ReactAgent in api-rag).
Authenticated via X-Internal-Secret header. Tenant isolation via X-Tenant-ID header.
"""
import logging
from datetime import date
from typing import Optional, List, Dict, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from sqlalchemy import Text, cast, or_
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.models.meeting import MeetingMinute

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/meeting-minutes", tags=["internal-chat-tools"])


async def verify_internal_secret(
    x_internal_secret: str = Header(..., alias="X-Internal-Secret"),
) -> None:
    """Verify the shared secret for internal service-to-service calls."""
    if x_internal_secret != settings.internal_api_secret:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid internal API secret",
        )


def _extract_summary(parsed_json: Optional[Dict[str, Any]]) -> Optional[str]:
    """Extract summary from parsed_json analysis result."""
    if not parsed_json:
        return None
    return parsed_json.get("summary")


def _extract_action_items(parsed_json: Optional[Dict[str, Any]]) -> Optional[List[str]]:
    """Extract action items / next_actions from parsed_json analysis result."""
    if not parsed_json:
        return None
    return parsed_json.get("next_actions")


@router.get("")
def search_meeting_minutes(
    customer: Optional[str] = Query(None, description="ILIKE search on company_name"),
    date_from: Optional[date] = Query(None, description="meeting_date >= date_from (ISO date)"),
    date_to: Optional[date] = Query(None, description="meeting_date <= date_to (ISO date)"),
    keyword: Optional[str] = Query(None, description="ILIKE search in raw_text and parsed_json"),
    x_tenant_id: Optional[str] = Header(None, alias="X-Tenant-ID"),
    _: None = Depends(verify_internal_secret),
    db: Session = Depends(get_db),
):
    """Search meeting minutes for ReactAgent tool calls.

    All filters are combined with AND logic. Results ordered by meeting_date DESC.
    Maximum 10 results returned.

    Returns:
        {"results": [...], "total": <count>}
    """
    query = db.query(MeetingMinute)

    # Tenant isolation via X-Tenant-ID header
    if x_tenant_id:
        try:
            tenant_uuid = UUID(x_tenant_id)
            query = query.filter(MeetingMinute.tenant_id == tenant_uuid)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid X-Tenant-ID format",
            )

    # Customer / company name filter
    if customer:
        query = query.filter(MeetingMinute.company_name.ilike(f"%{customer}%"))

    # Date range filters
    if date_from:
        query = query.filter(MeetingMinute.meeting_date >= date_from)
    if date_to:
        query = query.filter(MeetingMinute.meeting_date <= date_to)

    # Keyword search across raw_text and parsed_json (cast JSONB to text for ILIKE)
    if keyword:
        keyword_pattern = f"%{keyword}%"
        query = query.filter(
            or_(
                MeetingMinute.raw_text.ilike(keyword_pattern),
                cast(MeetingMinute.parsed_json, Text).ilike(keyword_pattern),
            )
        )

    # Order by meeting_date DESC (newest first), with nulls last
    query = query.order_by(MeetingMinute.meeting_date.desc().nullslast())

    # Get total count before limit
    total = query.count()

    # Limit to 10 results
    minutes = query.limit(10).all()

    results = []
    for m in minutes:
        date_str = m.meeting_date.isoformat() if m.meeting_date else "N/A"
        results.append({
            "minute_id": str(m.id),
            "customer": m.company_name,
            "date": date_str,
            "summary": _extract_summary(m.parsed_json) or "未記入",
        })

    return {"results": results, "total": total}
