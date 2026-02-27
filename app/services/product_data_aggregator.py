"""
Product Data Aggregator

媒体別データ集約サービス。
各媒体ごとに料金情報と掲載実績を個別に収集し、
DB にない場合は KB（ナレッジベース）からフォールバック検索する。
"""
import asyncio
import logging
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from uuid import UUID

import httpx
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.services.publication_record_service import get_publication_records

logger = logging.getLogger(__name__)


@dataclass
class MediaProductData:
    """媒体別の集約データ"""
    media_name: str
    pricing_plans: List[Dict[str, Any]] = field(default_factory=list)
    pricing_source: str = "none"  # "db" | "kb" | "none"
    publication_records: List[Dict[str, Any]] = field(default_factory=list)
    publication_source: str = "none"  # "db" | "kb" | "none"
    kb_pricing_context: str = ""
    kb_publication_context: str = ""


def get_pricing_info(
    db: Session,
    media_names: List[str],
    area: Optional[str] = None,
) -> Dict[str, List[Dict[str, Any]]]:
    """media_nameに対応する料金情報を取得。

    proposal_chat_service.py から移動（standalone 関数化、ロジック変更なし）。
    area フィルタで0件の媒体も空リストとして返却する。
    """
    if not media_names:
        return {}

    pricing_info: Dict[str, List[Dict[str, Any]]] = {}

    for media_name in media_names:
        query = """
            SELECT media_name, category_large, product_name, price, area,
                   listing_period, price_type, remarks
            FROM media_pricing
            WHERE media_name = :media_name
        """
        params: Dict[str, Any] = {"media_name": media_name}

        if area:
            query += " AND area = :area"
            params["area"] = area

        query += " ORDER BY price DESC NULLS LAST, category_large, product_name LIMIT 20"

        result = db.execute(text(query), params)
        rows = result.fetchall()

        plans = []
        for row in rows:
            plans.append({
                "media_name": row.media_name,
                "category": row.category_large,
                "product_name": row.product_name,
                "price": float(row.price) if row.price else None,
                "area": row.area,
                "listing_period": row.listing_period,
                "price_type": row.price_type,
                "remarks": row.remarks,
            })

        # 空リストも含めて全媒体分返却（元のコードは if plans: のみ格納していた）
        pricing_info[media_name] = plans
        if plans:
            logger.info(f"Found {len(plans)} pricing plans for {media_name}")

    return pricing_info


async def _kb_fallback_search(
    query: str,
    kb_id: UUID,
    tenant_id: UUID,
    top_k: int = 3,
) -> str:
    """api-rag の /internal/search/hybrid にリクエストして KB フォールバック検索。

    スコア閾値0.3未満はスキップ、結果テキスト結合（500文字/件）。
    """
    search_url = f"{settings.rag_service_url}/internal/search/hybrid"

    async with httpx.AsyncClient(timeout=60.0) as client:
        try:
            response = await client.post(
                search_url,
                json={
                    "query": query,
                    "tenant_id": str(tenant_id),
                    "knowledge_base_id": str(kb_id),
                    "top_k": top_k,
                    "enable_graph": False,
                },
                headers={
                    "X-Internal-Secret": settings.internal_api_secret,
                    "Content-Type": "application/json",
                },
            )
            response.raise_for_status()
            data = response.json()

            results = data.get("results") or []
            texts = []
            for item in results:
                score = item.get("final_score") or item.get("cross_encoder_score") or 0.0
                if score < 0.3:
                    continue
                content = (item.get("content") or "")[:500]
                if content:
                    texts.append(content)

            combined = "\n---\n".join(texts)
            logger.info(
                f"KB fallback: query='{query[:40]}...' "
                f"results={len(results)}, used={len(texts)}"
            )
            return combined

        except httpx.HTTPError as e:
            logger.error(f"KB fallback search failed: {e}")
            return ""


