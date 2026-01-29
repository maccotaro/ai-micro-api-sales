# ai-micro-api-sales/tests/unit/services/test_simulation_service.py
"""
Unit tests for app.services.simulation_service module.

Tests:
- Simulation parameter retrieval
- Wage data retrieval
- Product simulation calculations
- Campaign discount calculations
- Confidence level determination
"""
from decimal import Decimal
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest


# =============================================================================
# SimulationService Basic Tests
# =============================================================================


@pytest.mark.unit
class TestSimulationServiceBasic:
    """Basic tests for SimulationService."""

    def test_service_initialization(self):
        """SimulationService should initialize correctly."""
        from app.services.simulation_service import SimulationService

        service = SimulationService()
        assert service is not None


# =============================================================================
# _get_simulation_params Tests
# =============================================================================


@pytest.mark.unit
class TestGetSimulationParams:
    """Tests for _get_simulation_params method."""

    def test_returns_defaults_when_no_area_industry(self, mock_db_session):
        """Should return default params when area/industry not specified."""
        from app.services.simulation_service import SimulationService

        service = SimulationService()
        result = service._get_simulation_params(None, None, mock_db_session)

        assert result["pv_coefficient"] == 1.0
        assert result["apply_rate"] == 0.01
        assert result["conversion_rate"] is None
        assert result["seasonal_factor"] == 1.0
        assert result["metadata"] == {}

    def test_returns_params_from_database(self, mock_db_session):
        """Should return params from database when found."""
        from app.services.simulation_service import SimulationService

        mock_param = MagicMock()
        mock_param.pv_coefficient = Decimal("1.5")
        mock_param.apply_rate = Decimal("0.02")
        mock_param.conversion_rate = Decimal("0.05")
        mock_param.seasonal_factor = Decimal("1.2")
        mock_param.params_metadata = {"source": "test"}

        mock_query = MagicMock()
        mock_query.filter.return_value.first.return_value = mock_param
        mock_db_session.query.return_value = mock_query

        service = SimulationService()
        result = service._get_simulation_params("関東", "飲食", mock_db_session)

        assert result["pv_coefficient"] == 1.5
        assert result["apply_rate"] == 0.02
        assert result["conversion_rate"] == 0.05
        assert result["seasonal_factor"] == 1.2
        assert result["metadata"] == {"source": "test"}

    def test_returns_defaults_when_not_found(self, mock_db_session):
        """Should return defaults when params not found in database."""
        from app.services.simulation_service import SimulationService

        mock_query = MagicMock()
        mock_query.filter.return_value.first.return_value = None
        mock_db_session.query.return_value = mock_query

        service = SimulationService()
        result = service._get_simulation_params("未知", "未知", mock_db_session)

        assert result["pv_coefficient"] == 1.0
        assert result["apply_rate"] == 0.01


# =============================================================================
# _get_wage_data Tests
# =============================================================================


@pytest.mark.unit
class TestGetWageData:
    """Tests for _get_wage_data method."""

    def test_returns_none_when_no_area_industry(self, mock_db_session):
        """Should return None when area/industry not specified."""
        from app.services.simulation_service import SimulationService

        service = SimulationService()
        result = service._get_wage_data(None, None, mock_db_session)

        assert result is None

    def test_returns_wage_data_from_database(self, mock_db_session):
        """Should return wage data from database when found."""
        from datetime import date
        from app.services.simulation_service import SimulationService

        mock_wage = MagicMock()
        mock_wage.min_wage = Decimal("1100")
        mock_wage.avg_wage = Decimal("1350")
        mock_wage.max_wage = Decimal("1800")
        mock_wage.effective_date = date(2024, 1, 1)
        mock_wage.source = "厚生労働省"

        mock_query = MagicMock()
        mock_query.filter.return_value.order_by.return_value.first.return_value = mock_wage
        mock_db_session.query.return_value = mock_query

        service = SimulationService()
        result = service._get_wage_data("関東", "飲食", mock_db_session)

        assert result["min_wage"] == 1100.0
        assert result["avg_wage"] == 1350.0
        assert result["max_wage"] == 1800.0
        assert result["source"] == "厚生労働省"

    def test_returns_none_when_not_found(self, mock_db_session):
        """Should return None when wage data not found."""
        from app.services.simulation_service import SimulationService

        mock_query = MagicMock()
        mock_query.filter.return_value.order_by.return_value.first.return_value = None
        mock_db_session.query.return_value = mock_query

        service = SimulationService()
        result = service._get_wage_data("未知", "未知", mock_db_session)

        assert result is None


