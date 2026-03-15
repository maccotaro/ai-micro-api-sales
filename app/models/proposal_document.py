"""
Proposal Document Models
- ProposalDocument: 生成された提案書ドキュメント
- ProposalDocumentPage: ページ単位のMarkdown
- ProposalDocumentChat: ページ単位チャット + 全体チャット
"""
from datetime import datetime
from uuid import uuid4

from sqlalchemy import (
    Column, String, Text, Boolean, Integer,
    TIMESTAMP, ForeignKey, Index, CheckConstraint, UniqueConstraint
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship

from app.db.session import SalesDBBase


class ProposalDocument(SalesDBBase):
    """生成された提案書ドキュメント"""
    __tablename__ = "proposal_documents"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id = Column(UUID(as_uuid=True), nullable=False)
    user_id = Column(UUID(as_uuid=True), nullable=False)
    pipeline_run_id = Column(UUID(as_uuid=True), nullable=True)
    minute_id = Column(UUID(as_uuid=True), nullable=True)
    title = Column(String(255), nullable=False)
    story_structure = Column(JSONB, nullable=False)
    status = Column(String(20), default="draft")
    marp_theme = Column(String(50), default="default")
    created_at = Column(TIMESTAMP(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at = Column(TIMESTAMP(timezone=True), nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    pages = relationship(
        "ProposalDocumentPage",
        back_populates="document",
        cascade="all, delete-orphan",
        order_by="ProposalDocumentPage.page_number"
    )
    chats = relationship(
        "ProposalDocumentChat",
        back_populates="document",
        cascade="all, delete-orphan",
        order_by="ProposalDocumentChat.created_at"
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('draft', 'finalized', 'exported')",
            name="ck_proposal_documents_status"
        ),
        Index("idx_proposal_documents_tenant", "tenant_id", "updated_at"),
        Index("idx_proposal_documents_user", "user_id", "updated_at"),
        Index("idx_proposal_documents_pipeline_run", "pipeline_run_id"),
        Index("idx_proposal_documents_minute", "minute_id"),
    )


class ProposalDocumentPage(SalesDBBase):
    """ページ単位のMarkdown"""
    __tablename__ = "proposal_document_pages"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    document_id = Column(
        UUID(as_uuid=True),
        ForeignKey("proposal_documents.id", ondelete="CASCADE"),
        nullable=False
    )
    page_number = Column(Integer, nullable=False)
    title = Column(String(255))
    markdown_content = Column(Text, nullable=False)
    purpose = Column(Text)
    data_sources = Column(JSONB)
    generation_context = Column(JSONB)
    created_at = Column(TIMESTAMP(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at = Column(TIMESTAMP(timezone=True), nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    document = relationship("ProposalDocument", back_populates="pages")
    chats = relationship(
        "ProposalDocumentChat",
        back_populates="page",
        cascade="all, delete-orphan",
        order_by="ProposalDocumentChat.created_at"
    )

    __table_args__ = (
        UniqueConstraint("document_id", "page_number", name="uq_document_page_number"),
        Index("idx_proposal_document_pages_document", "document_id", "page_number"),
    )


class ProposalDocumentChat(SalesDBBase):
    """ページ単位チャット + 全体チャット"""
    __tablename__ = "proposal_document_chats"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    document_id = Column(
        UUID(as_uuid=True),
        ForeignKey("proposal_documents.id", ondelete="CASCADE"),
        nullable=False
    )
    page_id = Column(
        UUID(as_uuid=True),
        ForeignKey("proposal_document_pages.id", ondelete="CASCADE"),
        nullable=True  # NULLなら全体チャット
    )
    role = Column(String(20), nullable=False)
    content = Column(Text, nullable=False)
    action_type = Column(String(30))
    resulted_in_update = Column(Boolean, default=False)
    created_at = Column(TIMESTAMP(timezone=True), nullable=False, default=datetime.utcnow)

    # Relationships
    document = relationship("ProposalDocument", back_populates="chats")
    page = relationship("ProposalDocumentPage", back_populates="chats")

    __table_args__ = (
        CheckConstraint(
            "role IN ('user', 'assistant')",
            name="ck_proposal_document_chats_role"
        ),
        CheckConstraint(
            "action_type IS NULL OR action_type IN ('question', 'rewrite', 'regenerate_all')",
            name="ck_proposal_document_chats_action"
        ),
        Index("idx_proposal_document_chats_document", "document_id", "created_at"),
    )
