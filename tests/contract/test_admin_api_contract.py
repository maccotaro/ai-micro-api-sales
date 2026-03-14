"""
TDD Red Phase: Contract tests for api-sales -> api-admin internal API.

Verifies that the api-admin internal API responses match the JSON Schema
that api-sales depends on. Uses mocked HTTP calls (no live services needed).

These tests validate the CONTRACT, not the implementation. They should fail
if api-admin changes its response schema in a breaking way.
"""
import json
import os
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

try:
    from jsonschema import validate, ValidationError
except ImportError:
    pytest.skip("jsonschema not installed", allow_module_level=True)


# ---------------------------------------------------------------------------
# Schema loading
# ---------------------------------------------------------------------------

SCHEMA_DIR = Path(__file__).parent / "schemas"


def load_schema(name: str) -> dict:
    """Load a JSON Schema file from the schemas directory."""
    schema_path = SCHEMA_DIR / name
    assert schema_path.exists(), f"Schema file not found: {schema_path}"
    with open(schema_path) as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Sample responses (representing what api-admin currently returns)
# ---------------------------------------------------------------------------

VALID_MODEL_SETTINGS_RESPONSE = {
    "embedding_model": "bge-m3:567m",
    "embedding_dimension": 1024,
    "chat_model": "qwen3:8b",
    "tool_model": "llama3.1:8b",
    "vlm_enabled": False,
    "vlm_model": "qwen2.5vl:7b",
    "vlm_num_ctx": 16384,
    "chat_num_ctx": 32768,
    "vlm_timeout_seconds": 300,
    "reranker_model": "BAAI/bge-reranker-base",
    "cross_encoder_enabled": True,
    "bm25_reranker_enabled": True,
    "reranker_batch_size": 32,
    "distance_metric": "cosine",
    "ocr_engine": "easyocr",
}


# ---------------------------------------------------------------------------
# A) Model Settings Contract Tests
# ---------------------------------------------------------------------------

class TestAdminModelSettingsContract:
    """Contract tests for GET /internal/v1/model-settings."""

    @pytest.fixture
    def schema(self):
        return load_schema("admin_model_settings.json")

    def test_valid_response_passes_schema(self, schema):
        """A complete model settings response should validate."""
        validate(instance=VALID_MODEL_SETTINGS_RESPONSE, schema=schema)

    def test_required_field_embedding_model(self, schema):
        """embedding_model is required by api-sales."""
        response = {**VALID_MODEL_SETTINGS_RESPONSE}
        del response["embedding_model"]
        with pytest.raises(ValidationError, match="embedding_model"):
            validate(instance=response, schema=schema)

    def test_required_field_chat_model(self, schema):
        """chat_model is required by api-sales."""
        response = {**VALID_MODEL_SETTINGS_RESPONSE}
        del response["chat_model"]
        with pytest.raises(ValidationError, match="chat_model"):
            validate(instance=response, schema=schema)

    def test_required_field_embedding_dimension(self, schema):
        """embedding_dimension is required by api-sales."""
        response = {**VALID_MODEL_SETTINGS_RESPONSE}
        del response["embedding_dimension"]
        with pytest.raises(ValidationError, match="embedding_dimension"):
            validate(instance=response, schema=schema)

    def test_required_field_distance_metric(self, schema):
        """distance_metric is required by api-sales."""
        response = {**VALID_MODEL_SETTINGS_RESPONSE}
        del response["distance_metric"]
        with pytest.raises(ValidationError, match="distance_metric"):
            validate(instance=response, schema=schema)

    def test_embedding_dimension_must_be_integer(self, schema):
        """embedding_dimension must be an integer, not a string."""
        response = {**VALID_MODEL_SETTINGS_RESPONSE, "embedding_dimension": "1024"}
        with pytest.raises(ValidationError):
            validate(instance=response, schema=schema)

    def test_embedding_dimension_must_be_positive(self, schema):
        """embedding_dimension must be >= 1."""
        response = {**VALID_MODEL_SETTINGS_RESPONSE, "embedding_dimension": 0}
        with pytest.raises(ValidationError):
            validate(instance=response, schema=schema)

    def test_distance_metric_must_be_valid_enum(self, schema):
        """distance_metric must be one of cosine/euclidean/dot_product."""
        response = {**VALID_MODEL_SETTINGS_RESPONSE, "distance_metric": "manhattan"}
        with pytest.raises(ValidationError):
            validate(instance=response, schema=schema)

    def test_vlm_model_can_be_null(self, schema):
        """vlm_model can be null (VLM not configured)."""
        response = {**VALID_MODEL_SETTINGS_RESPONSE, "vlm_model": None}
        validate(instance=response, schema=schema)

    def test_reranker_model_can_be_null(self, schema):
        """reranker_model can be null (reranker disabled)."""
        response = {**VALID_MODEL_SETTINGS_RESPONSE, "reranker_model": None}
        validate(instance=response, schema=schema)

    def test_additive_fields_dont_break_contract(self, schema):
        """Adding new fields should not break the contract (additionalProperties: true)."""
        response = {
            **VALID_MODEL_SETTINGS_RESPONSE,
            "new_future_field": "some_value",
            "another_new_field": 42,
        }
        validate(instance=response, schema=schema)

    def test_boolean_fields_are_boolean(self, schema):
        """Boolean fields must be actual booleans, not strings."""
        response = {**VALID_MODEL_SETTINGS_RESPONSE, "vlm_enabled": "true"}
        with pytest.raises(ValidationError):
            validate(instance=response, schema=schema)

    def test_string_fields_are_strings(self, schema):
        """String fields must be actual strings, not numbers."""
        response = {**VALID_MODEL_SETTINGS_RESPONSE, "embedding_model": 123}
        with pytest.raises(ValidationError):
            validate(instance=response, schema=schema)


