"""
Simulation Router

API endpoints for sales simulation and cost estimation.
"""
import logging
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.core.security import require_sales_access
from app.schemas.simulation import (
    SimulationRequest,
    SimulationResult,
    QuickEstimateRequest,
    QuickEstimateResponse,
)
from app.services.simulation_service import SimulationService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/simulation", tags=["simulation"])


@router.post("", response_model=SimulationResult)
async def run_simulation(
    request: SimulationRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_sales_access),
):
    """
    Run a sales simulation.

    This endpoint calculates:
    - Product costs based on area/industry parameters
    - Applicable campaign discounts
    - ROI and payback period (if current cost provided)

    Required fields:
    - **area**: Region/area name
    - **industry**: Industry type
    - **product_ids**: List of product UUIDs to include

    Optional fields for better estimates:
    - **employee_count**: Number of employees
    - **current_cost**: Current spending (for savings calculation)
    - **target_reduction_rate**: Target cost reduction percentage
    """
    simulation_service = SimulationService()
    result = simulation_service.run_simulation(request, db)

    logger.info(
        f"Simulation completed for area={request.area}, "
        f"industry={request.industry}, products={len(request.product_ids)}"
    )
    return result


@router.post("/quick-estimate", response_model=QuickEstimateResponse)
async def quick_estimate(
    request: QuickEstimateRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_sales_access),
):
    """
    Get a quick cost estimate without detailed product selection.

    This is useful for initial conversations when specific products
    haven't been identified yet.

    Returns:
    - Recommended products for the area/industry
    - Price range estimates
    - Regional wage benchmarks
    """
    simulation_service = SimulationService()
    result = simulation_service.quick_estimate(request, db)

    logger.info(f"Quick estimate for area={request.area}, industry={request.industry}")
    return result
