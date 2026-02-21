"""
Meeting Minutes Router

API endpoints for managing and analyzing meeting minutes.
Tenant isolation: filters by tenant_id from JWT. super_admin sees all tenants.
"""
import logging
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.core.security import (
    require_sales_access,
    is_super_admin,
    get_user_tenant_id,
    check_tenant_access,
)
from app.models.meeting import MeetingMinute
from app.schemas.meeting import (
    MeetingMinuteCreate,
    MeetingMinuteUpdate,
    MeetingMinuteResponse,
    MeetingMinuteListResponse,
    MeetingMinuteAnalysis,
)
from app.services.analysis_service import AnalysisService
from app.services.embedding_service import get_embedding_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/meeting-minutes", tags=["meeting-minutes"])


def _build_tenant_query(db: Session, current_user: dict):
    """Build a base query with tenant isolation for meeting minutes."""
    query = db.query(MeetingMinute)

    if is_super_admin(current_user):
        return query

    user_tenant_id = get_user_tenant_id(current_user)
    user_id = UUID(current_user["user_id"])

    if user_tenant_id:
        # Tenant user: see own tenant's data
        query = query.filter(MeetingMinute.tenant_id == user_tenant_id)
    else:
        # No tenant: fallback to created_by only
        query = query.filter(MeetingMinute.created_by == user_id)

    return query


def _get_minute_with_access(
    db: Session, minute_id: UUID, current_user: dict
) -> MeetingMinute:
    """Get a meeting minute with tenant access check."""
    minute = db.query(MeetingMinute).filter(MeetingMinute.id == minute_id).first()

    if not minute:
        raise HTTPException(status_code=404, detail="Meeting minute not found")

    # Tenant access check
    if not check_tenant_access(
        str(minute.tenant_id) if minute.tenant_id else None,
        current_user,
        allow_none=False,
    ):
        # For legacy data (tenant_id=NULL), allow if created_by matches
        user_id = UUID(current_user["user_id"])
        if minute.tenant_id is None and minute.created_by == user_id:
            return minute
        raise HTTPException(status_code=403, detail="Access denied: resource belongs to different tenant")

    return minute


@router.get("", response_model=MeetingMinuteListResponse)
async def list_meeting_minutes(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: Optional[str] = None,
    company_name: Optional[str] = None,
    industry: Optional[str] = None,
    area: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_sales_access),
):
    """
    List meeting minutes with pagination and filtering.
    Tenant-isolated: returns only current tenant's data.
    super_admin sees all tenants.
    """
    query = _build_tenant_query(db, current_user)

    if status:
        query = query.filter(MeetingMinute.status == status)
    if company_name:
        query = query.filter(MeetingMinute.company_name.ilike(f"%{company_name}%"))
    if industry:
        query = query.filter(MeetingMinute.industry == industry)
    if area:
        query = query.filter(MeetingMinute.area == area)

    total = query.count()
    offset = (page - 1) * page_size
    items = query.order_by(MeetingMinute.created_at.desc()).offset(offset).limit(page_size).all()

    return MeetingMinuteListResponse(
        items=[MeetingMinuteResponse.model_validate(item) for item in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{minute_id}", response_model=MeetingMinuteResponse)
async def get_meeting_minute(
    minute_id: UUID,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_sales_access),
):
    """Get a specific meeting minute by ID."""
    minute = _get_minute_with_access(db, minute_id, current_user)
    return MeetingMinuteResponse.model_validate(minute)


@router.post("", response_model=MeetingMinuteResponse, status_code=201)
async def create_meeting_minute(
    data: MeetingMinuteCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_sales_access),
):
    """Create a new meeting minute. Sets tenant_id from JWT automatically."""
    user_id = UUID(current_user["user_id"])
    user_tenant_id = get_user_tenant_id(current_user)

    minute = MeetingMinute(
        **data.model_dump(),
        created_by=user_id,
        tenant_id=user_tenant_id,
        status="draft",
    )
    db.add(minute)
    db.commit()
    db.refresh(minute)

    logger.info(f"Created meeting minute: {minute.id} for company {minute.company_name}")
    return MeetingMinuteResponse.model_validate(minute)


@router.put("/{minute_id}", response_model=MeetingMinuteResponse)
async def update_meeting_minute(
    minute_id: UUID,
    data: MeetingMinuteUpdate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_sales_access),
):
    """Update a meeting minute."""
    minute = _get_minute_with_access(db, minute_id, current_user)

    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(minute, field, value)

    db.commit()
    db.refresh(minute)

    logger.info(f"Updated meeting minute: {minute.id}")
    return MeetingMinuteResponse.model_validate(minute)


@router.delete("/{minute_id}", status_code=204)
async def delete_meeting_minute(
    minute_id: UUID,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_sales_access),
):
    """Delete a meeting minute and all related proposals."""
    minute = _get_minute_with_access(db, minute_id, current_user)

    db.delete(minute)
    db.commit()

    logger.info(f"Deleted meeting minute: {minute_id}")
    return None


