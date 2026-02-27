# ai-micro-api-sales/tests/unit/services/test_pipeline_config.py
"""
Unit tests for app.services.pipeline_config module.

Tests:
- PipelineConfigData model defaults and methods
- StageConfig model
- KBMappingCategory model
- fetch_pipeline_config with cache hit/miss/fallback
"""
import json
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest


# =============================================================================
# StageConfig Tests
# =============================================================================


@pytest.mark.unit
class TestStageConfig:
    """Tests for StageConfig data model."""

    def test_default_values(self):
        from app.services.pipeline_config import StageConfig

        cfg = StageConfig()
        assert cfg.enabled is True
        assert cfg.name == ""
        assert cfg.model is None
        assert cfg.temperature is None
        assert cfg.max_tokens is None
        assert cfg.prompt_override is None
        assert cfg.use_simulation is None
        assert cfg.use_wage_data is None
        assert cfg.generate_catchcopy is None
        assert cfg.catchcopy_count is None

    def test_custom_values(self):
        from app.services.pipeline_config import StageConfig

        cfg = StageConfig(
            enabled=False,
            name="Stage 1",
            model="gemma2:9b",
            temperature=0.5,
            max_tokens=4096,
            prompt_override="custom prompt",
            use_simulation=True,
            use_wage_data=False,
            generate_catchcopy=True,
            catchcopy_count=3,
        )
        assert cfg.enabled is False
        assert cfg.name == "Stage 1"
        assert cfg.model == "gemma2:9b"
        assert cfg.temperature == 0.5
        assert cfg.max_tokens == 4096
        assert cfg.prompt_override == "custom prompt"
        assert cfg.use_simulation is True
        assert cfg.use_wage_data is False
        assert cfg.generate_catchcopy is True
        assert cfg.catchcopy_count == 3


# =============================================================================
# KBMappingCategory Tests
# =============================================================================


@pytest.mark.unit
class TestKBMappingCategory:
    """Tests for KBMappingCategory data model."""

    def test_default_values(self):
        from app.services.pipeline_config import KBMappingCategory

        cat = KBMappingCategory()
        assert cat.knowledge_base_ids == []
        assert cat.used_in_stages == []
        assert cat.search_query_template == ""
        assert cat.max_chunks == 10

    def test_custom_values(self):
        from app.services.pipeline_config import KBMappingCategory

        cat = KBMappingCategory(
            knowledge_base_ids=["kb-1", "kb-2"],
            used_in_stages=[0, 1, 2],
            search_query_template="{industry} {media_name}",
            max_chunks=5,
        )
        assert cat.knowledge_base_ids == ["kb-1", "kb-2"]
        assert cat.used_in_stages == [0, 1, 2]
        assert cat.max_chunks == 5


# =============================================================================
# PipelineConfigData Tests
# =============================================================================


@pytest.mark.unit
class TestPipelineConfigData:
    """Tests for PipelineConfigData model and methods."""

    def test_default_values(self):
        from app.services.pipeline_config import PipelineConfigData

        cfg = PipelineConfigData()
        assert cfg.enabled is True
        assert cfg.pipeline_name == "次回商談提案書"
        assert cfg.stage_config == {}
        assert cfg.kb_mapping == {}
        assert cfg.is_default is False

    def test_get_stage_existing(self):
        from app.services.pipeline_config import PipelineConfigData, StageConfig

        cfg = PipelineConfigData(
            stage_config={
                "stage_1": StageConfig(enabled=True, name="課題構造化"),
                "stage_2": StageConfig(enabled=False, name="逆算"),
            }
        )
        s1 = cfg.get_stage(1)
        assert s1.enabled is True
        assert s1.name == "課題構造化"

        s2 = cfg.get_stage(2)
        assert s2.enabled is False
        assert s2.name == "逆算"

    def test_get_stage_missing_returns_default(self):
        from app.services.pipeline_config import PipelineConfigData

        cfg = PipelineConfigData()
        s3 = cfg.get_stage(3)
        assert s3.enabled is True
        assert s3.name == "Stage 3"

    def test_get_kb_categories_for_stage(self):
        from app.services.pipeline_config import KBMappingCategory, PipelineConfigData

        cfg = PipelineConfigData(
            kb_mapping={
                "sales_framework": KBMappingCategory(
                    knowledge_base_ids=["kb-1"],
                    used_in_stages=[0, 1],
                ),
                "product_info": KBMappingCategory(
                    knowledge_base_ids=["kb-2"],
                    used_in_stages=[2, 4],
                ),
                "industry_knowledge": KBMappingCategory(
                    knowledge_base_ids=["kb-3"],
                    used_in_stages=[1, 3],
                ),
            }
        )

        stage0 = cfg.get_kb_categories_for_stage(0)
        assert "sales_framework" in stage0
        assert "product_info" not in stage0
        assert "industry_knowledge" not in stage0

        stage1 = cfg.get_kb_categories_for_stage(1)
        assert "sales_framework" in stage1
        assert "industry_knowledge" in stage1
        assert "product_info" not in stage1

        stage5 = cfg.get_kb_categories_for_stage(5)
        assert len(stage5) == 0


