"""Router for proposal document CRUD, chat, and export endpoints."""
import logging
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session, joinedload

from app.core.security import require_sales_access
from app.db.session import get_db
from app.utils.markdown_table_fixer import fix_markdown_tables
from app.models.proposal_document import (
    ProposalDocument, ProposalDocumentPage, ProposalDocumentChat,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/proposal-documents", tags=["proposal-documents"])

DEFAULT_TENANT_ID = UUID("00000000-0000-0000-0000-000000000000")


# ============================================================
# Schemas
# ============================================================

class PageResponse(BaseModel):
    id: str
    page_number: int
    title: Optional[str] = None
    markdown_content: str
    purpose: Optional[str] = None

    class Config:
        from_attributes = True


class DocumentListItem(BaseModel):
    id: str
    title: str
    status: str
    created_at: str
    updated_at: str
    page_count: int = 0


class DocumentDetailResponse(BaseModel):
    id: str
    title: str
    status: str
    marp_theme: str
    story_structure: dict
    pipeline_run_id: Optional[str] = None
    minute_id: Optional[str] = None
    created_at: str
    updated_at: str
    pages: list[PageResponse]


class ChatMessageRequest(BaseModel):
    page_id: Optional[str] = None
    content: str
    action_type: str = Field(..., pattern=r"^(question|rewrite|regenerate_all)$")


class ChatMessageResponse(BaseModel):
    id: str
    page_id: Optional[str] = None
    role: str
    content: str
    action_type: Optional[str] = None
    resulted_in_update: bool = False
    created_at: str


class ExportRequest(BaseModel):
    format: str = Field(..., pattern=r"^(pptx|pdf|html)$")


# ============================================================
# Helpers
# ============================================================

def _extract_ids(current_user: dict) -> tuple[UUID, UUID]:
    tenant_id_str = current_user.get("tenant_id")
    tenant_id = UUID(tenant_id_str) if tenant_id_str else DEFAULT_TENANT_ID
    user_id = UUID(current_user["user_id"])
    return tenant_id, user_id


# ============================================================
# Document CRUD
# ============================================================

@router.get("")
async def list_documents(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: dict = Depends(require_sales_access),
    db: Session = Depends(get_db),
):
    """List proposal documents for the current tenant."""
    tenant_id, _ = _extract_ids(current_user)

    query = db.query(ProposalDocument).filter(
        ProposalDocument.tenant_id == tenant_id,
    ).order_by(ProposalDocument.updated_at.desc())

    total = query.count()
    docs = query.offset((page - 1) * page_size).limit(page_size).all()

    items = []
    for doc in docs:
        page_count = db.query(ProposalDocumentPage).filter(
            ProposalDocumentPage.document_id == doc.id,
        ).count()
        items.append(DocumentListItem(
            id=str(doc.id),
            title=doc.title,
            status=doc.status,
            created_at=doc.created_at.isoformat(),
            updated_at=doc.updated_at.isoformat(),
            page_count=page_count,
        ))

    return {
        "items": [item.model_dump() for item in items],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/{document_id}")
async def get_document(
    document_id: UUID,
    current_user: dict = Depends(require_sales_access),
    db: Session = Depends(get_db),
):
    """Get proposal document detail with all pages."""
    tenant_id, _ = _extract_ids(current_user)

    doc = db.query(ProposalDocument).options(
        joinedload(ProposalDocument.pages),
    ).filter(
        ProposalDocument.id == document_id,
        ProposalDocument.tenant_id == tenant_id,
    ).first()

    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    pages = [
        PageResponse(
            id=str(p.id),
            page_number=p.page_number,
            title=p.title,
            markdown_content=fix_markdown_tables(p.markdown_content or ""),
            purpose=p.purpose,
        )
        for p in sorted(doc.pages, key=lambda p: p.page_number)
    ]

    return DocumentDetailResponse(
        id=str(doc.id),
        title=doc.title,
        status=doc.status,
        marp_theme=doc.marp_theme or "default",
        story_structure=doc.story_structure or {},
        pipeline_run_id=str(doc.pipeline_run_id) if doc.pipeline_run_id else None,
        minute_id=str(doc.minute_id) if doc.minute_id else None,
        created_at=doc.created_at.isoformat(),
        updated_at=doc.updated_at.isoformat(),
        pages=pages,
    ).model_dump()


@router.delete("/{document_id}", status_code=204)
async def delete_document(
    document_id: UUID,
    current_user: dict = Depends(require_sales_access),
    db: Session = Depends(get_db),
):
    """Delete a proposal document (cascades to pages and chats)."""
    tenant_id, _ = _extract_ids(current_user)

    doc = db.query(ProposalDocument).filter(
        ProposalDocument.id == document_id,
        ProposalDocument.tenant_id == tenant_id,
    ).first()

    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    db.delete(doc)
    db.commit()


# ============================================================
# Chat
# ============================================================

@router.get("/{document_id}/chat")
async def get_chat_history(
    document_id: UUID,
    page_id: Optional[str] = Query(None),
    current_user: dict = Depends(require_sales_access),
    db: Session = Depends(get_db),
):
    """Get chat history for a document (global) or page."""
    tenant_id, _ = _extract_ids(current_user)

    doc = db.query(ProposalDocument).filter(
        ProposalDocument.id == document_id,
        ProposalDocument.tenant_id == tenant_id,
    ).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    query = db.query(ProposalDocumentChat).filter(
        ProposalDocumentChat.document_id == document_id,
    )
    if page_id:
        query = query.filter(ProposalDocumentChat.page_id == UUID(page_id))
    else:
        query = query.filter(ProposalDocumentChat.page_id.is_(None))

    messages = query.order_by(ProposalDocumentChat.created_at.asc()).all()

    return {
        "messages": [
            ChatMessageResponse(
                id=str(m.id),
                page_id=str(m.page_id) if m.page_id else None,
                role=m.role,
                content=m.content,
                action_type=m.action_type,
                resulted_in_update=m.resulted_in_update or False,
                created_at=m.created_at.isoformat(),
            ).model_dump()
            for m in messages
        ],
    }


@router.post("/{document_id}/chat")
async def send_chat_message(
    document_id: UUID,
    req: ChatMessageRequest,
    current_user: dict = Depends(require_sales_access),
    db: Session = Depends(get_db),
):
    """Send a chat message (question/rewrite/regenerate_all)."""
    tenant_id, user_id = _extract_ids(current_user)

    doc = db.query(ProposalDocument).filter(
        ProposalDocument.id == document_id,
        ProposalDocument.tenant_id == tenant_id,
    ).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    page_uuid = UUID(req.page_id) if req.page_id else None

    # Validate page exists
    page = None
    if page_uuid:
        page = db.query(ProposalDocumentPage).filter(
            ProposalDocumentPage.id == page_uuid,
            ProposalDocumentPage.document_id == document_id,
        ).first()
        if not page:
            raise HTTPException(status_code=404, detail="Page not found")

    # Save user message
    user_msg = ProposalDocumentChat(
        document_id=document_id,
        page_id=page_uuid,
        role="user",
        content=req.content,
        action_type=req.action_type,
    )
    db.add(user_msg)
    db.flush()

    # Process with LLM
    from app.services.document_chat_service import process_document_chat
    response_text, updated = await process_document_chat(
        doc=doc,
        page=page,
        user_message=req.content,
        action_type=req.action_type,
        db=db,
    )

    # Save assistant message
    assistant_msg = ProposalDocumentChat(
        document_id=document_id,
        page_id=page_uuid,
        role="assistant",
        content=response_text,
        action_type=req.action_type,
        resulted_in_update=updated,
    )
    db.add(assistant_msg)
    db.commit()

    return ChatMessageResponse(
        id=str(assistant_msg.id),
        page_id=str(page_uuid) if page_uuid else None,
        role="assistant",
        content=response_text,
        action_type=req.action_type,
        resulted_in_update=updated,
        created_at=assistant_msg.created_at.isoformat(),
    ).model_dump()


# ============================================================
# Export
# ============================================================

@router.post("/{document_id}/export")
async def export_document(
    document_id: UUID,
    req: ExportRequest,
    current_user: dict = Depends(require_sales_access),
    db: Session = Depends(get_db),
):
    """Export proposal document as PPTX or PDF via Marp."""
    tenant_id, _ = _extract_ids(current_user)

    doc = db.query(ProposalDocument).options(
        joinedload(ProposalDocument.pages),
    ).filter(
        ProposalDocument.id == document_id,
        ProposalDocument.tenant_id == tenant_id,
    ).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    from app.services.marp_export_service import export_to_marp
    result = await export_to_marp(doc, req.format)

    doc.status = "exported"
    db.commit()

    return {"download_url": result["download_url"], "format": req.format}


@router.get("/{document_id}/export/download")
async def download_export(
    document_id: UUID,
    format: Optional[str] = Query(None, pattern=r"^(html|pdf|pptx)$"),
    current_user: dict = Depends(require_sales_access),
    db: Session = Depends(get_db),
):
    """Download exported file from MinIO."""
    tenant_id, _ = _extract_ids(current_user)

    doc = db.query(ProposalDocument).filter(
        ProposalDocument.id == document_id,
        ProposalDocument.tenant_id == tenant_id,
    ).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    from app.services.marp_export_service import download_export_file
    return await download_export_file(document_id, preferred_format=format)
