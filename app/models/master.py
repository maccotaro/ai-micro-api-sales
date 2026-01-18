"""
Master Data Models (Read-only reference from salesdb)
"""
from datetime import datetime, date
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import (
    Column, String, Text, Boolean, Integer, DECIMAL, DATE,
    TIMESTAMP, Index
)
from sqlalchemy.dialects.postgresql import UUID, JSONB, ARRAY

from app.db.session import SalesDBBase


class Product(SalesDBBase):
    """商品マスタ (Read-only)"""
    __tablename__ = "products"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    name = Column(String(255), nullable=False, unique=True)
    category = Column(String(100), nullable=False)
    base_price = Column(DECIMAL(12, 2))
    price_unit = Column(String(50))
    description = Column(Text)
    document_url = Column(Text)
    features = Column(JSONB, default=list)
    is_active = Column(Boolean, nullable=False, default=True)
    sort_order = Column(Integer, default=0)
    created_at = Column(TIMESTAMP(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at = Column(TIMESTAMP(timezone=True), nullable=False, default=datetime.utcnow)

    __table_args__ = (
        Index("idx_products_category", "category"),
        Index("idx_products_is_active", "is_active"),
        Index("idx_products_name", "name"),
    )


class Campaign(SalesDBBase):
    """キャンペーン情報 (Read-only)"""
    __tablename__ = "campaigns"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    name = Column(String(255), nullable=False)
    description = Column(Text)
    start_date = Column(DATE, nullable=False)
    end_date = Column(DATE, nullable=False)
    discount_rate = Column(DECIMAL(5, 2))
    discount_amount = Column(DECIMAL(12, 2))
    conditions = Column(JSONB, default=dict)
    target_products = Column(ARRAY(UUID(as_uuid=True)), default=list)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(TIMESTAMP(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at = Column(TIMESTAMP(timezone=True), nullable=False, default=datetime.utcnow)

    __table_args__ = (
        Index("idx_campaigns_dates", "start_date", "end_date"),
        Index("idx_campaigns_is_active", "is_active"),
    )


class SimulationParam(SalesDBBase):
    """シミュレーション係数 (Read-only)"""
    __tablename__ = "simulation_params"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    area = Column(String(100), nullable=False)
    industry = Column(String(100), nullable=False)
    pv_coefficient = Column(DECIMAL(8, 4), nullable=False, default=1.0)
    apply_rate = Column(DECIMAL(5, 4), nullable=False, default=0.01)
    conversion_rate = Column(DECIMAL(5, 4))
    seasonal_factor = Column(DECIMAL(5, 2), default=1.0)
    params_metadata = Column(JSONB, default=dict)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(TIMESTAMP(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at = Column(TIMESTAMP(timezone=True), nullable=False, default=datetime.utcnow)

    __table_args__ = (
        Index("idx_simulation_params_area", "area"),
        Index("idx_simulation_params_industry", "industry"),
    )


class WageData(SalesDBBase):
    """地域別時給相場 (Read-only)"""
    __tablename__ = "wage_data"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    area = Column(String(100), nullable=False)
    industry = Column(String(100), nullable=False)
    employment_type = Column(String(50), default="all")
    min_wage = Column(DECIMAL(10, 2), nullable=False)
    avg_wage = Column(DECIMAL(10, 2), nullable=False)
    max_wage = Column(DECIMAL(10, 2))
    effective_date = Column(DATE, nullable=False, default=date.today)
    source = Column(String(255))
    created_at = Column(TIMESTAMP(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at = Column(TIMESTAMP(timezone=True), nullable=False, default=datetime.utcnow)

    __table_args__ = (
        Index("idx_wage_data_area", "area"),
        Index("idx_wage_data_industry", "industry"),
        Index("idx_wage_data_effective_date", "effective_date"),
    )
