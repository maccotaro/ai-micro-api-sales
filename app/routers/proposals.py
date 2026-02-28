"""
Proposals Router

API endpoints for managing and generating sales proposals.
Tenant isolation: inherits tenant_id from parent meeting minute.
"""
import logging
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.core.security import (
    require_sales_access,
    is_super_admin,
    get_user_tenant_id,
    check_tenant_access,
)
from app.models.meeting import MeetingMinute, ProposalHistory
from app.schemas.meeting import (
    ProposalResponse,
    ProposalFeedback,
    ProposalListResponse,
    MeetingMinuteAnalysis,
    ExtractedIssue,
    ExtractedNeed,
)
from app.services.proposal_service import ProposalService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/proposals", tags=["proposals"])


DEFAULT_TENANT_ID = "00000000-0000-0000-0000-000000000000"


def _build_proposal_tenant_query(db: Session, current_user: dict):
    """Build a base query with tenant isolation for proposals."""
    query = db.query(ProposalHistory)

    user_tenant_id = get_user_tenant_id(current_user)

    if is_super_admin(current_user):
        if user_tenant_id and user_tenant_id != DEFAULT_TENANT_ID:
            query = query.filter(ProposalHistory.tenant_id == user_tenant_id)
        return query

    user_id = UUID(current_user["user_id"])

    if user_tenant_id:
        query = query.filter(ProposalHistory.tenant_id == user_tenant_id)
    else:
        query = query.filter(ProposalHistory.created_by == user_id)

    return query


def _get_proposal_with_access(
    db: Session, proposal_id: UUID, current_user: dict
) -> ProposalHistory:
    """Get a proposal with tenant access check."""
    proposal = db.query(ProposalHistory).filter(ProposalHistory.id == proposal_id).first()

    if not proposal:
        raise HTTPException(status_code=404, detail="Proposal not found")

    if not check_tenant_access(
        str(proposal.tenant_id) if proposal.tenant_id else None,
        current_user,
        allow_none=False,
    ):
        user_id = UUID(current_user["user_id"])
        if proposal.tenant_id is None and proposal.created_by == user_id:
            return proposal
        raise HTTPException(status_code=403, detail="Access denied: resource belongs to different tenant")

    return proposal


@router.get("", response_model=ProposalListResponse)
async def list_proposals(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    meeting_minute_id: Optional[UUID] = None,
    feedback: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_sales_access),
):
    """
    List proposals with pagination and filtering.
    Tenant-isolated: returns only current tenant's proposals.
    """
    query = _build_proposal_tenant_query(db, current_user)

    if meeting_minute_id:
        query = query.filter(ProposalHistory.meeting_minute_id == meeting_minute_id)
    if feedback:
        query = query.filter(ProposalHistory.feedback == feedback)

    total = query.count()
    offset = (page - 1) * page_size
    items = query.order_by(ProposalHistory.created_at.desc()).offset(offset).limit(page_size).all()

    return ProposalListResponse(
        items=[ProposalResponse.model_validate(item) for item in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{proposal_id}", response_model=ProposalResponse)
async def get_proposal(
    proposal_id: UUID,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_sales_access),
):
    """Get a specific proposal by ID."""
    proposal = _get_proposal_with_access(db, proposal_id, current_user)
    return ProposalResponse.model_validate(proposal)


@router.post("/generate/{minute_id}", response_model=ProposalResponse, status_code=201)
async def generate_proposal(
    minute_id: UUID,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_sales_access),
):
    """
    Generate a new proposal based on a meeting minute.
    Inherits tenant_id from parent meeting minute.
    """
    user_id = UUID(current_user["user_id"])

    # Get meeting minute with tenant check
    minute = db.query(MeetingMinute).filter(MeetingMinute.id == minute_id).first()
    if not minute:
        raise HTTPException(status_code=404, detail="Meeting minute not found")

    # Tenant access check on parent meeting minute
    if not check_tenant_access(
        str(minute.tenant_id) if minute.tenant_id else None,
        current_user,
        allow_none=False,
    ):
        if not (minute.tenant_id is None and minute.created_by == user_id):
            raise HTTPException(status_code=403, detail="Access denied: resource belongs to different tenant")

    if not minute.parsed_json:
        raise HTTPException(
            status_code=400,
            detail="Meeting minute must be analyzed first. Call POST /meeting-minutes/{id}/analyze"
        )

    # Build analysis from parsed_json
    analysis = MeetingMinuteAnalysis(
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

    # Generate proposal - inherits tenant_id from parent minute
    proposal_service = ProposalService()
    proposal = await proposal_service.generate_proposal(
        minute,
        analysis,
        db,
        user_id,
    )

    # Set tenant_id from parent meeting minute
    proposal.tenant_id = minute.tenant_id
    db.commit()
    db.refresh(proposal)

    logger.info(f"Generated proposal: {proposal.id} for meeting {minute_id}")
    return ProposalResponse.model_validate(proposal)


@router.put("/{proposal_id}/feedback", response_model=ProposalResponse)
async def update_proposal_feedback(
    proposal_id: UUID,
    feedback_data: ProposalFeedback,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_sales_access),
):
    """Update feedback for a proposal."""
    proposal = _get_proposal_with_access(db, proposal_id, current_user)

    proposal.feedback = feedback_data.feedback
    proposal.feedback_comment = feedback_data.feedback_comment
    db.commit()
    db.refresh(proposal)

    # Update meeting status if accepted
    if feedback_data.feedback == "accepted":
        minute = db.query(MeetingMinute).filter(
            MeetingMinute.id == proposal.meeting_minute_id
        ).first()
        if minute:
            minute.status = "closed"
            db.commit()

    logger.info(f"Updated feedback for proposal: {proposal_id} to {feedback_data.feedback}")
    return ProposalResponse.model_validate(proposal)


@router.delete("/{proposal_id}", status_code=204)
async def delete_proposal(
    proposal_id: UUID,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_sales_access),
):
    """Delete a proposal."""
    proposal = _get_proposal_with_access(db, proposal_id, current_user)

    db.delete(proposal)
    db.commit()

    logger.info(f"Deleted proposal: {proposal_id}")
    return None
