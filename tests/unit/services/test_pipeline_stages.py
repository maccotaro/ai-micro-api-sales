# ai-micro-api-sales/tests/unit/services/test_pipeline_stages.py
"""
Unit tests for app.services.pipeline_stages module.

Tests:
- _parse_json_response
- _merge_kb_results
- _load_product_data / _load_simulation_data / _load_wage_data
- _load_publication_records / _load_campaign_data
- _call_llm
- stage0-5 function signatures and basic behavior
"""
import json
from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest


# =============================================================================
# _parse_json_response Tests
# =============================================================================


@pytest.mark.unit
class TestParseJsonResponse:
    """Tests for _parse_json_response helper."""

    def test_valid_json(self):
        from app.services.pipeline_stages import _parse_json_response

        result = _parse_json_response('{"key": "value"}')
        assert result == {"key": "value"}

    def test_json_with_markdown_code_block(self):
        from app.services.pipeline_stages import _parse_json_response

        text = '```json\n{"key": "value"}\n```'
        result = _parse_json_response(text)
        assert result == {"key": "value"}

    def test_json_with_plain_code_block(self):
        from app.services.pipeline_stages import _parse_json_response

        text = '```\n{"key": "value"}\n```'
        result = _parse_json_response(text)
        assert result == {"key": "value"}

    def test_invalid_json_returns_raw(self):
        from app.services.pipeline_stages import _parse_json_response

        result = _parse_json_response("this is not json")
        assert "raw_response" in result
        assert result["raw_response"] == "this is not json"

    def test_whitespace_trimming(self):
        from app.services.pipeline_stages import _parse_json_response

        result = _parse_json_response('  \n  {"key": "value"}  \n  ')
        assert result == {"key": "value"}

    def test_complex_json(self):
        from app.services.pipeline_stages import _parse_json_response

        data = {
            "issues": [
                {"id": "I-1", "title": "テスト課題", "bant_c": {"budget": {"status": "確認済"}}}
            ]
        }
        result = _parse_json_response(json.dumps(data, ensure_ascii=False))
        assert result["issues"][0]["id"] == "I-1"


# =============================================================================
# _merge_kb_results Tests
# =============================================================================


@pytest.mark.unit
class TestMergeKBResults:
    """Tests for _merge_kb_results helper."""

    def test_merge_new_keys(self):
        from app.services.pipeline_stages import _merge_kb_results

        base = {"cat1": ["chunk1"]}
        new = {"cat2": ["chunk2"]}
        _merge_kb_results(base, new)
        assert "cat1" in base
        assert "cat2" in base

    def test_merge_existing_keys_extends(self):
        from app.services.pipeline_stages import _merge_kb_results

        base = {"cat1": ["chunk1"]}
        new = {"cat1": ["chunk2", "chunk3"]}
        _merge_kb_results(base, new)
        assert base["cat1"] == ["chunk1", "chunk2", "chunk3"]

    def test_merge_empty_new(self):
        from app.services.pipeline_stages import _merge_kb_results

        base = {"cat1": ["chunk1"]}
        _merge_kb_results(base, {})
        assert base == {"cat1": ["chunk1"]}


# =============================================================================
# _load_product_data Tests
# =============================================================================


@pytest.mark.unit
class TestLoadProductData:
    """Tests for _load_product_data helper."""

    def test_returns_product_list(self, mock_db_session):
        from app.services.pipeline_stages import _load_product_data

        mock_product = MagicMock()
        mock_product.name = "バイトル"
        mock_product.category = "求人広告"
        mock_product.base_price = Decimal("50000")
        mock_product.price_unit = "円/週"
        mock_product.description = "テスト商品"

        mock_query = MagicMock()
        mock_query.filter.return_value.limit.return_value.all.return_value = [mock_product]
        mock_db_session.query.return_value = mock_query

        # MediaPricing query returns empty
        mock_pricing_q = MagicMock()
        mock_pricing_q.filter.return_value.limit.return_value.all.return_value = []
        # Second call to query for MediaPricing
        mock_db_session.query.side_effect = [mock_query, mock_pricing_q]

        result = _load_product_data(mock_db_session, {"area": "関東"})
        assert len(result) == 1
        assert result[0]["name"] == "バイトル"
        assert result[0]["base_price"] == 50000.0

    def test_returns_empty_when_no_products(self, mock_db_session):
        from app.services.pipeline_stages import _load_product_data

        mock_query = MagicMock()
        mock_query.filter.return_value.limit.return_value.all.return_value = []
        mock_db_session.query.return_value = mock_query

        result = _load_product_data(mock_db_session, {})
        assert result == []


# =============================================================================
# _load_simulation_data Tests
# =============================================================================


@pytest.mark.unit
class TestLoadSimulationData:
    """Tests for _load_simulation_data helper."""

    def test_returns_simulation_params(self, mock_db_session):
        from app.services.pipeline_stages import _load_simulation_data

        mock_param = MagicMock()
        mock_param.area = "関東"
        mock_param.industry = "飲食"
        mock_param.pv_coefficient = Decimal("1.5")
        mock_param.apply_rate = Decimal("0.02")
        mock_param.conversion_rate = Decimal("0.05")

        mock_query = MagicMock()
        mock_query.filter.return_value.filter.return_value.limit.return_value.all.return_value = [mock_param]
        mock_db_session.query.return_value = mock_query

        result = _load_simulation_data(mock_db_session, {"area": "関東", "industry": "飲食"})
        assert len(result) == 1
        assert result[0]["area"] == "関東"
        assert result[0]["pv_coefficient"] == 1.5


