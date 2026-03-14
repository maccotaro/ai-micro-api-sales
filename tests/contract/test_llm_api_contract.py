"""
TDD Red Phase: Contract tests for api-sales -> api-llm internal API.

Verifies that api-llm responses match the JSON Schemas that api-sales
depends on. Uses mocked HTTP calls (no live services needed).
"""
import json
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
    schema_path = SCHEMA_DIR / name
    assert schema_path.exists(), f"Schema file not found: {schema_path}"
    with open(schema_path) as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Sample responses (representing what api-llm currently returns)
# ---------------------------------------------------------------------------

VALID_GENERATE_RESPONSE = {
    "response": "This is the generated text response.",
    "model": "qwen3:8b",
    "total_tokens": 150,
    "provider": "ollama",
    "thinking": None,
}

VALID_CHAT_RESPONSE = {
    "response": "This is the chat response.",
    "model": "qwen3:8b",
    "total_tokens": 200,
    "provider": "ollama",
    "tool_calls": None,
}

VALID_CHAT_RESPONSE_WITH_TOOLS = {
    "response": "",
    "model": "llama3.1:8b",
    "total_tokens": 100,
    "provider": "ollama",
    "tool_calls": [
        {
            "function": {
                "name": "search_products",
                "arguments": {"query": "recruitment ads"},
            }
        }
    ],
}


# ---------------------------------------------------------------------------
# A) Generate endpoint contract tests
# ---------------------------------------------------------------------------

class TestLLMGenerateContract:
    """Contract tests for POST /llm/generate."""

    @pytest.fixture
    def schema(self):
        return load_schema("llm_generate_response.json")

    def test_valid_generate_response_passes_schema(self, schema):
        """A complete generate response should validate."""
        validate(instance=VALID_GENERATE_RESPONSE, schema=schema)

    def test_required_field_response(self, schema):
        """response field is required."""
        resp = {**VALID_GENERATE_RESPONSE}
        del resp["response"]
        with pytest.raises(ValidationError, match="response"):
            validate(instance=resp, schema=schema)

    def test_required_field_model(self, schema):
        """model field is required."""
        resp = {**VALID_GENERATE_RESPONSE}
        del resp["model"]
        with pytest.raises(ValidationError, match="model"):
            validate(instance=resp, schema=schema)

    def test_required_field_provider(self, schema):
        """provider field is required."""
        resp = {**VALID_GENERATE_RESPONSE}
        del resp["provider"]
        with pytest.raises(ValidationError, match="provider"):
            validate(instance=resp, schema=schema)

    def test_total_tokens_can_be_null(self, schema):
        """total_tokens can be null (streaming may not report)."""
        resp = {**VALID_GENERATE_RESPONSE, "total_tokens": None}
        validate(instance=resp, schema=schema)

    def test_thinking_can_be_null(self, schema):
        """thinking field can be null."""
        resp = {**VALID_GENERATE_RESPONSE, "thinking": None}
        validate(instance=resp, schema=schema)

    def test_thinking_can_be_string(self, schema):
        """thinking field can be a string when model supports it."""
        resp = {**VALID_GENERATE_RESPONSE, "thinking": "Let me think about this..."}
        validate(instance=resp, schema=schema)

    def test_response_must_be_string(self, schema):
        """response must be a string, not a number."""
        resp = {**VALID_GENERATE_RESPONSE, "response": 42}
        with pytest.raises(ValidationError):
            validate(instance=resp, schema=schema)

    def test_additive_fields_dont_break_contract(self, schema):
        """New fields from api-llm should not break api-sales."""
        resp = {
            **VALID_GENERATE_RESPONSE,
            "latency_ms": 500,
            "cache_hit": False,
        }
        validate(instance=resp, schema=schema)


# ---------------------------------------------------------------------------
# B) Chat endpoint contract tests
# ---------------------------------------------------------------------------

class TestLLMChatContract:
    """Contract tests for POST /llm/chat."""

    @pytest.fixture
    def schema(self):
        return load_schema("llm_chat_response.json")

    def test_valid_chat_response_passes_schema(self, schema):
        """A complete chat response should validate."""
        validate(instance=VALID_CHAT_RESPONSE, schema=schema)

    def test_valid_chat_response_with_tools_passes_schema(self, schema):
        """Chat response with tool_calls should validate."""
        validate(instance=VALID_CHAT_RESPONSE_WITH_TOOLS, schema=schema)

    def test_required_field_response(self, schema):
        """response field is required."""
        resp = {**VALID_CHAT_RESPONSE}
        del resp["response"]
        with pytest.raises(ValidationError, match="response"):
            validate(instance=resp, schema=schema)

    def test_required_field_model(self, schema):
        """model field is required."""
        resp = {**VALID_CHAT_RESPONSE}
        del resp["model"]
        with pytest.raises(ValidationError, match="model"):
            validate(instance=resp, schema=schema)

    def test_required_field_provider(self, schema):
        """provider field is required."""
        resp = {**VALID_CHAT_RESPONSE}
        del resp["provider"]
        with pytest.raises(ValidationError, match="provider"):
            validate(instance=resp, schema=schema)

    def test_tool_calls_can_be_null(self, schema):
        """tool_calls can be null when no tools are invoked."""
        resp = {**VALID_CHAT_RESPONSE, "tool_calls": None}
        validate(instance=resp, schema=schema)

    def test_tool_calls_must_have_function(self, schema):
        """Each tool_call entry must have a function field."""
        resp = {
            **VALID_CHAT_RESPONSE,
            "tool_calls": [{"invalid_key": "value"}],
        }
        with pytest.raises(ValidationError):
            validate(instance=resp, schema=schema)

    def test_tool_call_function_must_have_name(self, schema):
        """function must have a name field."""
        resp = {
            **VALID_CHAT_RESPONSE,
            "tool_calls": [
                {"function": {"arguments": {"query": "test"}}}
            ],
        }
        with pytest.raises(ValidationError):
            validate(instance=resp, schema=schema)

    def test_tool_call_function_must_have_arguments(self, schema):
        """function must have an arguments field."""
        resp = {
            **VALID_CHAT_RESPONSE,
            "tool_calls": [
                {"function": {"name": "search"}}
            ],
        }
        with pytest.raises(ValidationError):
            validate(instance=resp, schema=schema)


# ---------------------------------------------------------------------------
# C) Versioned endpoint contract (Red Phase)
# ---------------------------------------------------------------------------

class TestLLMVersionedEndpoint:
    """Tests for future versioned api-llm endpoints.

    api-llm currently has no /internal/ prefix (uses /llm/ prefix).
    When versioning is added, it will use /llm/v1/generate etc.
    """

    @pytest.fixture
    def generate_schema(self):
        return load_schema("llm_generate_response.json")

    @patch("httpx.AsyncClient.post")
    @pytest.mark.asyncio
    async def test_versioned_generate_matches_schema(
        self, mock_post, generate_schema
    ):
        """Mocked call to /llm/v1/generate should match schema."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = VALID_GENERATE_RESPONSE
        mock_post.return_value = mock_response

        import httpx

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                "http://api-llm:8012/llm/v1/generate",
                json={
                    "service_name": "api-sales",
                    "task_type": "proposal",
                    "prompt": "test",
                },
                headers={"X-Internal-Secret": "test-secret"},
            )

        assert resp.status_code == 200
        validate(instance=resp.json(), schema=generate_schema)
