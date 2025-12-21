"""
Sales Simulation Schemas
"""
from decimal import Decimal
from typing import Optional, List, Dict, Any
from uuid import UUID

from pydantic import BaseModel, Field


class SimulationRequest(BaseModel):
    """シミュレーションリクエスト"""
    area: Optional[str] = Field(None, max_length=100)
    industry: Optional[str] = Field(None, max_length=100)
    product_ids: List[UUID] = Field(default_factory=list)

    # オプション入力
    employee_count: Optional[int] = Field(None, ge=1)
    current_cost: Optional[Decimal] = None
    target_reduction_rate: Optional[Decimal] = Field(None, ge=0, le=100)

    # カスタムパラメータ
    custom_params: Optional[Dict[str, Any]] = None


class ProductSimulation(BaseModel):
    """商品別シミュレーション結果"""
    product_id: UUID
    product_name: str
    category: str

    # コスト試算
    estimated_cost: Decimal
    monthly_cost: Optional[Decimal] = None
    annual_cost: Optional[Decimal] = None

    # 効果試算
    estimated_savings: Optional[Decimal] = None
    roi_estimate: Optional[Decimal] = None
    payback_months: Optional[int] = None

    # 詳細
    calculation_basis: Dict[str, Any] = Field(default_factory=dict)


class SimulationResult(BaseModel):
    """シミュレーション結果"""
    # 入力情報
    area: Optional[str] = None
    industry: Optional[str] = None
    product_ids: List[UUID] = Field(default_factory=list)

    # 地域・業界パラメータ
    simulation_params: Dict[str, Any] = Field(default_factory=dict)
    wage_data: Optional[Dict[str, Any]] = None

    # 商品別結果
    product_simulations: List[ProductSimulation] = Field(default_factory=list)

    # 総合結果
    total_estimated_cost: Decimal
    total_estimated_savings: Optional[Decimal] = None
    total_roi: Optional[Decimal] = None

    # 適用キャンペーン
    applicable_campaigns: List[Dict[str, Any]] = Field(default_factory=list)
    campaign_discount: Optional[Decimal] = None
    final_cost: Decimal

    # 信頼度
    confidence_level: str = Field(default="medium", pattern="^(high|medium|low)$")
    assumptions: List[str] = Field(default_factory=list)


class QuickEstimateRequest(BaseModel):
    """簡易見積もりリクエスト"""
    area: Optional[str] = Field(None, max_length=100)
    industry: Optional[str] = Field(None, max_length=100)
    product_category: Optional[str] = None
    budget_range: Optional[str] = Field(None, pattern="^(low|medium|high)$")


class QuickEstimateResponse(BaseModel):
    """簡易見積もりレスポンス"""
    area: Optional[str] = None
    industry: Optional[str] = None

    # 推奨商品
    recommended_products: List[Dict[str, Any]] = Field(default_factory=list)

    # 価格帯
    min_estimate: Decimal
    max_estimate: Decimal
    typical_estimate: Decimal

    # 地域相場
    area_wage_avg: Optional[Decimal] = None
    industry_benchmark: Optional[Dict[str, Any]] = None
