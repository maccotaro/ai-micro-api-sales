# ai-micro-api-sales/tests/unit/services/test_stage7_industry_target_analysis.py
"""
TDD unit tests for Stage 7: Industry & Target Analysis (LLM).

Tests:
- LLM prompt contains correct input context
- Output JSON schema validation (industry_analysis, target_insights, decision_maker_insights)
- source flag (kb_data / general_knowledge) switching
- Context size constraint (~3,500 tokens)
"""
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from tests.fixtures.proposal_document_fixtures import (
    make_stage0_context,
    make_stage1_output,
    make_stage6_context,
    make_stage7_output,
    TENANT_ID,
)


@pytest.mark.unit
class TestStage7IndustryTargetAnalysis:
    """Tests for stage7_industry_target_analysis() function."""

    @pytest.fixture
    def mock_config(self):
        config = MagicMock()
        stage_cfg = MagicMock()
        stage_cfg.enabled = True
        stage_cfg.model = None
        stage_cfg.temperature = 0.3
        stage_cfg.max_tokens = 2000
        stage_cfg.prompt_override = None  # Must be None so _call_llm uses system_prompt
        config.get_stage.return_value = stage_cfg
        return config

    @pytest.fixture
    def mock_llm_client(self):
        client = AsyncMock()
        client.chat.return_value = {
            "response": json.dumps(make_stage7_output(), ensure_ascii=False)
        }
        return client

    @pytest.mark.asyncio
    async def test_output_contains_industry_analysis(self, mock_config, mock_llm_client):
        """Stage 7 output SHALL include industry_analysis."""
        from app.services.proposal_stages import stage7_industry_target_analysis

        context = make_stage0_context()
        stage1_output = make_stage1_output()
        stage6_output = make_stage6_context()

        result = await stage7_industry_target_analysis(
            context, stage1_output, stage6_output, mock_config, mock_llm_client, TENANT_ID
        )

        assert "industry_analysis" in result
        assert "industry_name" in result["industry_analysis"]
        assert "job_types" in result["industry_analysis"]

    @pytest.mark.asyncio
    async def test_output_contains_target_insights(self, mock_config, mock_llm_client):
        """Stage 7 output SHALL include target_insights with psychological_axes."""
        from app.services.proposal_stages import stage7_industry_target_analysis

        context = make_stage0_context()
        stage1_output = make_stage1_output()
        stage6_output = make_stage6_context()

        result = await stage7_industry_target_analysis(
            context, stage1_output, stage6_output, mock_config, mock_llm_client, TENANT_ID
        )

        assert "target_insights" in result
        assert "primary_target" in result["target_insights"]
        assert "psychological_axes" in result["target_insights"]
        for axis in result["target_insights"]["psychological_axes"]:
            assert "axis" in axis
            assert "detail" in axis
            assert "appeal_direction" in axis

    @pytest.mark.asyncio
    async def test_output_contains_decision_maker_insights(self, mock_config, mock_llm_client):
        """Stage 7 output SHALL include decision_maker_insights."""
        from app.services.proposal_stages import stage7_industry_target_analysis

        context = make_stage0_context()
        stage1_output = make_stage1_output()
        stage6_output = make_stage6_context()

        result = await stage7_industry_target_analysis(
            context, stage1_output, stage6_output, mock_config, mock_llm_client, TENANT_ID
        )

        assert "decision_maker_insights" in result
        assert "role" in result["decision_maker_insights"]
        assert "judgment_criteria" in result["decision_maker_insights"]
        assert "common_concerns" in result["decision_maker_insights"]

    @pytest.mark.asyncio
    async def test_source_flag_kb_data(self, mock_config, mock_llm_client):
        """When KB psychology data exists, source SHALL be 'kb_data'."""
        from app.services.proposal_stages import stage7_industry_target_analysis

        context = make_stage0_context()
        stage1_output = make_stage1_output()
        stage6_output = make_stage6_context()  # has psychology chunks

        result = await stage7_industry_target_analysis(
            context, stage1_output, stage6_output, mock_config, mock_llm_client, TENANT_ID
        )

        assert result.get("source") == "kb_data"

    @pytest.mark.asyncio
    async def test_source_flag_general_knowledge(self, mock_config, mock_llm_client):
        """When no KB psychology data, source SHALL be 'general_knowledge'."""
        from app.services.proposal_stages import stage7_industry_target_analysis

        context = make_stage0_context()
        stage1_output = make_stage1_output()
        stage6_output = make_stage6_context()
        stage6_output["end_user_psychology_chunks"] = []
        stage6_output["decision_maker_psychology_chunks"] = []

        # Override LLM response without source field
        stage7_no_source = make_stage7_output()
        del stage7_no_source["source"]
        mock_llm_client.chat.return_value = {
            "response": json.dumps(stage7_no_source, ensure_ascii=False)
        }

        result = await stage7_industry_target_analysis(
            context, stage1_output, stage6_output, mock_config, mock_llm_client, TENANT_ID
        )

        assert result.get("source") == "general_knowledge"

    @pytest.mark.asyncio
    async def test_llm_prompt_contains_industry_info(self, mock_config, mock_llm_client):
        """LLM prompt SHALL contain industry and job type information."""
        from app.services.proposal_stages import stage7_industry_target_analysis

        context = make_stage0_context(industry="警備", area="東京")
        stage1_output = make_stage1_output()
        stage6_output = make_stage6_context()

        await stage7_industry_target_analysis(
            context, stage1_output, stage6_output, mock_config, mock_llm_client, TENANT_ID
        )

        # _call_llm builds messages=[{"role":"system","content":prompt}, {"role":"user",...}]
        mock_llm_client.chat.assert_called_once()
        call_kwargs = mock_llm_client.chat.call_args.kwargs
        messages = call_kwargs.get("messages", [])
        # System message contains the full prompt with industry info
        system_msg = next((m for m in messages if m.get("role") == "system"), {})
        assert "警備" in system_msg.get("content", "")