# =============================================================================
# _get_products Tests
# =============================================================================


@pytest.mark.unit
class TestGetProducts:
    """Tests for _get_products method."""

    def test_returns_empty_list_for_empty_ids(self, mock_db_session):
        """Should return empty list when no product IDs provided."""
        from app.services.simulation_service import SimulationService

        service = SimulationService()
        result = service._get_products([], mock_db_session)

        assert result == []

    def test_returns_products_from_database(self, mock_db_session, sample_product):
        """Should return products from database."""
        from app.services.simulation_service import SimulationService

        mock_query = MagicMock()
        mock_query.filter.return_value.all.return_value = [sample_product]
        mock_db_session.query.return_value = mock_query

        service = SimulationService()
        result = service._get_products([sample_product.id], mock_db_session)

        assert len(result) == 1
        assert result[0] == sample_product


# =============================================================================
# _calculate_product_simulation Tests
# =============================================================================


@pytest.mark.unit
class TestCalculateProductSimulation:
    """Tests for _calculate_product_simulation method."""

    def test_basic_calculation(self, sample_product, sample_simulation_params):
        """Should calculate basic product simulation."""
        from app.services.simulation_service import SimulationService
        from app.schemas.simulation import SimulationRequest

        request = SimulationRequest(
            area="関東",
            industry="飲食",
            product_ids=[sample_product.id],
        )

        service = SimulationService()
        result = service._calculate_product_simulation(
            sample_product,
            sample_simulation_params,
            None,
            request,
        )

        assert result.product_id == sample_product.id
        assert result.product_name == sample_product.name
        assert result.category == sample_product.category
        # 50000 * 1.2 * 1.1 = 66000
        expected_cost = Decimal("50000") * Decimal("1.2") * Decimal("1.1")
        assert result.estimated_cost == expected_cost

    def test_calculation_with_employee_count(self, sample_product, sample_simulation_params):
        """Should multiply by employee count when provided."""
        from app.services.simulation_service import SimulationService
        from app.schemas.simulation import SimulationRequest

        request = SimulationRequest(
            area="関東",
            industry="飲食",
            product_ids=[sample_product.id],
            employee_count=10,
        )

        service = SimulationService()
        result = service._calculate_product_simulation(
            sample_product,
            sample_simulation_params,
            None,
            request,
        )

        # (50000 * 1.2 * 1.1) * 10 = 660000
        base_cost = Decimal("50000") * Decimal("1.2") * Decimal("1.1")
        expected_cost = base_cost * 10
        assert result.estimated_cost == expected_cost
        assert result.monthly_cost == expected_cost
        assert result.annual_cost == expected_cost * 12

    def test_calculation_with_savings(self, sample_product, sample_simulation_params):
        """Should calculate savings when current_cost and target_reduction provided."""
        from app.services.simulation_service import SimulationService
        from app.schemas.simulation import SimulationRequest

        request = SimulationRequest(
            area="関東",
            industry="飲食",
            product_ids=[sample_product.id],
            current_cost=Decimal("100000"),
            target_reduction_rate=Decimal("20"),
        )

        service = SimulationService()
        result = service._calculate_product_simulation(
            sample_product,
            sample_simulation_params,
            None,
            request,
        )

        # Target savings: 100000 * 0.2 = 20000, capped at 30% = 30000
        # So estimated_savings should be min(20000, 30000) = 20000
        assert result.estimated_savings is not None
        assert result.estimated_savings == Decimal("20000")


# =============================================================================
# _calculate_campaign_discount Tests
# =============================================================================