async def aggregate_product_data(
    db: Session,
    media_names: List[str],
    kb_id: UUID,
    tenant_id: UUID,
    area: Optional[str] = None,
    prefecture: Optional[str] = None,
    job_category: Optional[str] = None,
    employment_type: Optional[str] = None,
) -> Dict[str, MediaProductData]:
    """各媒体の DB 料金取得 -> DB 実績取得 -> 不足分 KB fallback -> 集約結果返却。"""
    if not media_names:
        return {}

    # Step 1: DB 料金取得（全媒体）
    pricing_info = get_pricing_info(db, media_names, area)

    # Step 2: 媒体ごとに DB 実績取得
    media_data: Dict[str, MediaProductData] = {}
    for media_name in media_names:
        plans = pricing_info.get(media_name, [])
        product_names = list({
            p["product_name"] for p in plans if p.get("product_name")
        })

        pub_records = get_publication_records(
            db, product_names, area, prefecture, job_category, employment_type
        ) if product_names else []

        data = MediaProductData(
            media_name=media_name,
            pricing_plans=plans,
            pricing_source="db" if plans else "none",
            publication_records=pub_records,
            publication_source="db" if pub_records else "none",
        )
        media_data[media_name] = data

    # Step 3: KB fallback 対象を特定して並列実行
    fallback_tasks = []
    fallback_keys = []  # (media_name, "pricing"|"publication")

    for media_name, data in media_data.items():
        if data.pricing_source == "none":
            fallback_tasks.append(
                _kb_fallback_search(
                    f"{media_name} 料金 プラン 価格",
                    kb_id, tenant_id,
                )
            )
            fallback_keys.append((media_name, "pricing"))

        if data.publication_source == "none":
            fallback_tasks.append(
                _kb_fallback_search(
                    f"{media_name} 掲載実績 成功事例 効果",
                    kb_id, tenant_id,
                )
            )
            fallback_keys.append((media_name, "publication"))

    if fallback_tasks:
        logger.info(f"Running {len(fallback_tasks)} KB fallback searches")
        results = await asyncio.gather(*fallback_tasks, return_exceptions=True)

        for (media_name, kind), result in zip(fallback_keys, results):
            if isinstance(result, Exception):
                logger.error(f"KB fallback error for {media_name}/{kind}: {result}")
                continue

            text_result = result or ""
            if kind == "pricing" and text_result:
                media_data[media_name].kb_pricing_context = text_result
                media_data[media_name].pricing_source = "kb"
            elif kind == "publication" and text_result:
                media_data[media_name].kb_publication_context = text_result
                media_data[media_name].publication_source = "kb"

    return media_data


def build_per_media_context(media_data: Dict[str, MediaProductData]) -> str:
    """媒体別に料金+実績をデータソース付きで構築。"""
    if not media_data:
        return "(媒体データなし)"

    parts = []
    for media_name, data in media_data.items():
        section = [f"【{media_name}】"]

        # 料金情報
        if data.pricing_source == "db":
            section.append(f"  ■ 料金情報（データベース: {len(data.pricing_plans)}件）")
            for plan in data.pricing_plans[:15]:
                price_str = f"¥{plan['price']:,.0f}" if plan.get("price") else "要問合せ"
                area_str = plan.get("area") or "全国"
                period_str = f"({plan['listing_period']})" if plan.get("listing_period") else ""
                cat_str = f"[{plan['category']}] " if plan.get("category") else ""
                section.append(f"    - {cat_str}{plan['product_name']}: {price_str} / {area_str} {period_str}")
        elif data.pricing_source == "kb":
            section.append("  ■ 料金情報（※ 参考情報 - KBより）")
            section.append(f"    {data.kb_pricing_context}")
        else:
            section.append("  ■ 料金情報（情報なし - 要確認）")

        # 掲載実績
        if data.publication_source == "db":
            records = data.publication_records
            section.append(f"  ■ 掲載実績（データベース: {len(records)}件）")
            for i, rec in enumerate(records[:5], 1):
                job_str = rec.get("job_category_large") or "不明"
                pref_str = rec.get("prefecture") or "不明"
                section.append(
                    f"    事例{i}: {pref_str}/{job_str} "
                    f"PV:{rec.get('pv_count', 0):,} 応募:{rec.get('application_count', 0):,} "
                    f"採用:{rec.get('hire_count', 0):,}"
                )
            if records:
                total = len(records)
                avg_app = sum(r.get("application_count", 0) for r in records) / total
                avg_hire = sum(r.get("hire_count", 0) for r in records) / total
                section.append(f"    集計: {total}件平均 応募:{avg_app:.1f} 採用:{avg_hire:.1f}")
        elif data.publication_source == "kb":
            section.append("  ■ 掲載実績（※ 参考情報 - KBより）")
            section.append(f"    {data.kb_publication_context}")
        else:
            section.append("  ■ 掲載実績（情報なし）")

        section.append("")  # 媒体間の空行
        parts.append("\n".join(section))

    return "\n".join(parts)


def build_data_summary(media_data: Dict[str, MediaProductData]) -> str:
    """SSE info 用の1行サマリーテキスト生成。"""
    if not media_data:
        return "媒体データなし"

    summaries = []
    for media_name, data in media_data.items():
        # 料金サマリー
        if data.pricing_source == "db":
            pricing_str = f"料金{len(data.pricing_plans)}件(DB)"
        elif data.pricing_source == "kb":
            pricing_str = "料金(KB検索)"
        else:
            pricing_str = "料金なし"

        # 実績サマリー
        if data.publication_source == "db":
            pub_str = f"実績{len(data.publication_records)}件(DB)"
        elif data.publication_source == "kb":
            pub_str = "実績(KB検索)"
        else:
            pub_str = "実績なし"

        summaries.append(f"{media_name}: {pricing_str}/{pub_str}")

    return ", ".join(summaries)
