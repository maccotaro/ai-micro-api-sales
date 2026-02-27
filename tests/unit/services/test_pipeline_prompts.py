# ai-micro-api-sales/tests/unit/services/test_pipeline_prompts.py
"""
Unit tests for app.services.pipeline_prompts module.

Tests:
- build_kb_context_block formatting
- Prompt template placeholder validation
"""
import pytest


# =============================================================================
# build_kb_context_block Tests
# =============================================================================


@pytest.mark.unit
class TestBuildKBContextBlock:
    """Tests for build_kb_context_block function."""

    def test_empty_dict_returns_fallback(self):
        from app.services.pipeline_prompts import build_kb_context_block

        result = build_kb_context_block({})
        assert "ナレッジベース情報" in result
        assert "該当する情報がありません" in result

    def test_none_like_empty(self):
        from app.services.pipeline_prompts import build_kb_context_block

        result = build_kb_context_block({})
        assert "一般的な知識で対応してください" in result

    def test_single_category_with_chunks(self):
        from app.services.pipeline_prompts import build_kb_context_block

        kb_results = {
            "営業フレームワーク": [
                "BANT-Cフレームワークとは...",
                "課題分析の手順は...",
            ]
        }
        result = build_kb_context_block(kb_results)
        assert "#### 営業フレームワーク" in result
        assert "[1] BANT-Cフレームワークとは..." in result
        assert "[2] 課題分析の手順は..." in result

    def test_multiple_categories(self):
        from app.services.pipeline_prompts import build_kb_context_block

        kb_results = {
            "営業スキーム": ["チャンク1"],
            "業界知識": ["チャンク2", "チャンク3"],
        }
        result = build_kb_context_block(kb_results)
        assert "#### 営業スキーム" in result
        assert "#### 業界知識" in result
        assert "[1] チャンク1" in result
        assert "[1] チャンク2" in result
        assert "[2] チャンク3" in result

    def test_category_with_empty_chunks_skipped(self):
        from app.services.pipeline_prompts import build_kb_context_block

        kb_results = {
            "営業スキーム": ["チャンク1"],
            "空カテゴリ": [],
        }
        result = build_kb_context_block(kb_results)
        assert "#### 営業スキーム" in result
        assert "#### 空カテゴリ" not in result


# =============================================================================
# Prompt Template Validation Tests
# =============================================================================


@pytest.mark.unit
class TestPromptTemplates:
    """Tests for prompt template placeholders."""

    def test_stage1_prompt_has_required_placeholders(self):
        from app.services.pipeline_prompts import STAGE1_SYSTEM_PROMPT

        assert "{meeting_text}" in STAGE1_SYSTEM_PROMPT
        assert "{parsed_json}" in STAGE1_SYSTEM_PROMPT
        assert "{kb_context}" in STAGE1_SYSTEM_PROMPT

    def test_stage2_prompt_has_required_placeholders(self):
        from app.services.pipeline_prompts import STAGE2_SYSTEM_PROMPT

        assert "{stage1_output}" in STAGE2_SYSTEM_PROMPT
        assert "{kb_context}" in STAGE2_SYSTEM_PROMPT
        assert "{product_data}" in STAGE2_SYSTEM_PROMPT
        assert "{simulation_data}" in STAGE2_SYSTEM_PROMPT
        assert "{wage_data}" in STAGE2_SYSTEM_PROMPT
        assert "{publication_data}" in STAGE2_SYSTEM_PROMPT
        assert "{campaign_data}" in STAGE2_SYSTEM_PROMPT

    def test_stage3_prompt_has_required_placeholders(self):
        from app.services.pipeline_prompts import STAGE3_SYSTEM_PROMPT

        assert "{stage1_output}" in STAGE3_SYSTEM_PROMPT
        assert "{stage2_output}" in STAGE3_SYSTEM_PROMPT
        assert "{kb_context}" in STAGE3_SYSTEM_PROMPT

    def test_stage4_prompt_has_required_placeholders(self):
        from app.services.pipeline_prompts import STAGE4_SYSTEM_PROMPT

        assert "{stage1_output}" in STAGE4_SYSTEM_PROMPT
        assert "{stage2_output}" in STAGE4_SYSTEM_PROMPT
        assert "{kb_context}" in STAGE4_SYSTEM_PROMPT
        assert "{catchcopy_count}" in STAGE4_SYSTEM_PROMPT

    def test_stage5_prompt_has_required_placeholders(self):
        from app.services.pipeline_prompts import STAGE5_SYSTEM_PROMPT

        assert "{stage1_output}" in STAGE5_SYSTEM_PROMPT
        assert "{stage2_output}" in STAGE5_SYSTEM_PROMPT
        assert "{stage3_output}" in STAGE5_SYSTEM_PROMPT
        assert "{stage4_output}" in STAGE5_SYSTEM_PROMPT

    def test_stage1_prompt_formats_without_error(self):
        from app.services.pipeline_prompts import STAGE1_SYSTEM_PROMPT

        result = STAGE1_SYSTEM_PROMPT.format(
            meeting_text="テスト議事録",
            parsed_json='{"key": "value"}',
            kb_context="### ナレッジベース情報\nテスト",
        )
        assert "テスト議事録" in result
        assert "JSON" in result

    def test_stage2_prompt_formats_without_error(self):
        from app.services.pipeline_prompts import STAGE2_SYSTEM_PROMPT

        result = STAGE2_SYSTEM_PROMPT.format(
            stage1_output='{"issues": []}',
            kb_context="KB情報",
            product_data='[{"name": "商品A"}]',
            simulation_data="[]",
            wage_data="[]",
            publication_data="[]",
            campaign_data="[]",
        )
        assert "商品A" in result
        assert "前回掲載実績" in result
        assert "適用可能キャンペーン" in result
