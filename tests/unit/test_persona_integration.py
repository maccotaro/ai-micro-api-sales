"""Unit tests for persona integration in api-sales (tasks 7.4, 7.6).

Tests:
- LLMClient persona_id/persona_mode payload construction
- Backward compatibility: all LLMClient methods work without persona params
- Pipeline stage _call_llm passes persona_id through
"""

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4


# ---------------------------------------------------------------
# LLMClient: persona_id in payload
# ---------------------------------------------------------------

class TestLLMClientPersonaParams:
    """Verify LLMClient includes persona_id/persona_mode in HTTP payload."""

    def _make_client(self):
        from app.services.llm_client import LLMClient
        return LLMClient(base_url="http://localhost:8012", secret="test")

    @pytest.mark.asyncio
    async def test_chat_includes_persona_id(self):
        """chat() includes persona_id in payload when provided."""
        client = self._make_client()
        captured_payload = {}

        async def mock_post(url, headers, json):
            captured_payload.update(json)
            resp = MagicMock()
            resp.raise_for_status = MagicMock()
            resp.json.return_value = {"response": "ok", "model": "test", "total_tokens": 0}
            return resp

        with patch("httpx.AsyncClient") as mock_cls:
            mock_instance = AsyncMock()
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=False)
            mock_instance.post = mock_post
            mock_cls.return_value = mock_instance

            await client.chat(
                messages=[{"role": "user", "content": "test"}],
                service_name="api-sales",
                persona_id="p-123",
                persona_mode="clone",
            )

        assert captured_payload["persona_id"] == "p-123"
        assert captured_payload["persona_mode"] == "clone"

    @pytest.mark.asyncio
    async def test_generate_includes_persona_id(self):
        """generate() includes persona_id in payload when provided."""
        client = self._make_client()
        captured_payload = {}

        async def mock_post(url, headers, json):
            captured_payload.update(json)
            resp = MagicMock()
            resp.raise_for_status = MagicMock()
            resp.json.return_value = {"response": "ok", "model": "test", "total_tokens": 0}
            return resp

        with patch("httpx.AsyncClient") as mock_cls:
            mock_instance = AsyncMock()
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=False)
            mock_instance.post = mock_post
            mock_cls.return_value = mock_instance

            await client.generate(
                prompt="test",
                task_type="proposal",
                service_name="api-sales",
                persona_id="p-456",
            )

        assert captured_payload["persona_id"] == "p-456"
        assert "persona_mode" not in captured_payload  # Not provided, not included


# ---------------------------------------------------------------
# Backward compatibility: no persona params
# ---------------------------------------------------------------

class TestBackwardCompatibility:
    """Task 7.6: Existing endpoints work without persona_id."""

    def _make_client(self):
        from app.services.llm_client import LLMClient
        return LLMClient(base_url="http://localhost:8012", secret="test")

    @pytest.mark.asyncio
    async def test_chat_without_persona(self):
        """chat() works without persona_id — no persona keys in payload."""
        client = self._make_client()
        captured_payload = {}

        async def mock_post(url, headers, json):
            captured_payload.update(json)
            resp = MagicMock()
            resp.raise_for_status = MagicMock()
            resp.json.return_value = {"response": "ok", "model": "test", "total_tokens": 0}
            return resp

        with patch("httpx.AsyncClient") as mock_cls:
            mock_instance = AsyncMock()
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=False)
            mock_instance.post = mock_post
            mock_cls.return_value = mock_instance

            await client.chat(
                messages=[{"role": "user", "content": "hello"}],
                service_name="api-sales",
            )

        assert "persona_id" not in captured_payload
        assert "persona_mode" not in captured_payload

    @pytest.mark.asyncio
    async def test_generate_without_persona(self):
        """generate() works without persona_id."""
        client = self._make_client()
        captured_payload = {}

        async def mock_post(url, headers, json):
            captured_payload.update(json)
            resp = MagicMock()
            resp.raise_for_status = MagicMock()
            resp.json.return_value = {"response": "ok", "model": "test", "total_tokens": 0}
            return resp

        with patch("httpx.AsyncClient") as mock_cls:
            mock_instance = AsyncMock()
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=False)
            mock_instance.post = mock_post
            mock_cls.return_value = mock_instance

            await client.generate(
                prompt="test",
                task_type="test",
                service_name="api-sales",
            )

        assert "persona_id" not in captured_payload
        assert "persona_mode" not in captured_payload


# ---------------------------------------------------------------
# Schema backward compatibility
# ---------------------------------------------------------------

class TestSchemaBackwardCompatibility:
    """Existing request schemas work with and without persona_id."""

    def test_pipeline_request_without_persona(self):
        """PipelineRequest works without persona_id."""
        from app.routers.proposal_pipeline import PipelineRequest
        req = PipelineRequest(minute_id=uuid4())
        assert req.persona_id is None

    def test_pipeline_request_with_persona(self):
        """PipelineRequest accepts persona_id."""
        from app.routers.proposal_pipeline import PipelineRequest
        pid = uuid4()
        req = PipelineRequest(minute_id=uuid4(), persona_id=pid)
        assert req.persona_id == pid

    def test_chat_stream_request_without_persona(self):
        """ChatStreamRequest works without persona_id."""
        from app.schemas.chat import ChatStreamRequest
        req = ChatStreamRequest(content="テスト質問です。")
        assert req.persona_id is None

    def test_chat_stream_request_with_persona(self):
        """ChatStreamRequest accepts persona_id."""
        from app.schemas.chat import ChatStreamRequest
        pid = uuid4()
        req = ChatStreamRequest(content="テスト質問です。", persona_id=pid)
        assert req.persona_id == pid

    def test_proposal_chat_request_without_persona(self):
        """ProposalChatRequest works without persona_id."""
        from app.routers.proposal_chat import ProposalChatRequest
        req = ProposalChatRequest(
            query="飲食店の採用について提案してください",
            knowledge_base_id=uuid4(),
        )
        assert req.persona_id is None

    def test_proposal_chat_request_with_persona(self):
        """ProposalChatRequest accepts persona_id."""
        from app.routers.proposal_chat import ProposalChatRequest
        pid = uuid4()
        req = ProposalChatRequest(
            query="飲食店の採用について提案してください",
            knowledge_base_id=uuid4(),
            persona_id=pid,
        )
        assert req.persona_id == pid
