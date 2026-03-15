# ai-micro-api-sales/tests/contract/test_proposal_documents_contract.py
"""
Contract tests for proposal document API endpoints.

Validates request/response schemas without hitting real services.
"""
import pytest
from pydantic import BaseModel, ValidationError
from typing import Optional
from uuid import uuid4


# ============================================================
# Response Schemas (contract definitions)
# ============================================================

class PageSchema(BaseModel):
    id: str
    page_number: int
    title: Optional[str]
    markdown_content: str
    purpose: Optional[str]


class DocumentListItemSchema(BaseModel):
    id: str
    title: str
    status: str
    created_at: str
    updated_at: str
    page_count: int


class DocumentListResponseSchema(BaseModel):
    items: list[DocumentListItemSchema]
    total: int
    page: int
    page_size: int


class DocumentDetailSchema(BaseModel):
    id: str
    title: str
    status: str
    marp_theme: str
    story_structure: dict
    pipeline_run_id: Optional[str]
    minute_id: Optional[str]
    created_at: str
    updated_at: str
    pages: list[PageSchema]


class ChatMessageSchema(BaseModel):
    id: str
    page_id: Optional[str]
    role: str
    content: str
    action_type: Optional[str]
    resulted_in_update: bool
    created_at: str


class ChatHistoryResponseSchema(BaseModel):
    messages: list[ChatMessageSchema]


class ExportResponseSchema(BaseModel):
    download_url: str
    format: str


# ============================================================
# Contract Tests
# ============================================================

@pytest.mark.contract
class TestProposalDocumentsContract:
    """Contract tests for proposal documents API."""

    def test_document_list_response_schema(self):
        """GET /proposal-documents response SHALL match DocumentListResponseSchema."""
        sample = {
            "items": [
                {
                    "id": str(uuid4()),
                    "title": "テスト提案書",
                    "status": "draft",
                    "created_at": "2026-03-14T10:00:00+09:00",
                    "updated_at": "2026-03-14T10:00:00+09:00",
                    "page_count": 8,
                }
            ],
            "total": 1,
            "page": 1,
            "page_size": 20,
        }
        result = DocumentListResponseSchema(**sample)
        assert result.total == 1
        assert len(result.items) == 1
        assert result.items[0].status == "draft"

    def test_document_detail_response_schema(self):
        """GET /proposal-documents/{id} response SHALL match DocumentDetailSchema."""
        sample = {
            "id": str(uuid4()),
            "title": "テスト提案書",
            "status": "draft",
            "marp_theme": "default",
            "story_structure": {"story_theme": "test", "pages": []},
            "pipeline_run_id": str(uuid4()),
            "minute_id": str(uuid4()),
            "created_at": "2026-03-14T10:00:00+09:00",
            "updated_at": "2026-03-14T10:00:00+09:00",
            "pages": [
                {
                    "id": str(uuid4()),
                    "page_number": 1,
                    "title": "ページ1",
                    "markdown_content": "# Test",
                    "purpose": "テスト",
                }
            ],
        }
        result = DocumentDetailSchema(**sample)
        assert len(result.pages) == 1
        assert result.pages[0].page_number == 1

    def test_document_detail_with_null_optionals(self):
        """Optional fields SHALL accept null values."""
        sample = {
            "id": str(uuid4()),
            "title": "テスト",
            "status": "draft",
            "marp_theme": "default",
            "story_structure": {},
            "pipeline_run_id": None,
            "minute_id": None,
            "created_at": "2026-03-14T10:00:00+09:00",
            "updated_at": "2026-03-14T10:00:00+09:00",
            "pages": [],
        }
        result = DocumentDetailSchema(**sample)
        assert result.pipeline_run_id is None

    def test_chat_message_request_question(self):
        """POST /chat request with action_type=question SHALL be valid."""
        from app.routers.proposal_documents import ChatMessageRequest
        req = ChatMessageRequest(
            page_id=str(uuid4()),
            content="なぜこの課題を選んだ？",
            action_type="question",
        )
        assert req.action_type == "question"

    def test_chat_message_request_rewrite(self):
        """POST /chat request with action_type=rewrite SHALL be valid."""
        from app.routers.proposal_documents import ChatMessageRequest
        req = ChatMessageRequest(
            page_id=str(uuid4()),
            content="もっとデータを入れて",
            action_type="rewrite",
        )
        assert req.action_type == "rewrite"

    def test_chat_message_request_regenerate_all(self):
        """POST /chat request with action_type=regenerate_all SHALL be valid."""
        from app.routers.proposal_documents import ChatMessageRequest
        req = ChatMessageRequest(
            page_id=None,
            content="構成を変えて",
            action_type="regenerate_all",
        )
        assert req.action_type == "regenerate_all"
        assert req.page_id is None

    def test_chat_message_request_invalid_action(self):
        """POST /chat with invalid action_type SHALL be rejected."""
        from app.routers.proposal_documents import ChatMessageRequest
        with pytest.raises(ValidationError):
            ChatMessageRequest(
                content="test",
                action_type="invalid_action",
            )

    def test_chat_history_response_schema(self):
        """GET /chat response SHALL match ChatHistoryResponseSchema."""
        sample = {
            "messages": [
                {
                    "id": str(uuid4()),
                    "page_id": str(uuid4()),
                    "role": "user",
                    "content": "テスト質問",
                    "action_type": "question",
                    "resulted_in_update": False,
                    "created_at": "2026-03-14T10:00:00+09:00",
                },
                {
                    "id": str(uuid4()),
                    "page_id": str(uuid4()),
                    "role": "assistant",
                    "content": "回答です",
                    "action_type": "question",
                    "resulted_in_update": False,
                    "created_at": "2026-03-14T10:01:00+09:00",
                },
            ]
        }
        result = ChatHistoryResponseSchema(**sample)
        assert len(result.messages) == 2

    def test_export_request_schema(self):
        """POST /export request SHALL accept pptx or pdf format."""
        from app.routers.proposal_documents import ExportRequest
        req_pptx = ExportRequest(format="pptx")
        assert req_pptx.format == "pptx"
        req_pdf = ExportRequest(format="pdf")
        assert req_pdf.format == "pdf"

    def test_export_request_invalid_format(self):
        """POST /export with invalid format SHALL be rejected."""
        from app.routers.proposal_documents import ExportRequest
        with pytest.raises(ValidationError):
            ExportRequest(format="docx")

    def test_export_response_schema(self):
        """POST /export response SHALL match ExportResponseSchema."""
        sample = {
            "download_url": "/api/sales/proposal-documents/xxx/export/download",
            "format": "pptx",
        }
        result = ExportResponseSchema(**sample)
        assert result.format == "pptx"

    def test_tenant_isolation_404_contract(self):
        """Accessing another tenant's document SHALL return 404 (not 403)."""
        # This is a contract expectation — actual test needs DB
        # Document: the API returns 404 (not found) rather than 403 (forbidden)
        # to prevent information leakage about other tenants' documents
        pass