# =============================================================================
# fetch_pipeline_config Tests
# =============================================================================


@pytest.mark.unit
class TestFetchPipelineConfig:
    """Tests for fetch_pipeline_config function."""

    @pytest.mark.asyncio
    async def test_cache_hit(self):
        """Should return cached config when Redis has it."""
        from app.services.pipeline_config import PipelineConfigData

        tenant_id = uuid4()
        cached_data = PipelineConfigData(
            enabled=True,
            pipeline_name="キャッシュテスト",
            is_default=False,
        )

        mock_redis = MagicMock()
        mock_redis.get.return_value = cached_data.model_dump_json()

        with patch("app.services.pipeline_config._get_redis", return_value=mock_redis):
            from app.services.pipeline_config import fetch_pipeline_config

            result = await fetch_pipeline_config(tenant_id)

        assert result.pipeline_name == "キャッシュテスト"
        mock_redis.get.assert_called_once()

    @pytest.mark.asyncio
    async def test_cache_miss_fetches_from_admin(self):
        """Should fetch from api-admin when cache misses."""
        from app.services.pipeline_config import PipelineConfigData

        tenant_id = uuid4()

        mock_redis = MagicMock()
        mock_redis.get.return_value = None

        admin_response = {
            "enabled": True,
            "pipeline_name": "API取得テスト",
            "stage_config": {
                "stage_1": {"enabled": True, "name": "Stage 1"},
            },
            "kb_mapping": {},
            "output_template": {"sections": [], "format": "markdown", "locale": "ja"},
            "is_default": False,
        }

        mock_http_resp = MagicMock()
        mock_http_resp.json.return_value = admin_response
        mock_http_resp.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_http_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with (
            patch("app.services.pipeline_config._get_redis", return_value=mock_redis),
            patch("app.services.pipeline_config.httpx.AsyncClient", return_value=mock_client),
        ):
            from app.services.pipeline_config import fetch_pipeline_config

            result = await fetch_pipeline_config(tenant_id)

        assert result.pipeline_name == "API取得テスト"
        assert result.get_stage(1).name == "Stage 1"
        mock_redis.setex.assert_called_once()

    @pytest.mark.asyncio
    async def test_admin_failure_returns_defaults(self):
        """Should return default config when api-admin fails."""
        tenant_id = uuid4()

        mock_redis = MagicMock()
        mock_redis.get.return_value = None

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=Exception("Connection refused"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with (
            patch("app.services.pipeline_config._get_redis", return_value=mock_redis),
            patch("app.services.pipeline_config.httpx.AsyncClient", return_value=mock_client),
        ):
            from app.services.pipeline_config import fetch_pipeline_config

            result = await fetch_pipeline_config(tenant_id)

        assert result.enabled is True
        assert result.pipeline_name == "次回商談提案書"

    @pytest.mark.asyncio
    async def test_redis_unavailable(self):
        """Should work without Redis."""
        tenant_id = uuid4()

        admin_response = {
            "enabled": True,
            "pipeline_name": "NoRedisテスト",
            "stage_config": {},
            "kb_mapping": {},
            "output_template": {},
            "is_default": True,
        }

        mock_http_resp = MagicMock()
        mock_http_resp.json.return_value = admin_response
        mock_http_resp.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_http_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with (
            patch("app.services.pipeline_config._get_redis", return_value=None),
            patch("app.services.pipeline_config.httpx.AsyncClient", return_value=mock_client),
        ):
            from app.services.pipeline_config import fetch_pipeline_config

            result = await fetch_pipeline_config(tenant_id)

        assert result.pipeline_name == "NoRedisテスト"
        assert result.is_default is True
