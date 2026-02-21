"""
Graph Router

API endpoints for graph-based recommendations using Neo4j.
"""
import logging
from typing import Optional, List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.core.security import require_sales_access, get_user_tenant_id
from app.models.meeting import MeetingMinute
from app.services.graph.sales_graph_service import sales_graph_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/graph", tags=["graph"])


# Response schemas
class RelatedProduct(BaseModel):
    """Related product via REQUIRES or CROSS_SELL."""
    name: str
    reason: Optional[str] = None


class ProductRecommendation(BaseModel):
    """Product recommendation from graph."""
    product_id: Optional[str] = None
    product_name: str
    relevance_score: float = 0.0
    matched_problems: List[str] = []
    requires: List[RelatedProduct] = []
    cross_sell: List[RelatedProduct] = []


class SimilarMeeting(BaseModel):
    """Similar meeting from graph."""
    meeting_id: str
    company_name: Optional[str] = None
    similarity_score: float = 0.0
    shared_problems: List[str] = []
    shared_needs: List[str] = []


class SuccessCaseRecommendation(BaseModel):
    """Success case recommendation from graph."""
    id: UUID
    title: Optional[str] = None
    industry: Optional[str] = None
    achievement: Optional[str] = None


class GraphRecommendationsResponse(BaseModel):
    """Combined graph-based recommendations."""
    meeting_id: UUID
    products: List[ProductRecommendation] = []
    similar_meetings: List[SimilarMeeting] = []
    success_cases: List[SuccessCaseRecommendation] = []


class GraphStatsResponse(BaseModel):
    """Graph statistics for tenant."""
    stats: dict


@router.get("/health")
async def graph_health():
    """Check if the graph service is available."""
    is_connected = await sales_graph_service.ensure_connected()
    return {
        "status": "connected" if is_connected else "disconnected",
        "service": "neo4j",
    }


@router.get("/recommendations/{minute_id}", response_model=GraphRecommendationsResponse)
async def get_graph_recommendations(
    minute_id: UUID,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_sales_access),
):
    """
    Get graph-based recommendations for a meeting minute.

    Uses Neo4j graph traversal to find:
    - Products that solve the meeting's identified problems
    - Similar meetings with shared problems, needs, or industry
    - Success cases related to the meeting's context
    """
    # Tenant isolation: verify meeting belongs to user's tenant
    meeting = db.query(MeetingMinute).filter(MeetingMinute.id == minute_id).first()
    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting minute not found")

    user_tenant_id = get_user_tenant_id(current_user)
    if meeting.tenant_id and user_tenant_id and str(meeting.tenant_id) != user_tenant_id:
        raise HTTPException(
            status_code=403,
            detail="Access denied: resource belongs to different tenant"
        )

    # Use default tenant_id if not provided
    tenant_id = UUID(current_user.get("tenant_id")) if current_user.get("tenant_id") else UUID("00000000-0000-0000-0000-000000000000")

    # Ensure connection
    if not await sales_graph_service.ensure_connected():
        raise HTTPException(
            status_code=503,
            detail="Graph service is unavailable"
        )

    # Get product recommendations with REQUIRES/CROSS_SELL relations
    products = await sales_graph_service.find_products_with_relations(
        meeting_id=minute_id,
        tenant_id=tenant_id,
        limit=10,
    )

    # Get similar meetings
    similar_meetings = await sales_graph_service.find_similar_meetings(
        meeting_id=minute_id,
        tenant_id=tenant_id,
        limit=5,
    )

    # Get success cases
    success_cases = await sales_graph_service.find_success_cases_for_meeting(
        meeting_id=minute_id,
        tenant_id=tenant_id,
        limit=5,
    )

    return GraphRecommendationsResponse(
        meeting_id=minute_id,
        products=[ProductRecommendation(**p) for p in products],
        similar_meetings=[SimilarMeeting(**m) for m in similar_meetings],
        success_cases=[SuccessCaseRecommendation(**s) for s in success_cases],
    )


@router.get("/stats", response_model=GraphStatsResponse)
async def get_graph_stats(
    current_user: dict = Depends(require_sales_access),
):
    """Get graph statistics for the current tenant."""
    # Use default tenant_id if not provided
    tenant_id = UUID(current_user.get("tenant_id")) if current_user.get("tenant_id") else UUID("00000000-0000-0000-0000-000000000000")

    if not await sales_graph_service.ensure_connected():
        raise HTTPException(
            status_code=503,
            detail="Graph service is unavailable"
        )

    stats = await sales_graph_service.get_graph_stats(tenant_id)

    return GraphStatsResponse(stats=stats)


@router.delete("/meetings/{minute_id}")
async def delete_meeting_graph(
    minute_id: UUID,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_sales_access),
):
    """Delete graph data for a specific meeting."""
    # Tenant isolation: verify meeting belongs to user's tenant
    meeting = db.query(MeetingMinute).filter(MeetingMinute.id == minute_id).first()
    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting minute not found")

    user_tenant_id = get_user_tenant_id(current_user)
    if meeting.tenant_id and user_tenant_id and str(meeting.tenant_id) != user_tenant_id:
        raise HTTPException(
            status_code=403,
            detail="Access denied: resource belongs to different tenant"
        )

    tenant_id = UUID(current_user.get("tenant_id")) if current_user.get("tenant_id") else None

    if not tenant_id:
        raise HTTPException(
            status_code=400,
            detail="Tenant ID is required"
        )

    if not await sales_graph_service.ensure_connected():
        raise HTTPException(
            status_code=503,
            detail="Graph service is unavailable"
        )

    success = await sales_graph_service.delete_meeting_graph(minute_id, tenant_id)

    if not success:
        raise HTTPException(
            status_code=500,
            detail="Failed to delete meeting graph data"
        )

    return {"status": "deleted", "meeting_id": str(minute_id)}
