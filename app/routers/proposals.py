"""
Proposals Router

API endpoints for managing and generating sales proposals.
"""
import logging
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.core.security import require_sales_access
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

    - **meeting_minute_id**: Filter by meeting minute
    - **feedback**: Filter by feedback status (accepted, rejected, modified, pending)
    """
    user_id = UUID(current_user["user_id"])
    query = db.query(ProposalHistory).filter(ProposalHistory.created_by == user_id)

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
    user_id = UUID(current_user["user_id"])
    proposal = db.query(ProposalHistory).filter(
        ProposalHistory.id == proposal_id,
        ProposalHistory.created_by == user_id,
    ).first()

    if not proposal:
        raise HTTPException(status_code=404, detail="Proposal not found")

    return ProposalResponse.model_validate(proposal)


@router.post("/generate/{minute_id}", response_model=ProposalResponse, status_code=201)
async def generate_proposal(
    minute_id: UUID,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_sales_access),
):
    """
    Generate a new proposal based on a meeting minute.

    The meeting minute must be analyzed first.
    This endpoint uses AI to:
    - Match customer needs with products
    - Generate talking points
    - Create objection handlers
    """
    user_id = UUID(current_user["user_id"])

    # Get meeting minute
    minute = db.query(MeetingMinute).filter(
        MeetingMinute.id == minute_id,
        MeetingMinute.created_by == user_id,
    ).first()

    if not minute:
        raise HTTPException(status_code=404, detail="Meeting minute not found")

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

    # Generate proposal
    proposal_service = ProposalService()
    proposal = await proposal_service.generate_proposal(
        minute,
        analysis,
        db,
        user_id,
    )

    logger.info(f"Generated proposal: {proposal.id} for meeting {minute_id}")
    return ProposalResponse.model_validate(proposal)


@router.put("/{proposal_id}/feedback", response_model=ProposalResponse)
async def update_proposal_feedback(
    proposal_id: UUID,
    feedback_data: ProposalFeedback,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_sales_access),
):
    """
    Update feedback for a proposal.

    - **feedback**: Status (accepted, rejected, modified, pending)
    - **feedback_comment**: Optional comment about the feedback
    """
    user_id = UUID(current_user["user_id"])
    proposal = db.query(ProposalHistory).filter(
        ProposalHistory.id == proposal_id,
        ProposalHistory.created_by == user_id,
    ).first()

    if not proposal:
        raise HTTPException(status_code=404, detail="Proposal not found")

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
    user_id = UUID(current_user["user_id"])
    proposal = db.query(ProposalHistory).filter(
        ProposalHistory.id == proposal_id,
        ProposalHistory.created_by == user_id,
    ).first()

    if not proposal:
        raise HTTPException(status_code=404, detail="Proposal not found")

    db.delete(proposal)
    db.commit()

    logger.info(f"Deleted proposal: {proposal_id}")
    return None
