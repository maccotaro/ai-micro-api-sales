"""
Pricing Router - 媒体別料金検索API

商材提案RAGシステムで使用する料金検索APIを提供。
media_nameをキーにして、salesdb.media_pricingから料金情報を取得する。
"""
import logging
from typing import List, Optional
from decimal import Decimal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.core.security import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/pricing", tags=["pricing"])


# =============================================================================
# Pydantic Models
# =============================================================================

class PricingItem(BaseModel):
    """料金アイテム"""
    id: int
    media_name: str
    category_large: Optional[str] = None
    category_medium: Optional[str] = None
    product_name: str
    listing_rank: Optional[str] = None
    location_count: Optional[int] = None
    listing_period: Optional[str] = None
    quantity: Optional[int] = None
    price_type: Optional[str] = None
    area: Optional[str] = None
    price: Optional[Decimal] = None
    rate: Optional[int] = None
    rate_basis: Optional[str] = None
    remarks: Optional[str] = None

    class Config:
        from_attributes = True


class PricingListResponse(BaseModel):
    """料金リストレスポンス"""
    items: List[PricingItem]
    total: int
    media_name: str
    area: Optional[str] = None


class PricingSummary(BaseModel):
    """料金サマリー（提案用）"""
    media_name: str
    min_price: Optional[Decimal] = None
    max_price: Optional[Decimal] = None
    avg_price: Optional[Decimal] = None
    product_count: int
    areas: List[str]
    categories: List[str]


# =============================================================================
# Endpoints
# =============================================================================

@router.get("/{media_name}", response_model=PricingListResponse)
async def get_pricing_by_media_name(
    media_name: str,
    area: Optional[str] = Query(None, description="エリアでフィルタ（例: 関東）"),
    category_large: Optional[str] = Query(None, description="カテゴリ（大）でフィルタ"),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    media_nameに対応する料金プラン一覧を取得。

    - **media_name**: 媒体名（例: WEB広告, マイナビバイト）
    - **area**: オプション。エリアでフィルタ（例: 関東, 関西）
    - **category_large**: オプション。カテゴリ（大）でフィルタ
    """
    logger.info(f"Get pricing for media_name={media_name}, area={area}")

    # Build query
    query = """
        SELECT id, media_name, category_large, category_medium,
               product_name, listing_rank, location_count, listing_period,
               quantity, price_type, area, price, rate, rate_basis, remarks
        FROM media_pricing
        WHERE media_name = :media_name
    """
    params = {"media_name": media_name}

    if area:
        query += " AND area = :area"
        params["area"] = area

    if category_large:
        query += " AND category_large = :category_large"
        params["category_large"] = category_large

    query += " ORDER BY category_large, category_medium, product_name"

    result = db.execute(text(query), params)
    rows = result.fetchall()

    items = []
    for row in rows:
        items.append(PricingItem(
            id=row.id,
            media_name=row.media_name,
            category_large=row.category_large,
            category_medium=row.category_medium,
            product_name=row.product_name,
            listing_rank=row.listing_rank,
            location_count=row.location_count,
            listing_period=row.listing_period,
            quantity=row.quantity,
            price_type=row.price_type,
            area=row.area,
            price=row.price,
            rate=row.rate,
            rate_basis=row.rate_basis,
            remarks=row.remarks,
        ))

    return PricingListResponse(
        items=items,
        total=len(items),
        media_name=media_name,
        area=area,
    )


@router.get("/{media_name}/summary", response_model=PricingSummary)
async def get_pricing_summary(
    media_name: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    media_nameの料金サマリーを取得。

    提案書生成時に使用する、最小/最大/平均価格とエリア・カテゴリ一覧を返す。
    """
    logger.info(f"Get pricing summary for media_name={media_name}")

    # Get price statistics
    stats_query = """
        SELECT
            MIN(price) as min_price,
            MAX(price) as max_price,
            AVG(price) as avg_price,
            COUNT(*) as product_count
        FROM media_pricing
        WHERE media_name = :media_name AND price IS NOT NULL
    """
    stats_result = db.execute(text(stats_query), {"media_name": media_name})
    stats = stats_result.fetchone()

    # Get distinct areas
    areas_query = """
        SELECT DISTINCT area FROM media_pricing
        WHERE media_name = :media_name AND area IS NOT NULL
        ORDER BY area
    """
    areas_result = db.execute(text(areas_query), {"media_name": media_name})
    areas = [row.area for row in areas_result.fetchall()]

    # Get distinct categories
    categories_query = """
        SELECT DISTINCT category_large FROM media_pricing
        WHERE media_name = :media_name AND category_large IS NOT NULL
        ORDER BY category_large
    """
    categories_result = db.execute(text(categories_query), {"media_name": media_name})
    categories = [row.category_large for row in categories_result.fetchall()]

    # Get total product count including those without price
    count_query = """
        SELECT COUNT(*) as total FROM media_pricing WHERE media_name = :media_name
    """
    count_result = db.execute(text(count_query), {"media_name": media_name})
    total_count = count_result.fetchone().total

    return PricingSummary(
        media_name=media_name,
        min_price=stats.min_price if stats else None,
        max_price=stats.max_price if stats else None,
        avg_price=round(stats.avg_price, 2) if stats and stats.avg_price else None,
        product_count=total_count,
        areas=areas,
        categories=categories,
    )


@router.get("/", response_model=List[str])
async def list_media_names(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    利用可能なmedia_name一覧を取得。

    ドキュメント編集画面やチャット機能で使用する選択肢リストを返す。
    """
    logger.info("List all media names from media_pricing")

    query = """
        SELECT DISTINCT media_name FROM media_pricing
        WHERE media_name IS NOT NULL
        ORDER BY media_name
    """
    result = db.execute(text(query))
    media_names = [row.media_name for row in result.fetchall()]

    return media_names
