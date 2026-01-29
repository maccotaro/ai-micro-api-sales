# ai-micro-api-sales/tests/conftest.py
"""
Pytest fixtures for ai-micro-api-sales tests.

Fixtures:
- mock_settings: Mocked settings for testing
- mock_jwks: Sample JWKS response
- sample_jwt_payload: Sample decoded JWT payload
- mock_db_session: Mock database session
- sample_simulation_request: Sample simulation request data
"""
import sys
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock, AsyncMock
from uuid import uuid4

import pytest

# Ensure app module is importable
sys.path.insert(0, str(Path(__file__).parent.parent))


@pytest.fixture
def mock_settings():
    """Mock settings with test values."""
    settings_mock = MagicMock()
    settings_mock.salesdb_url = "postgresql://postgres:password@localhost:5433/salesdb"
    settings_mock.redis_url = "redis://localhost:6380"
    settings_mock.auth_service_url = "http://localhost:8002"
    settings_mock.admin_service_url = "http://localhost:8003"
    settings_mock.jwks_url = "http://localhost:8002/.well-known/jwks.json"
    settings_mock.rag_service_url = "http://localhost:8010"
    settings_mock.jwt_issuer = "https://test.example.com"
    settings_mock.jwt_audience = "test-api"
    settings_mock.ollama_base_url = "http://localhost:11434"
    settings_mock.openai_api_key = ""
    settings_mock.default_llm_model = "gemma2:9b"
    settings_mock.default_embedding_model = "bge-m3:567m"
    settings_mock.neo4j_uri = "bolt://localhost:7687"
    settings_mock.neo4j_user = "neo4j"
    settings_mock.neo4j_password = "test_password"
    settings_mock.neo4j_database = "neo4j"
    settings_mock.log_level = "DEBUG"
    settings_mock.cors_origins = ["http://localhost:3004"]
    settings_mock.max_meeting_text_length = 50000
    settings_mock.max_proposal_products = 10
    return settings_mock


@pytest.fixture
def mock_jwks():
    """Sample JWKS response for testing."""
    return {
        "keys": [
            {
                "kty": "RSA",
                "use": "sig",
                "kid": "key-1",
                "alg": "RS256",
                "n": "0vx7agoebGcQSuuPiLJXZptN9nndrQmbXEps2aiAFbWhM78LhWx4cbbfAAtVT86zwu1RK7aPFFxuhDR1L6tSoc_BJECPebWKRXjBZCiFV4n3oknjhMstn64tZ_2W-5JsGY4Hc5n9yBXArwl93lqt7_RN5w6Cf0h4QyQ5v-65YGjQR0_FDW2QvzqY368QQMicAtaSqzs8KJZgnYb9c7d0zgdAZHzu6qMQvRL5hajrn1n91CbOpbISD08qNLyrdkt-bFTWhAI4vMQFh6WeZu0fM4lFd2NcRwr3XPksINHaQ-G_xBniIqbw0Ls1jF44-csFCur-kEgU8awapJzKnqDKgw",
                "e": "AQAB"
            }
        ]
    }


@pytest.fixture
def sample_jwt_payload():
    """Sample decoded JWT payload."""
    return {
        "sub": "test-user-123",
        "email": "test@example.com",
        "iss": "https://test.example.com",
        "aud": "test-api",
        "iat": 1704067200,
        "exp": 1704153600,
        "jti": "test-jti-456",
        "scope": "access",
        "roles": ["user", "sales"],
        "tenant_id": "test-tenant",
        "department": "sales",
        "clearance_level": "internal",
    }


@pytest.fixture
def mock_http_credentials():
    """Mock HTTP authorization credentials."""
    credentials = MagicMock()
    credentials.credentials = "mock.jwt.token"
    return credentials


@pytest.fixture
def mock_db_session():
    """Mock database session for testing."""
    session = MagicMock()
    session.commit = MagicMock()
    session.rollback = MagicMock()
    session.close = MagicMock()
    session.query = MagicMock()
    session.add = MagicMock()
    session.delete = MagicMock()
    session.refresh = MagicMock()
    return session


@pytest.fixture
def sample_product():
    """Sample product for testing."""
    product = MagicMock()
    product.id = uuid4()
    product.name = "テスト商品"
    product.category = "求人広告"
    product.base_price = Decimal("50000")
    product.is_active = True
    product.sort_order = 1
    return product


@pytest.fixture
def sample_campaign():
    """Sample campaign for testing."""
    from datetime import date, timedelta

    campaign = MagicMock()
    campaign.id = uuid4()
    campaign.name = "テストキャンペーン"
    campaign.discount_rate = Decimal("10")
    campaign.discount_amount = None
    campaign.is_active = True
    campaign.start_date = date.today() - timedelta(days=30)
    campaign.end_date = date.today() + timedelta(days=30)
    campaign.target_products = None
    return campaign


@pytest.fixture
def sample_simulation_params():
    """Sample simulation parameters."""
    return {
        "pv_coefficient": 1.2,
        "apply_rate": 0.015,
        "conversion_rate": 0.05,
        "seasonal_factor": 1.1,
        "metadata": {"source": "test"},
    }


@pytest.fixture
def sample_wage_data():
    """Sample wage data."""
    return {
        "min_wage": 1100.0,
        "avg_wage": 1350.0,
        "max_wage": 1800.0,
        "effective_date": "2024-01-01",
        "source": "test",
    }


@pytest.fixture
def sample_simulation_request():
    """Sample simulation request."""
    from app.schemas.simulation import SimulationRequest

    return SimulationRequest(
        area="関東",
        industry="飲食",
        product_ids=[uuid4()],
        employee_count=10,
        current_cost=Decimal("100000"),
        target_reduction_rate=Decimal("20"),
    )


@pytest.fixture
def sample_quick_estimate_request():
    """Sample quick estimate request."""
    from app.schemas.simulation import QuickEstimateRequest

    return QuickEstimateRequest(
        area="関東",
        industry="IT",
        product_category="求人広告",
        budget_range="medium",
    )