@router.post("/{minute_id}/analyze", response_model=MeetingMinuteAnalysis)
async def analyze_meeting_minute(
    minute_id: UUID,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_sales_access),
):
    """
    Analyze a meeting minute using AI.

    This endpoint uses LLM to extract:
    - Key issues and challenges
    - Customer needs
    - Keywords
    - Summary
    - Next actions

    Analysis results are also stored in Neo4j graph for recommendations.
    Embeddings are generated and stored for vector similarity search.
    """
    minute = _get_minute_with_access(db, minute_id, current_user)
    user_id = UUID(current_user["user_id"])
    tenant_id = UUID(current_user.get("tenant_id")) if current_user.get("tenant_id") else None

    if not minute.raw_text:
        raise HTTPException(status_code=400, detail="Meeting minute has no text content")

    analysis_service = AnalysisService()
    analysis = await analysis_service.analyze_meeting(
        meeting=minute,
        db=db,
        tenant_id=tenant_id,
        store_in_graph=True,
    )

    # Generate and store embedding for vector similarity search
    try:
        embedding_service = await get_embedding_service()
        await embedding_service.store_meeting_embedding(
            db=db,
            meeting_id=minute.id,
            text_content=minute.raw_text,
            metadata={
                "company_name": minute.company_name,
                "industry": minute.industry,
                "area": minute.area,
                "user_id": str(user_id),
            }
        )
        logger.info(f"Stored embedding for meeting {minute.id}")
    except Exception as e:
        logger.warning(f"Failed to store embedding for meeting {minute.id}: {e}")
        # Don't fail the analysis if embedding fails

    return analysis


@router.get("/{minute_id}/analysis", response_model=MeetingMinuteAnalysis)
async def get_meeting_analysis(
    minute_id: UUID,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_sales_access),
):
    """Get the existing analysis for a meeting minute."""
    minute = _get_minute_with_access(db, minute_id, current_user)

    if not minute.parsed_json:
        raise HTTPException(status_code=404, detail="Meeting minute has not been analyzed")

    from datetime import datetime
    from app.schemas.meeting import ExtractedIssue, ExtractedNeed

    return MeetingMinuteAnalysis(
        meeting_minute_id=minute.id,
        company_name=minute.company_name,
        industry=minute.industry,
        area=minute.area,
        issues=[ExtractedIssue(**i) for i in minute.parsed_json.get("issues", [])],
        needs=[ExtractedNeed(**n) for n in minute.parsed_json.get("needs", [])],
        keywords=minute.parsed_json.get("keywords", []),
        summary=minute.parsed_json.get("summary", ""),
        company_size_estimate=minute.parsed_json.get("company_size_estimate"),
        decision_maker_present=minute.parsed_json.get("decision_maker_present", False),
        next_actions=minute.parsed_json.get("next_actions", []),
        follow_up_date=minute.next_action_date,
        confidence_score=minute.parsed_json.get("confidence_score", 0.5),
        analysis_timestamp=minute.updated_at,
    )


@router.post("/embeddings/generate-all")
async def generate_all_embeddings(
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_sales_access),
):
    """
    Generate embeddings for all analyzed meeting minutes that don't have embeddings yet.

    This is useful for backfilling embeddings for existing data.
    Respects tenant isolation.
    """
    from sqlalchemy import text as sql_text

    query = _build_tenant_query(db, current_user).filter(
        MeetingMinute.raw_text.isnot(None),
        MeetingMinute.status.in_(["analyzed", "proposed", "closed"]),
    )

    # Exclude meetings that already have embeddings
    existing_embeddings = db.execute(
        sql_text("SELECT meeting_minute_id FROM meeting_minute_embeddings")
    ).fetchall()
    existing_ids = {row[0] for row in existing_embeddings}

    meetings = [m for m in query.all() if m.id not in existing_ids]

    if not meetings:
        return {"message": "No meetings to process", "processed": 0, "failed": 0}

    embedding_service = await get_embedding_service()
    user_id = UUID(current_user["user_id"])

    processed = 0
    failed = 0

    for minute in meetings:
        try:
            success = await embedding_service.store_meeting_embedding(
                db=db,
                meeting_id=minute.id,
                text_content=minute.raw_text,
                metadata={
                    "company_name": minute.company_name,
                    "industry": minute.industry,
                    "area": minute.area,
                    "user_id": str(user_id),
                }
            )
            if success:
                processed += 1
                logger.info(f"Generated embedding for meeting {minute.id}")
            else:
                failed += 1
                logger.warning(f"Failed to generate embedding for meeting {minute.id}")
        except Exception as e:
            failed += 1
            logger.error(f"Error generating embedding for meeting {minute.id}: {e}")

    return {
        "message": f"Embedding generation complete",
        "processed": processed,
        "failed": failed,
        "total_found": len(meetings),
    }
