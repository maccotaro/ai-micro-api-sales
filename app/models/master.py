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


class MediaPricing(SalesDBBase):
    """媒体別料金表 (Read-only) - 商材提案RAG用"""
    __tablename__ = "media_pricing"

    id = Column(Integer, primary_key=True, autoincrement=True)
    media_name = Column(String(100), nullable=False)
    category_large = Column(String(100))
    category_medium = Column(String(100))
    product_name = Column(String(255), nullable=False)
    listing_rank = Column(String(100))
    location_count = Column(Integer)
    listing_period = Column(String(100))
    quantity = Column(Integer)
    price_type = Column(String(50))
    area = Column(String(100))
    price = Column(DECIMAL(12, 2))
    rate = Column(Integer)
    rate_basis = Column(String(100))
    application_start_date = Column(DATE)
    application_end_date = Column(DATE)
    remarks = Column(Text)

    __table_args__ = (
        Index("idx_media_pricing_media_name", "media_name"),
        Index("idx_media_pricing_area", "area"),
        Index("idx_media_pricing_product_name", "product_name"),
    )


class SeasonalTrend(SalesDBBase):
    """月別・地域別・業種別の採用トレンド (Read-only)"""
    __tablename__ = "seasonal_trends"

    id = Column(Integer, primary_key=True, autoincrement=True)
    month = Column(Integer, nullable=False)
    area = Column(String(100), nullable=False, default="全国")
    industry = Column(String(100), nullable=False, default="全業種")
    trend_summary = Column(Text)
    hiring_intensity = Column(String(20))
    key_factors = Column(JSONB, default=list)
    advice = Column(Text)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(TIMESTAMP(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at = Column(TIMESTAMP(timezone=True), nullable=False, default=datetime.utcnow)

    __table_args__ = (
        Index("idx_seasonal_trends_month", "month"),
        Index("idx_seasonal_trends_area", "area"),
        Index("idx_seasonal_trends_industry", "industry"),
    )


class DocumentLink(SalesDBBase):
    """参考資料リンク (Read-only)"""
    __tablename__ = "document_links"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    name = Column(String(255), nullable=False)
    url = Column(Text, nullable=False)
    category = Column(String(100))
    product_id = Column(UUID(as_uuid=True))
    description = Column(Text)
    file_type = Column(String(50))
    is_active = Column(Boolean, nullable=False, default=True)

    __table_args__ = (
        Index("idx_document_links_category", "category"),
        Index("idx_document_links_is_active", "is_active"),
    )
