"""
Publication Record Service

掲載実績データを検索し、LLM向けコンテキストを構築するサービス。
proposal_chat_service から呼び出され、成功事例ベースの提案を支援する。
"""
import logging
from typing import List, Dict, Any, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# エリア→都道府県マッピング（日本の地方区分）
AREA_PREFECTURE_MAP: Dict[str, List[str]] = {
    "北海道": ["北海道"],
    "東北": ["青森県", "岩手県", "宮城県", "秋田県", "山形県", "福島県"],
    "関東": ["東京都", "神奈川県", "千葉県", "埼玉県", "茨城県", "栃木県", "群馬県"],
    "北陸": ["新潟県", "富山県", "石川県", "福井県"],
    "東海": ["愛知県", "岐阜県", "静岡県", "三重県"],
    "関西": ["大阪府", "京都府", "兵庫県", "奈良県", "滋賀県", "和歌山県"],
    "中国": ["広島県", "岡山県", "山口県", "鳥取県", "島根県"],
    "四国": ["徳島県", "香川県", "愛媛県", "高知県"],
    "九州": ["福岡県", "佐賀県", "長崎県", "熊本県", "大分県", "宮崎県", "鹿児島県", "沖縄県"],
}


def get_publication_records(
    db: Session,
    product_names: List[str],
    area: Optional[str] = None,
    prefecture: Optional[str] = None,
    job_category: Optional[str] = None,
    employment_type: Optional[str] = None,
    limit: int = 10,
) -> List[Dict[str, Any]]:
    """
    掲載実績を検索する。

    Args:
        db: データベースセッション
        product_names: 商材名リスト（media_pricing.product_name = publication_records.plan_category）
        area: エリア名（関東、関西等）→ 都道府県リストにマッピング
        prefecture: 都道府県（直接指定、areaより優先）
        job_category: 職種大分類フィルタ
        employment_type: 雇用形態フィルタ
        limit: 最大取得件数

    Returns:
        List[Dict]: 掲載実績レコードのリスト
    """
    if not product_names:
        return []

    # ベースクエリ: plan_category マッチ + 成果あり
    query = """
        SELECT plan_category, prefecture, job_category_large, job_category_medium,
               job_title, catchcopy, employment_type,
               pv_count, application_count, hire_count,
               company_name, store_name,
               publication_start_date, publication_end_date
        FROM publication_records
        WHERE plan_category = ANY(:product_names)
          AND (application_count > 0 OR hire_count > 0)
    """
    params: Dict[str, Any] = {"product_names": product_names}

    # 都道府県フィルタ（直接指定 or エリアマッピング）
    if prefecture:
        query += " AND prefecture = :prefecture"
        params["prefecture"] = prefecture
    elif area and area in AREA_PREFECTURE_MAP:
        prefectures = AREA_PREFECTURE_MAP[area]
        query += " AND prefecture = ANY(:prefectures)"
        params["prefectures"] = prefectures

    # オプションフィルタ
    if job_category:
        query += " AND job_category_large = :job_category"
        params["job_category"] = job_category

    if employment_type:
        query += " AND employment_type = :employment_type"
        params["employment_type"] = employment_type

    query += " ORDER BY application_count DESC, hire_count DESC, pv_count DESC LIMIT :limit"
    params["limit"] = limit

    try:
        result = db.execute(text(query), params)
        rows = result.fetchall()

        records = []
        for row in rows:
            records.append({
                "plan_category": row.plan_category,
                "prefecture": row.prefecture,
                "job_category_large": row.job_category_large,
                "job_category_medium": row.job_category_medium,
                "job_title": row.job_title,
                "catchcopy": row.catchcopy,
                "employment_type": row.employment_type,
                "pv_count": row.pv_count or 0,
                "application_count": row.application_count or 0,
                "hire_count": row.hire_count or 0,
                "company_name": row.company_name,
                "store_name": row.store_name,
                "publication_start_date": str(row.publication_start_date) if row.publication_start_date else None,
                "publication_end_date": str(row.publication_end_date) if row.publication_end_date else None,
            })

        logger.info(
            f"Found {len(records)} publication records for "
            f"products={product_names}, prefecture={prefecture}, area={area}"
        )
        return records

    except Exception as e:
        logger.error(f"Failed to query publication_records: {e}")
        return []


def build_publication_context(records: List[Dict[str, Any]]) -> str:
    """
    掲載実績レコードからLLM向けコンテキストテキストを構築する。

    Args:
        records: get_publication_records() の返り値

    Returns:
        str: LLMプロンプト用テキスト
    """
    if not records:
        return "（掲載実績データなし）"

    parts = [f"以下は過去の掲載実績データ（成功事例）です（{len(records)}件）：\n"]

    for i, rec in enumerate(records, 1):
        catchcopy_str = f"\n  キャッチコピー: {rec['catchcopy']}" if rec.get("catchcopy") else ""
        job_title_str = f"\n  募集職種名: {rec['job_title']}" if rec.get("job_title") else ""
        start = rec.get("publication_start_date") or "不明"
        end = rec.get("publication_end_date") or "不明"
        period_str = f"\n  掲載期間: {start} 〜 {end}"
        parts.append(
            f"【事例{i}】\n"
            f"  企画: {rec['plan_category']}\n"
            f"  地域: {rec['prefecture'] or '不明'}\n"
            f"  職種: {rec['job_category_large'] or '不明'}"
            f"（{rec['job_category_medium'] or ''}）\n"
            f"  雇用形態: {rec['employment_type'] or '不明'}"
            f"{job_title_str}{catchcopy_str}{period_str}\n"
            f"  PV: {rec['pv_count']:,} / 応募: {rec['application_count']:,}"
            f" / 採用: {rec['hire_count']:,}\n"
        )

    # 集計統計
    total = len(records)
    avg_pv = sum(r["pv_count"] for r in records) / total
    avg_app = sum(r["application_count"] for r in records) / total
    avg_hire = sum(r["hire_count"] for r in records) / total

    parts.append(
        f"\n【集計】{total}件の平均:\n"
        f"  平均PV: {avg_pv:,.1f} / 平均応募: {avg_app:,.1f} / 平均採用: {avg_hire:,.1f}\n"
        f"  ※ 上記は過去実績の参考値であり、保証値ではありません"
    )

    return "\n".join(parts)
