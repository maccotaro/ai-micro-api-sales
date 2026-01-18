"""
Search Router

API endpoints for similarity search across sales data.
"""
import logging
from typing import Optional, List
from uuid import UUID

from fastapi import APIRouter, Depends, Query, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.core.security import require_sales_access
from app.services.embedding_service import get_embedding_service, EmbeddingService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/search", tags=["search"])


# Request/Response schemas
class SearchRequest(BaseModel):
    """Search request schema."""
    query: str = Field(..., min_length=1, max_length=1000, description="Search query text")
    limit: int = Field(default=5, ge=1, le=20, description="Maximum number of results")
    threshold: float = Field(default=0.6, ge=0.0, le=1.0, description="Similarity threshold")


class MeetingSearchRequest(SearchRequest):
    """Meeting search request."""
    pass


class SuccessCaseSearchRequest(SearchRequest):
    """Success case search request."""
    industry: Optional[str] = Field(default=None, description="Filter by industry")
    area: Optional[str] = Field(default=None, description="Filter by area")


class SalesTalkSearchRequest(SearchRequest):
    """Sales talk search request."""
    issue_type: Optional[str] = Field(default=None, description="Filter by issue type")
    industry: Optional[str] = Field(default=None, description="Filter by industry")


class ProductSearchRequest(SearchRequest):
    """Product search request."""
    category: Optional[str] = Field(default=None, description="Filter by category")


class SimilarMeeting(BaseModel):
    """Similar meeting response."""
    meeting_id: UUID
    company_name: str
    industry: Optional[str]
    area: Optional[str]
    meeting_date: Optional[str]
    status: str
    content_preview: str
    similarity: float


class SimilarSuccessCase(BaseModel):
    """Similar success case response."""
    id: UUID
    title: str
    content_preview: str
    industry: Optional[str]
    area: Optional[str]
    company_size: Optional[str]
    achievement: Optional[str]
    metrics: Optional[dict]
    case_date: Optional[str]
    similarity: float


class SimilarSalesTalk(BaseModel):
    """Similar sales talk response."""
    id: UUID
    title: str
    content: str
    issue_type: Optional[str]
    industry: Optional[str]
    target_persona: Optional[str]
    effectiveness_score: Optional[float]
    usage_count: int
    tags: Optional[List[str]]
    similarity: float


class SimilarProduct(BaseModel):
    """Similar product response."""
    id: UUID
    name: str
    category: str
    base_price: Optional[float]
    price_unit: Optional[str]
    description: Optional[str]
    features: Optional[List[dict]]
    matched_content: str
    similarity: float


class SearchResponse(BaseModel):
    """Generic search response."""
    query: str
    total: int
    results: List[dict]


@router.post("/meetings", response_model=SearchResponse)
async def search_similar_meetings(
    request: MeetingSearchRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_sales_access),
    embedding_service: EmbeddingService = Depends(get_embedding_service),
):
    """
    Search for similar meeting minutes based on query text.

    This endpoint uses vector similarity search to find meeting minutes
    that are semantically similar to the provided query.
    Only returns meetings owned by the current user.
    """
    user_id = UUID(current_user["user_id"])

    results = await embedding_service.search_similar_meetings(
        db=db,
        query=request.query,
        user_id=user_id,
        limit=request.limit,
        threshold=request.threshold,
    )

    return SearchResponse(
        query=request.query,
        total=len(results),
        results=results,
    )


@router.post("/success-cases", response_model=SearchResponse)
async def search_similar_success_cases(
    request: SuccessCaseSearchRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_sales_access),
    embedding_service: EmbeddingService = Depends(get_embedding_service),
):
    """
    Search for similar success cases based on query text.

    Finds success cases that match the query semantically.
    Can optionally filter by industry and area.
    """
    results = await embedding_service.search_similar_success_cases(
        db=db,
        query=request.query,
        industry=request.industry,
        area=request.area,
        limit=request.limit,
        threshold=request.threshold,
    )

    return SearchResponse(
        query=request.query,
        total=len(results),
        results=results,
    )


@router.post("/sales-talks", response_model=SearchResponse)
async def search_similar_sales_talks(
    request: SalesTalkSearchRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_sales_access),
    embedding_service: EmbeddingService = Depends(get_embedding_service),
):
    """
    Search for similar sales talks based on query text.

    Finds sales talk scripts that match the query semantically.
    Useful for finding appropriate responses to customer concerns.
    Can optionally filter by issue type and industry.
    """
    results = await embedding_service.search_similar_sales_talks(
        db=db,
        query=request.query,
        issue_type=request.issue_type,
        industry=request.industry,
        limit=request.limit,
        threshold=request.threshold,
    )

    return SearchResponse(
        query=request.query,
        total=len(results),
        results=results,
    )


@router.post("/products", response_model=SearchResponse)
async def search_similar_products(
    request: ProductSearchRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_sales_access),
    embedding_service: EmbeddingService = Depends(get_embedding_service),
):
    """
    Search for products based on query text.

    Finds products whose descriptions match the query semantically.
    Useful for finding products that address specific customer needs.
    Can optionally filter by category.
    """
    results = await embedding_service.search_similar_products(
        db=db,
        query=request.query,
        category=request.category,
        limit=request.limit,
        threshold=request.threshold,
    )

    return SearchResponse(
        query=request.query,
        total=len(results),
        results=results,
    )


@router.get("/health")
async def search_health(
    embedding_service: EmbeddingService = Depends(get_embedding_service),
):
    """
    Check if the search service is ready.

    Returns the status of the embedding service.
    """
    is_ready = embedding_service.is_ready()
    return {
        "status": "ready" if is_ready else "initializing",
        "embedding_model": "bge-m3:567m",
        "embedding_dimension": 1024,
        "search_types": ["meetings", "success-cases", "sales-talks", "products"],
    }
