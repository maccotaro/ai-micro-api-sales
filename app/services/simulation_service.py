"""
Sales Simulation Service

Calculates cost estimates and ROI based on products and regional data.
"""
import logging
from datetime import date
from decimal import Decimal
from typing import Optional, Dict, Any, List
from uuid import UUID

from sqlalchemy.orm import Session
from sqlalchemy import and_

from app.models.master import Product, Campaign, SimulationParam, WageData
from app.schemas.simulation import (
    SimulationRequest,
    SimulationResult,
    ProductSimulation,
    QuickEstimateRequest,
    QuickEstimateResponse,
)

logger = logging.getLogger(__name__)


class SimulationService:
    """Sales simulation service."""

    def run_simulation(
        self,
        request: SimulationRequest,
        db: Session,
    ) -> SimulationResult:
        """
        Run a sales simulation.

        Args:
            request: Simulation request parameters
            db: Database session

        Returns:
            SimulationResult with cost estimates and ROI
        """
        logger.info(f"Running simulation for area={request.area}, industry={request.industry}")

        # Get simulation parameters
        sim_params = self._get_simulation_params(request.area, request.industry, db)

        # Get wage data
        wage_data = self._get_wage_data(request.area, request.industry, db)

        # Get products
        products = self._get_products(request.product_ids, db)

        # Calculate product simulations
        product_simulations = []
        total_cost = Decimal("0")

        for product in products:
            sim = self._calculate_product_simulation(
                product,
                sim_params,
                wage_data,
                request,
            )
            product_simulations.append(sim)
            total_cost += sim.estimated_cost

        # Get applicable campaigns
        campaigns = self._get_applicable_campaigns(request.product_ids, db)
        campaign_discount = self._calculate_campaign_discount(campaigns, total_cost)

        # Calculate totals
        total_savings = None
        total_roi = None

        if request.current_cost and request.current_cost > 0:
            final_cost = total_cost - campaign_discount
            total_savings = request.current_cost - final_cost
            if final_cost > 0:
                total_roi = (total_savings / final_cost) * 100

        result = SimulationResult(
            area=request.area,
            industry=request.industry,
            product_ids=request.product_ids,
            simulation_params=sim_params,
            wage_data=wage_data,
            product_simulations=product_simulations,
            total_estimated_cost=total_cost,
            total_estimated_savings=total_savings,
            total_roi=total_roi,
            applicable_campaigns=[
                {
                    "id": str(c.id),
                    "name": c.name,
                    "discount_rate": float(c.discount_rate) if c.discount_rate else None,
                    "discount_amount": float(c.discount_amount) if c.discount_amount else None,
                }
                for c in campaigns
            ],
            campaign_discount=campaign_discount,
            final_cost=total_cost - campaign_discount,
            confidence_level=self._determine_confidence(sim_params, wage_data),
            assumptions=self._get_assumptions(sim_params, wage_data, request),
        )

        return result

    def quick_estimate(
        self,
        request: QuickEstimateRequest,
        db: Session,
    ) -> QuickEstimateResponse:
        """
        Get a quick estimate without detailed calculation.

        Args:
            request: Quick estimate request
            db: Database session

        Returns:
            QuickEstimateResponse with price ranges
        """
        # Get wage data for benchmarking
        wage_data = self._get_wage_data(request.area, request.industry, db)
        avg_wage = Decimal(wage_data.get("avg_wage", 1200)) if wage_data else Decimal("1200")

        # Get products by category if specified
        query = db.query(Product).filter(Product.is_active == True)
        if request.product_category:
            query = query.filter(Product.category == request.product_category)

        products = query.order_by(Product.sort_order).limit(10).all()

        # Calculate price ranges
        prices = [p.base_price for p in products if p.base_price]
        if prices:
            min_price = min(prices)
            max_price = max(prices)
            avg_price = sum(prices) / len(prices)
        else:
            # Default estimates based on budget range
            if request.budget_range == "low":
                min_price, max_price, avg_price = Decimal("10000"), Decimal("50000"), Decimal("30000")
            elif request.budget_range == "high":
                min_price, max_price, avg_price = Decimal("200000"), Decimal("1000000"), Decimal("500000")
            else:  # medium
                min_price, max_price, avg_price = Decimal("50000"), Decimal("200000"), Decimal("100000")

        return QuickEstimateResponse(
            area=request.area,
            industry=request.industry,
            recommended_products=[
                {
                    "id": str(p.id),
                    "name": p.name,
                    "category": p.category,
                    "base_price": float(p.base_price) if p.base_price else None,
                }
                for p in products[:5]
            ],
            min_estimate=min_price,
            max_estimate=max_price,
            typical_estimate=avg_price,
            area_wage_avg=avg_wage,
            industry_benchmark={
                "typical_spend_per_employee": float(avg_price / 10) if avg_price else None,
                "wage_index": float(avg_wage / 1200),  # Normalized to national average
            } if wage_data else None,
        )

    def _get_simulation_params(
        self,
        area: Optional[str],
        industry: Optional[str],
        db: Session,
    ) -> Dict[str, Any]:
        """Get simulation parameters for area and industry."""
        # Return default if area/industry not specified
        if not area or not industry:
            return {
                "pv_coefficient": 1.0,
                "apply_rate": 0.01,
                "conversion_rate": None,
                "seasonal_factor": 1.0,
                "metadata": {},
            }

        param = db.query(SimulationParam).filter(
            and_(
                SimulationParam.area == area,
                SimulationParam.industry == industry,
                SimulationParam.is_active == True,
            )
        ).first()

        if param:
            return {
                "pv_coefficient": float(param.pv_coefficient),
                "apply_rate": float(param.apply_rate),
                "conversion_rate": float(param.conversion_rate) if param.conversion_rate else None,
                "seasonal_factor": float(param.seasonal_factor),
                "metadata": param.params_metadata or {},
            }

        # Default parameters
        return {
            "pv_coefficient": 1.0,
            "apply_rate": 0.01,
            "conversion_rate": None,
            "seasonal_factor": 1.0,
            "metadata": {},
        }

    def _get_wage_data(
        self,
        area: Optional[str],
        industry: Optional[str],
        db: Session,
    ) -> Optional[Dict[str, Any]]:
        """Get wage data for area and industry."""
        # Return None if area/industry not specified
        if not area or not industry:
            return None

        wage = db.query(WageData).filter(
            and_(
                WageData.area == area,
                WageData.industry == industry,
            )
        ).order_by(WageData.effective_date.desc()).first()

        if wage:
            return {
                "min_wage": float(wage.min_wage),
                "avg_wage": float(wage.avg_wage),
                "max_wage": float(wage.max_wage) if wage.max_wage else None,
                "effective_date": wage.effective_date.isoformat(),
                "source": wage.source,
            }

        return None

    def _get_products(
        self,
        product_ids: List[UUID],
        db: Session,
    ) -> List[Product]:
        """Get products by IDs."""
        if not product_ids:
            return []

        return db.query(Product).filter(
            Product.id.in_(product_ids)
        ).all()

    def _calculate_product_simulation(
        self,
        product: Product,
        sim_params: Dict[str, Any],
        wage_data: Optional[Dict[str, Any]],
        request: SimulationRequest,
    ) -> ProductSimulation:
        """Calculate simulation for a single product."""
        base_price = product.base_price or Decimal("0")

        # Apply simulation coefficients
        pv_coef = Decimal(str(sim_params.get("pv_coefficient", 1.0)))
        seasonal = Decimal(str(sim_params.get("seasonal_factor", 1.0)))

        estimated_cost = base_price * pv_coef * seasonal

        # Calculate monthly/annual if employee count provided
        monthly_cost = None
        annual_cost = None
        if request.employee_count:
            # Assume per-employee pricing
            estimated_cost = estimated_cost * request.employee_count
            monthly_cost = estimated_cost
            annual_cost = estimated_cost * 12

        # Calculate savings and ROI
        estimated_savings = None
        roi_estimate = None
        payback_months = None

        if request.current_cost and request.target_reduction_rate:
            target_savings = request.current_cost * (request.target_reduction_rate / 100)
            estimated_savings = min(target_savings, request.current_cost * Decimal("0.3"))  # Cap at 30%

            if estimated_cost > 0:
                roi_estimate = (estimated_savings / estimated_cost) * 100
                if monthly_cost and monthly_cost > 0:
                    payback_months = int(estimated_cost / (estimated_savings / 12))

        return ProductSimulation(
            product_id=product.id,
            product_name=product.name,
            category=product.category,
            estimated_cost=estimated_cost,
            monthly_cost=monthly_cost,
            annual_cost=annual_cost,
            estimated_savings=estimated_savings,
            roi_estimate=roi_estimate,
            payback_months=payback_months,
            calculation_basis={
                "base_price": float(base_price),
                "pv_coefficient": float(pv_coef),
                "seasonal_factor": float(seasonal),
                "employee_count": request.employee_count,
            },
        )

    def _get_applicable_campaigns(
        self,
        product_ids: List[UUID],
        db: Session,
    ) -> List[Campaign]:
        """Get applicable campaigns."""
        today = date.today()

        campaigns = db.query(Campaign).filter(
            and_(
                Campaign.is_active == True,
                Campaign.start_date <= today,
                Campaign.end_date >= today,
            )
        ).all()

        applicable = []
        for campaign in campaigns:
            if not campaign.target_products:
                applicable.append(campaign)
            elif any(pid in (campaign.target_products or []) for pid in product_ids):
                applicable.append(campaign)

        return applicable

    def _calculate_campaign_discount(
        self,
        campaigns: List[Campaign],
        total_cost: Decimal,
    ) -> Decimal:
        """Calculate total campaign discount."""
        discount = Decimal("0")

        for campaign in campaigns:
            if campaign.discount_rate:
                discount += total_cost * (campaign.discount_rate / 100)
            if campaign.discount_amount:
                discount += campaign.discount_amount

        return discount

    def _determine_confidence(
        self,
        sim_params: Dict[str, Any],
        wage_data: Optional[Dict[str, Any]],
    ) -> str:
        """Determine confidence level of simulation."""
        if sim_params.get("metadata") and wage_data:
            return "high"
        elif sim_params.get("pv_coefficient") != 1.0 or wage_data:
            return "medium"
        return "low"

    def _get_assumptions(
        self,
        sim_params: Dict[str, Any],
        wage_data: Optional[Dict[str, Any]],
        request: SimulationRequest,
    ) -> List[str]:
        """Get list of assumptions made in simulation."""
        assumptions = []

        if sim_params.get("pv_coefficient") == 1.0:
            assumptions.append("地域係数はデフォルト値（1.0）を使用")

        if not wage_data:
            assumptions.append("地域時給データなし、全国平均を使用")

        if not request.employee_count:
            assumptions.append("従業員数未指定、単価ベースの試算")

        if not request.current_cost:
            assumptions.append("現在のコスト未指定、削減効果は試算不可")

        return assumptions
