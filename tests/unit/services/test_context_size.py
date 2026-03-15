# ai-micro-api-sales/tests/unit/services/test_context_size.py
"""
TDD unit tests for context size constraints.

Tests that each stage's LLM input stays within qwen3:14b limits.
Token estimation: ~4 chars per token for Japanese text.
"""
import json
import pytest
from unittest.mock import AsyncMock, MagicMock

from tests.fixtures.proposal_document_fixtures import (
    make_stage0_context,
    make_stage1_output,
    make_stage6_context,
    make_stage7_output,
    make_stage8_output,
    make_stage9_output,
    TENANT_ID,
    USER_ID,
    PIPELINE_RUN_ID,
    MINUTE_ID,
)


def estimate_tokens(text: str) -> int:
    """Rough token estimation for Japanese text (~4 chars per token)."""
    return len(text) // 4


@pytest.mark.unit
class TestContextSize:
    """Tests for context size constraints across Stage 7-10."""

    @pytest.fixture
    def mock_config(self):
        config = MagicMock()
        stage_cfg = MagicMock()
        stage_cfg.enabled = True
        stage_cfg.model = None
        stage_cfg.temperature = 0.3
        stage_cfg.max_tokens = 2000
        stage_cfg.prompt_override = None
        config.get_stage.return_value = stage_cfg
        return config

    @pytest.fixture
    def capturing_llm_client(self):
        """LLM client that captures prompts for size analysis."""
        client = AsyncMock()
        client.captured_prompts = []

        async def capture_chat(**kwargs):
            messages = kwargs.get("messages", [])
            total_text = " ".join(m["content"] for m in messages if isinstance(m.get("content"), str))
            client.captured_prompts.append(total_text)
            return {"response": json.dumps(make_stage7_output(), ensure_ascii=False)}

        client.chat.side_effect = capture_chat
        return client

    @pytest.mark.asyncio
    async def test_stage7_context_within_limit(self, mock_config, capturing_llm_client):
        """Stage 7 input context SHALL NOT exceed ~3,500 tokens."""
        from app.services.proposal_stages import stage7_industry_target_analysis

        await stage7_industry_target_analysis(
            make_stage0_context(), make_stage1_output(), make_stage6_context(),
            mock_config, capturing_llm_client, TENANT_ID
        )

        assert len(capturing_llm_client.captured_prompts) == 1
        tokens = estimate_tokens(capturing_llm_client.captured_prompts[0])
        assert tokens <= 5000, f"Stage 7 context is {tokens} tokens, expected <= 5000"

    @pytest.mark.asyncio
    async def test_stage8_context_within_limit(self, mock_config, capturing_llm_client):
        """Stage 8 input context SHALL NOT exceed ~3,500 tokens."""
        from app.services.proposal_stages import stage8_appeal_strategy

        capturing_llm_client.chat.side_effect = None
        capturing_llm_client.chat.return_value = {
            "response": json.dumps(make_stage8_output(), ensure_ascii=False)
        }

        await stage8_appeal_strategy(
            make_stage0_context(), make_stage1_output(),
            make_stage6_context(), make_stage7_output(),
            mock_config, capturing_llm_client, TENANT_ID
        )

        call_args = capturing_llm_client.chat.call_args
        messages = call_args.kwargs.get("messages", [])
        total_text = " ".join(m["content"] for m in messages if isinstance(m.get("content"), str))
        tokens = estimate_tokens(total_text)
        assert tokens <= 5000, f"Stage 8 context is {tokens} tokens, expected <= 5000"

    @pytest.mark.asyncio
    async def test_stage10_per_page_context_within_limit(self, mock_config):
        """Stage 10 per-page LLM input SHALL NOT exceed ~2,000 tokens."""
        mock_llm = AsyncMock()
        mock_llm.captured_prompts = []

        sample_md = "# Test\n\nContent"

        async def capture(**kwargs):
            messages = kwargs.get("messages", [])
            total_text = " ".join(m["content"] for m in messages if isinstance(m.get("content"), str))
            mock_llm.captured_prompts.append(total_text)
            return {"response": sample_md}

        mock_llm.chat.side_effect = capture
        mock_db = MagicMock()

        from app.services.proposal_stages import stage10_page_generation

        await stage10_page_generation(
            make_stage0_context(), make_stage1_output(),
            make_stage6_context(), make_stage7_output(), make_stage8_output(),
            make_stage9_output(), mock_config, mock_llm, mock_db,
            TENANT_ID, USER_ID, PIPELINE_RUN_ID, MINUTE_ID,
        )

        for i, prompt in enumerate(mock_llm.captured_prompts):
            tokens = estimate_tokens(prompt)
            assert tokens <= 3500, f"Stage 10 page {i+1} context is {tokens} tokens, expected <= 3500"