@pytest.mark.unit
class TestCalculateCampaignDiscount:
    """Tests for _calculate_campaign_discount method."""

    def test_no_campaigns(self):
        """Should return zero for no campaigns."""
        from app.services.simulation_service import SimulationService

        service = SimulationService()
        result = service._calculate_campaign_discount([], Decimal("100000"))

        assert result == Decimal("0")

    def test_discount_rate_campaign(self, sample_campaign):
        """Should calculate discount from discount_rate."""
        from app.services.simulation_service import SimulationService

        service = SimulationService()
        result = service._calculate_campaign_discount([sample_campaign], Decimal("100000"))

        # 100000 * (10 / 100) = 10000
        assert result == Decimal("10000")

    def test_discount_amount_campaign(self):
        """Should calculate discount from discount_amount."""
        from app.services.simulation_service import SimulationService

        campaign = MagicMock()
        campaign.discount_rate = None
        campaign.discount_amount = Decimal("5000")

        service = SimulationService()
        result = service._calculate_campaign_discount([campaign], Decimal("100000"))

        assert result == Decimal("5000")

    def test_combined_discounts(self, sample_campaign):
        """Should combine multiple campaign discounts."""
        from app.services.simulation_service import SimulationService

        campaign2 = MagicMock()
        campaign2.discount_rate = None
        campaign2.discount_amount = Decimal("3000")

        service = SimulationService()
        result = service._calculate_campaign_discount(
            [sample_campaign, campaign2], Decimal("100000")
        )

        # 10000 (10% of 100000) + 3000 = 13000
        assert result == Decimal("13000")


# =============================================================================
# _determine_confidence Tests
# =============================================================================


@pytest.mark.unit
class TestDetermineConfidence:
    """Tests for _determine_confidence method."""

    def test_high_confidence(self, sample_simulation_params, sample_wage_data):
        """Should return high confidence with metadata and wage data."""
        from app.services.simulation_service import SimulationService

        service = SimulationService()
        result = service._determine_confidence(sample_simulation_params, sample_wage_data)

        assert result == "high"

    def test_medium_confidence_with_pv(self, sample_wage_data):
        """Should return medium confidence with non-default pv_coefficient."""
        from app.services.simulation_service import SimulationService

        params = {
            "pv_coefficient": 1.5,
            "apply_rate": 0.01,
            "metadata": {},
        }

        service = SimulationService()
        result = service._determine_confidence(params, sample_wage_data)

        assert result == "medium"

    def test_medium_confidence_with_wage_only(self, sample_wage_data):
        """Should return medium confidence with wage data only."""
        from app.services.simulation_service import SimulationService

        params = {
            "pv_coefficient": 1.0,
            "apply_rate": 0.01,
            "metadata": {},
        }

        service = SimulationService()
        result = service._determine_confidence(params, sample_wage_data)

        assert result == "medium"

    def test_low_confidence(self):
        """Should return low confidence with defaults only."""
        from app.services.simulation_service import SimulationService

        params = {
            "pv_coefficient": 1.0,
            "apply_rate": 0.01,
            "metadata": {},
        }

        service = SimulationService()
        result = service._determine_confidence(params, None)

        assert result == "low"


# =============================================================================
# _get_assumptions Tests
# =============================================================================


@pytest.mark.unit
class TestGetAssumptions:
    """Tests for _get_assumptions method."""

    def test_assumption_default_pv(self, sample_wage_data, sample_simulation_request):
        """Should add assumption for default pv_coefficient."""
        from app.services.simulation_service import SimulationService

        params = {"pv_coefficient": 1.0}

        service = SimulationService()
        result = service._get_assumptions(params, sample_wage_data, sample_simulation_request)

        assert any("地域係数はデフォルト" in a for a in result)

    def test_assumption_no_wage_data(self, sample_simulation_request):
        """Should add assumption when wage data is missing."""
        from app.services.simulation_service import SimulationService

        params = {"pv_coefficient": 1.5}

        service = SimulationService()
        result = service._get_assumptions(params, None, sample_simulation_request)

        assert any("地域時給データなし" in a for a in result)

    def test_assumption_no_employee_count(self, sample_wage_data):
        """Should add assumption when employee count is missing."""
        from app.services.simulation_service import SimulationService
        from app.schemas.simulation import SimulationRequest

        request = SimulationRequest(
            area="関東",
            industry="飲食",
            product_ids=[uuid4()],
            # No employee_count
        )
        params = {"pv_coefficient": 1.5}

        service = SimulationService()
        result = service._get_assumptions(params, sample_wage_data, request)

        assert any("従業員数未指定" in a for a in result)

    def test_assumption_no_current_cost(self, sample_wage_data):
        """Should add assumption when current cost is missing."""
        from app.services.simulation_service import SimulationService
        from app.schemas.simulation import SimulationRequest

        request = SimulationRequest(
            area="関東",
            industry="飲食",
            product_ids=[uuid4()],
            employee_count=10,
            # No current_cost
        )
        params = {"pv_coefficient": 1.5}

        service = SimulationService()
        result = service._get_assumptions(params, sample_wage_data, request)

        assert any("現在のコスト未指定" in a for a in result)