# =============================================================================
# _load_wage_data Tests
# =============================================================================


@pytest.mark.unit
class TestLoadWageData:
    """Tests for _load_wage_data helper."""

    def test_returns_wage_data(self, mock_db_session):
        from app.services.pipeline_stages import _load_wage_data

        mock_wage = MagicMock()
        mock_wage.area = "関東"
        mock_wage.industry = "飲食"
        mock_wage.employment_type = "アルバイト"
        mock_wage.min_wage = Decimal("1100")
        mock_wage.avg_wage = Decimal("1350")

        mock_query = MagicMock()
        mock_query.filter.return_value.filter.return_value.limit.return_value.all.return_value = [mock_wage]
        mock_db_session.query.return_value = mock_query

        result = _load_wage_data(mock_db_session, {"area": "関東", "industry": "飲食"})
        assert len(result) == 1
        assert result[0]["min_wage"] == 1100.0


# =============================================================================
# _load_campaign_data Tests
# =============================================================================


@pytest.mark.unit
class TestLoadCampaignData:
    """Tests for _load_campaign_data helper."""

    def test_returns_active_campaigns(self, mock_db_session):
        from app.services.pipeline_stages import _load_campaign_data

        mock_campaign = MagicMock()
        mock_campaign.name = "春キャンペーン"
        mock_campaign.description = "春の特別割引"
        mock_campaign.start_date = date.today() - timedelta(days=10)
        mock_campaign.end_date = date.today() + timedelta(days=20)
        mock_campaign.discount_rate = Decimal("10")
        mock_campaign.discount_amount = None
        mock_campaign.conditions = {"min_products": 2}

        mock_query = MagicMock()
        mock_query.filter.return_value.limit.return_value.all.return_value = [mock_campaign]
        mock_db_session.query.return_value = mock_query

        result = _load_campaign_data(mock_db_session)
        assert len(result) == 1
        assert result[0]["name"] == "春キャンペーン"
        assert result[0]["discount_rate"] == 10.0
        assert result[0]["conditions"] == {"min_products": 2}


# =============================================================================
# _call_llm Tests
# =============================================================================


@pytest.mark.unit
class TestCallLLM:
    """Tests for _call_llm helper."""

    @pytest.mark.asyncio
    async def test_basic_call(self):
        from app.services.pipeline_config import StageConfig
        from app.services.pipeline_stages import _call_llm

        mock_client = AsyncMock()
        mock_client.chat.return_value = {
            "response": '{"issues": []}',
            "model": "gemma2:9b",
            "total_tokens": 100,
        }

        stage_cfg = StageConfig(name="test", model="gemma2:9b", temperature=0.3)
        result = await _call_llm(
            mock_client, "テストプロンプト", stage_cfg,
            uuid4(), stage_num=1,
        )
        assert result == {"issues": []}
        mock_client.chat.assert_called_once()

    @pytest.mark.asyncio
    async def test_uses_prompt_override(self):
        from app.services.pipeline_config import StageConfig
        from app.services.pipeline_stages import _call_llm

        mock_client = AsyncMock()
        mock_client.chat.return_value = {"response": '{"result": "ok"}'}

        stage_cfg = StageConfig(prompt_override="カスタムプロンプト")
        await _call_llm(mock_client, "元のプロンプト", stage_cfg, uuid4(), stage_num=1)

        call_args = mock_client.chat.call_args
        messages = call_args.kwargs.get("messages", call_args.args[0] if call_args.args else None)
        if messages is None:
            messages = call_args[1].get("messages", [])
        assert messages[0]["content"] == "カスタムプロンプト"

    @pytest.mark.asyncio
    async def test_passes_pipeline_run_id(self):
        from app.services.pipeline_config import StageConfig
        from app.services.pipeline_stages import _call_llm

        mock_client = AsyncMock()
        mock_client.chat.return_value = {"response": '{"ok": true}'}

        stage_cfg = StageConfig()
        run_id = "test-run-123"
        await _call_llm(
            mock_client, "prompt", stage_cfg,
            uuid4(), stage_num=2, pipeline_run_id=run_id,
        )

        call_kwargs = mock_client.chat.call_args.kwargs
        assert call_kwargs.get("pipeline_run_id") == run_id
        assert call_kwargs.get("pipeline_stage") == 2

    @pytest.mark.asyncio
    async def test_handles_markdown_json_response(self):
        from app.services.pipeline_config import StageConfig
        from app.services.pipeline_stages import _call_llm

        mock_client = AsyncMock()
        mock_client.chat.return_value = {
            "response": '```json\n{"key": "value"}\n```',
        }

        stage_cfg = StageConfig()
        result = await _call_llm(mock_client, "prompt", stage_cfg, uuid4(), stage_num=1)
        assert result == {"key": "value"}
