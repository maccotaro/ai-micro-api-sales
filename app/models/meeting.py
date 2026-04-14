"""
Meeting Minutes and Proposal History Models
"""
from datetime import datetime, date
from uuid import uuid4

from sqlalchemy import (
    Column, String, Text, Boolean, Integer,
    TIMESTAMP, DATE, ForeignKey, Index, CheckConstraint
)
from sqlalchemy.dialects.postgresql import UUID, JSONB, ARRAY
from sqlalchemy.orm import relationship

from app.db.session import SalesDBBase


class MeetingMinute(SalesDBBase):
    """議事録管理"""
    __tablename__ = "meeting_minutes"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    company_name = Column(String(255), nullable=False)
    company_id = Column(UUID(as_uuid=True))
    raw_text = Column(Text, nullable=False)
    parsed_json = Column(JSONB)
    industry = Column(String(100))
    area = Column(String(100))
    meeting_date = Column(DATE)
    attendees = Column(JSONB, default=list)
    next_action_date = Column(DATE)
    status = Column(String(50), default="draft")
    entity_data = Column(JSONB, nullable=True)
    entity_extraction_status = Column(String(50), nullable=True)
    # STT integration columns
    stt_job_id = Column(UUID(as_uuid=True), nullable=True)
    corrected_text = Column(Text, nullable=True)
    final_text = Column(Text, nullable=True)
    minutes_status = Column(String(20), default="manual")
    version = Column(Integer, default=1)
    tenant_id = Column(UUID(as_uuid=True), nullable=True)
    created_by = Column(UUID(as_uuid=True), nullable=False)
    created_at = Column(TIMESTAMP(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at = Column(TIMESTAMP(timezone=True), nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    proposals = relationship("ProposalHistory", back_populates="meeting_minute", cascade="all, delete-orphan")
    versions = relationship("MeetingMinuteVersion", back_populates="meeting_minute", cascade="all, delete-orphan")

    __table_args__ = (
        CheckConstraint(
            "status IN ('draft', 'analyzed', 'proposed', 'closed')",
            name="ck_meeting_minutes_status"
        ),
        CheckConstraint(
            "minutes_status IN ('manual', 'raw', 'corrected', 'reviewed', 'finalized')",
            name="ck_meeting_minutes_minutes_status"
        ),
        Index("idx_meeting_minutes_company_id", "company_id"),
        Index("idx_meeting_minutes_company_name", "company_name"),
        Index("idx_meeting_minutes_created_by", "created_by"),
        Index("idx_meeting_minutes_meeting_date", "meeting_date"),
        Index("idx_meeting_minutes_status", "status"),
        Index("idx_meeting_minutes_stt_job_id", "stt_job_id"),
    )


class MeetingMinuteVersion(SalesDBBase):
    """議事録バージョン管理"""
    __tablename__ = "meeting_minutes_versions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    minutes_id = Column(
        UUID(as_uuid=True),
        ForeignKey("meeting_minutes.id", ondelete="CASCADE"),
        nullable=False
    )
    version = Column(Integer, nullable=False)
    status = Column(String(20), nullable=False)
    text = Column(Text, nullable=False)
    changed_by = Column(UUID(as_uuid=True), nullable=True)
    created_at = Column(TIMESTAMP(timezone=True), nullable=False, default=datetime.utcnow)

    # Relationships
    meeting_minute = relationship("MeetingMinute", back_populates="versions")

    __table_args__ = (
        Index("idx_meeting_minutes_versions_minutes_id", "minutes_id"),
        Index("idx_meeting_minutes_versions_version", "minutes_id", "version"),
    )


class ProposalHistory(SalesDBBase):
    """提案履歴"""
    __tablename__ = "proposal_history"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    meeting_minute_id = Column(
        UUID(as_uuid=True),
        ForeignKey("meeting_minutes.id", ondelete="CASCADE"),
        nullable=False
    )
    proposal_json = Column(JSONB, nullable=False)
    recommended_products = Column(ARRAY(UUID(as_uuid=True)), default=list)
    simulation_results = Column(JSONB)
    feedback = Column(String(50))
    feedback_comment = Column(Text)
    tenant_id = Column(UUID(as_uuid=True), nullable=True)
    created_by = Column(UUID(as_uuid=True), nullable=False)
    created_at = Column(TIMESTAMP(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at = Column(TIMESTAMP(timezone=True), nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    meeting_minute = relationship("MeetingMinute", back_populates="proposals")

    __table_args__ = (
        CheckConstraint(
            "feedback IS NULL OR feedback IN ('accepted', 'rejected', 'modified', 'pending')",
            name="ck_proposal_history_feedback"
        ),
        Index("idx_proposal_history_minute_id", "meeting_minute_id"),
        Index("idx_proposal_history_feedback", "feedback"),
        Index("idx_proposal_history_created_by", "created_by"),
    )
