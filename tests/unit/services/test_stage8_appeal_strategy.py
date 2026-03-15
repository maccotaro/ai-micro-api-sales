# ai-micro-api-sales/tests/unit/services/test_stage8_appeal_strategy.py
"""
TDD unit tests for Stage 8: Appeal Strategy (LLM).

Tests:
- Strategy axes output structure
- Catchcopy psychology_link is required
- Before/After success case construction
- Fallback when no publication records
- Decision-maker psychology utilization
"""
import json
import pytest
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from tests.fixtures.proposal_document_fixtures import (
    make_stage0_context,
    make_stage1_output,
    make_stage6_context,
    make_stage7_output,
    make_stage8_output,
    TENANT_ID,
)


@pytest.mark.unit
class TestStage8AppealStrategy:
    """Tests for stage8_appeal_strategy() function."""

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
    def mock_llm_client(self):
        client = AsyncMock()
        client.chat.return_value = {
            "response": json.dumps(make_stage8_output(), ensure_ascii=False)
        }
        return client

    @pytest.mark.asyncio
    async def test_output_contains_strategy_axes(self, mock_config, mock_llm_client):
        """Stage 8 output SHALL include strategy_axes array."""
        from app.services.proposal_stages import stage8_appeal_strategy

        result = await stage8_appeal_strategy(
            make_stage0_context(), make_stage1_output(),
            make_stage6_context(), make_stage7_output(),
            mock_config, mock_llm_client, TENANT_ID
        )

        assert "strategy_axes" in result
        assert len(result["strategy_axes"]) > 0
        for axis in result["strategy_axes"]:
            assert "id" in axis
            assert "title" in axis
            assert "rationale" in axis
            assert "target_psychology" in axis

    @pytest.mark.asyncio
    async def test_catchcopy_has_psychology_link(self, mock_config, mock_llm_client):
        """Each catchcopy SHALL include a psychology_link field."""
        from app.services.proposal_stages import stage8_appeal_strategy

        result = await stage8_appeal_strategy(
            make_stage0_context(), make_stage1_output(),
            make_stage6_context(), make_stage7_output(),
            mock_config, mock_llm_client, TENANT_ID
        )

        for axis in result["strategy_axes"]:
            assert "catchcopies" in axis
            for copy in axis["catchcopies"]:
                assert "text" in copy
                assert "psychology_link" in copy
                assert len(copy["psychology_link"]) > 0

    @pytest.mark.asyncio
    async def test_success_case_before_after(self, mock_config, mock_llm_client):
        """Stage 8 output SHALL include success_case_references with before/after."""
        from app.services.proposal_stages import stage8_appeal_strategy

        result = await stage8_appeal_strategy(
            make_stage0_context(), make_stage1_output(),
            make_stage6_context(), make_stage7_output(),
            mock_config, mock_llm_client, TENANT_ID
        )

        assert "success_case_references" in result
        for case in result["success_case_references"]:
            assert "before" in case
            assert "after" in case
            assert "improvement" in case

    @pytest.mark.asyncio
    async def test_fallback_no_publication_records(self, mock_config, mock_llm_client):
        """When no publication_records, Stage 8 SHALL still produce strategy axes."""
        from app.services.proposal_stages import stage8_appeal_strategy

        stage6_output = make_stage6_context()
        stage6_output["publication_records"] = []
        stage6_output["success_cases"] = []

        # Mock LLM response without success cases
        output_no_cases = make_stage8_output()
        output_no_cases["success_case_references"] = []
        mock_llm_client.chat.return_value = {
            "response": json.dumps(output_no_cases, ensure_ascii=False)
        }

        result = await stage8_appeal_strategy(
            make_stage0_context(), make_stage1_output(),
            stage6_output, make_stage7_output(),
            mock_config, mock_llm_client, TENANT_ID
        )

        assert "strategy_axes" in result
        assert len(result["strategy_axes"]) > 0

    @pytest.mark.asyncio
    async def test_decision_maker_psychology_in_prompt(self, mock_config, mock_llm_client):
        """Stage 8 prompt SHALL include decision-maker psychology data."""
        from app.services.proposal_stages import stage8_appeal_strategy

        stage6_output = make_stage6_context()

        await stage8_appeal_strategy(
            make_stage0_context(), make_stage1_output(),
            stage6_output, make_stage7_output(),
            mock_config, mock_llm_client, TENANT_ID
        )

        mock_llm_client.chat.assert_called_once()
        call_kwargs = mock_llm_client.chat.call_args.kwargs
        messages = call_kwargs.get("messages", [])
        system_msg = next((m for m in messages if m.get("role") == "system"), {})
        prompt = system_msg.get("content", "")
        assert "担当者" in prompt or "意思決定" in prompt or "費用対効果" in prompt
