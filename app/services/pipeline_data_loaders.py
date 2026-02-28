"""Data loading helpers for the proposal pipeline.

Extracted from pipeline_stages.py to keep each file under 500 lines.
All functions load read-only data from salesdb for pipeline context.
"""
import logging
from datetime import date, datetime

from sqlalchemy.orm import Session

from app.models.master import (
    Campaign, SimulationParam, WageData, MediaPricing, SeasonalTrend, DocumentLink,
)
from app.services.publication_record_service import get_publication_records

logger = logging.getLogger(__name__)


def load_product_data(db: Session, meeting_data: dict) -> list[dict]:
    """Load relevant product and pricing data from media_pricing table."""
    query = db.query(MediaPricing)
    area = meeting_data.get("area")
    if area:
        query = query.filter(MediaPricing.area.in_([area, "全国"]))

    pricings = query.order_by(
        MediaPricing.media_name,
        MediaPricing.price.desc().nullslast()
    ).all()

    return [
        {
            "media_name": p.media_name,
            "product_name": p.product_name,
            "price": float(p.price) if p.price else None,
            "area": p.area,
            "listing_period": p.listing_period,
            "listing_rank": p.listing_rank,
            "price_type": p.price_type,
        }
        for p in pricings
    ]


def load_simulation_data(db: Session, meeting_data: dict) -> list[dict]:
    """Load simulation parameters for the meeting's area/industry."""
    query = db.query(SimulationParam)
    if meeting_data.get("area"):
        query = query.filter(SimulationParam.area == meeting_data["area"])
    if meeting_data.get("industry"):
        query = query.filter(SimulationParam.industry == meeting_data["industry"])
    params = query.limit(10).all()
    return [
        {
            "area": p.area,
            "industry": p.industry,
            "pv_coefficient": float(p.pv_coefficient) if p.pv_coefficient else None,
            "apply_rate": float(p.apply_rate) if p.apply_rate else None,
            "conversion_rate": float(p.conversion_rate) if p.conversion_rate else None,
        }
        for p in params
    ]


def load_wage_data(db: Session, meeting_data: dict) -> list[dict]:
    """Load wage data for the meeting's area/industry."""
    query = db.query(WageData)
    if meeting_data.get("area"):
        query = query.filter(WageData.area == meeting_data["area"])
    if meeting_data.get("industry"):
        query = query.filter(WageData.industry == meeting_data["industry"])
    wages = query.limit(10).all()
    return [
        {
            "area": w.area,
            "industry": w.industry,
            "employment_type": w.employment_type,
            "min_wage": float(w.min_wage) if w.min_wage else None,
            "avg_wage": float(w.avg_wage) if w.avg_wage else None,
        }
        for w in wages
    ]


def load_publication_records(db: Session, product_names: list, meeting_data: dict) -> list[dict]:
    """Load publication records for the given products and area.

    Tries to match by industry (mapped to job_category_large) first.
    Falls back to all industries if no matching records found.
    """
    area = meeting_data.get("area")
    industry = meeting_data.get("industry")

    # Map meeting industry to job_category_large values
    job_category = _map_industry_to_job_category(industry) if industry else None

    if job_category:
        records = get_publication_records(
            db, product_names, area=area, job_category=job_category, limit=10,
        )
        if records:
            return records

    # No matching industry records found.
    # Return empty list to avoid polluting the LLM context with
    # unrelated cross-industry data that causes hallucination.
    return []


# Map meeting.industry to publication_records.job_category_large
_INDUSTRY_JOB_CATEGORY_MAP = {
    "飲食": "飲食",
    "小売": "小売",
    "介護": "介護・福祉",
    "福祉": "介護・福祉",
    "医療": "医療",
    "製造": "製造・工場",
    "工場": "製造・工場",
    "物流": "物流・配送",
    "配送": "物流・配送",
    "教育": "教育",
    "オフィス": "オフィスワーク",
    "事務": "オフィスワーク",
    "フィットネス": "サービス",
    "美容": "サービス",
    "ホテル": "サービス",
    "清掃": "サービス",
    "警備": "サービス",
    "IT": "オフィスワーク",
    "不動産": "オフィスワーク",
}


def _map_industry_to_job_category(industry: str) -> str | None:
    """Map meeting industry to publication_records.job_category_large."""
    if not industry:
        return None
    # Direct match
    if industry in _INDUSTRY_JOB_CATEGORY_MAP:
        return _INDUSTRY_JOB_CATEGORY_MAP[industry]
    # Partial match
    for key, value in _INDUSTRY_JOB_CATEGORY_MAP.items():
        if key in industry:
            return value
    return None


def load_campaign_data(db: Session) -> list[dict]:
    """Load currently active campaigns."""
    today = date.today()
    campaigns = db.query(Campaign).filter(
        Campaign.is_active == True,
        Campaign.start_date <= today,
        Campaign.end_date >= today,
    ).limit(10).all()
    return [
        {
            "name": c.name,
            "description": c.description,
            "start_date": str(c.start_date),
            "end_date": str(c.end_date),
            "discount_rate": float(c.discount_rate) if c.discount_rate else None,
            "discount_amount": float(c.discount_amount) if c.discount_amount else None,
            "conditions": c.conditions or {},
        }
        for c in campaigns
    ]


def load_seasonal_data(db: Session, month: int, area: str, industry: str) -> dict:
    """Load seasonal trend data with 4-level fallback matching.

    Fallback order:
    1. Exact match: month + area + industry
    2. Area only: month + area + '全業種'
    3. Industry only: month + '全国' + industry
    4. Default: month + '全国' + '全業種'

    Returns dict with trend data and match_level, or empty dict if no match.
    """
    base_query = db.query(SeasonalTrend).filter(
        SeasonalTrend.month == month,
        SeasonalTrend.is_active == True,
    )

    # Level 1: exact match
    if area and industry:
        result = base_query.filter(
            SeasonalTrend.area == area,
            SeasonalTrend.industry == industry,
        ).first()
        if result:
            return _seasonal_to_dict(result, "exact")

    # Level 2: area only
    if area:
        result = base_query.filter(
            SeasonalTrend.area == area,
            SeasonalTrend.industry == "全業種",
        ).first()
        if result:
            return _seasonal_to_dict(result, "area")

    # Level 3: industry only
    if industry:
        result = base_query.filter(
            SeasonalTrend.area == "全国",
            SeasonalTrend.industry == industry,
        ).first()
        if result:
            return _seasonal_to_dict(result, "industry")

    # Level 4: default
    result = base_query.filter(
        SeasonalTrend.area == "全国",
        SeasonalTrend.industry == "全業種",
    ).first()
    if result:
        return _seasonal_to_dict(result, "default")

    return {}


def load_document_links(db: Session, meeting_data: dict) -> list[dict]:
    """Load relevant document links for proposal reference materials."""
    query = db.query(DocumentLink).filter(DocumentLink.is_active == True)

    # Filter by category if product-related context is available
    results = query.order_by(DocumentLink.category, DocumentLink.name).limit(20).all()

    return [
        {
            "name": d.name,
            "url": d.url,
            "category": d.category or "",
            "description": d.description or "",
            "file_type": d.file_type or "",
        }
        for d in results
    ]


def _seasonal_to_dict(trend: SeasonalTrend, match_level: str) -> dict:
    """Convert SeasonalTrend model to dict."""
    return {
        "trend_summary": trend.trend_summary or "",
        "hiring_intensity": trend.hiring_intensity or "",
        "key_factors": trend.key_factors or [],
        "advice": trend.advice or "",
        "match_level": match_level,
        "area": trend.area,
        "industry": trend.industry,
    }