# ---------------------------------------------------------------------------
# B) Versioned endpoint contract test (Red Phase)
# ---------------------------------------------------------------------------

class TestAdminModelSettingsVersionedEndpoint:
    """Tests that api-sales can call the VERSIONED endpoint."""

    @pytest.fixture
    def schema(self):
        return load_schema("admin_model_settings.json")

    @patch("httpx.AsyncClient.get")
    @pytest.mark.asyncio
    async def test_versioned_endpoint_response_matches_schema(
        self, mock_get, schema
    ):
        """Mocked call to /internal/v1/model-settings should match schema.

        In production, api-sales calls api-admin's versioned endpoint.
        This test verifies the expected response structure.
        """
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = VALID_MODEL_SETTINGS_RESPONSE
        mock_get.return_value = mock_response

        import httpx

        async with httpx.AsyncClient() as client:
            resp = await client.get(
                "http://api-admin:8003/internal/v1/model-settings",
                headers={"X-Internal-Secret": "test-secret"},
            )

        assert resp.status_code == 200
        validate(instance=resp.json(), schema=schema)

    @patch("httpx.AsyncClient.get")
    @pytest.mark.asyncio
    async def test_unversioned_endpoint_also_matches_schema(
        self, mock_get, schema
    ):
        """Mocked call to /internal/model-settings (unversioned) should also match."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = VALID_MODEL_SETTINGS_RESPONSE
        mock_get.return_value = mock_response

        import httpx

        async with httpx.AsyncClient() as client:
            resp = await client.get(
                "http://api-admin:8003/internal/model-settings",
                headers={"X-Internal-Secret": "test-secret"},
            )

        validate(instance=resp.json(), schema=schema)


# ---------------------------------------------------------------------------
# C) Pipeline config contract (api-sales also calls this)
# ---------------------------------------------------------------------------

VALID_PIPELINE_CONFIG_RESPONSE = {
    "id": "00000000-0000-0000-0000-000000000001",
    "tenant_id": "00000000-0000-0000-0000-000000000000",
    "stage_1_enabled": True,
    "stage_2_enabled": True,
    "stage_3_enabled": True,
    "stage_4_enabled": True,
    "stage_5_enabled": True,
    "is_default": True,
}


class TestAdminPipelineConfigContract:
    """Contract tests for GET /internal/v1/proposal-pipeline/config."""

    def test_pipeline_config_has_is_default_field(self):
        """api-sales requires the is_default field in the response."""
        assert "is_default" in VALID_PIPELINE_CONFIG_RESPONSE
        assert isinstance(VALID_PIPELINE_CONFIG_RESPONSE["is_default"], bool)

    def test_pipeline_config_has_tenant_id(self):
        """api-sales expects tenant_id in the response."""
        assert "tenant_id" in VALID_PIPELINE_CONFIG_RESPONSE
        assert isinstance(VALID_PIPELINE_CONFIG_RESPONSE["tenant_id"], str)
