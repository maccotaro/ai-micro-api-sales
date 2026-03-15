"""Data loaders for proposal document pipeline (Stage 6)."""
import logging
from typing import Optional
from uuid import UUID

import httpx
from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.core.config import settings

logger = logging.getLogger(__name__)


async def load_success_cases(
    industry: str,
    area: str,
    tenant_id: UUID,
    limit: int = 5,
) -> list[dict]:
    """Search success_case_embeddings by industry and area via embedding API."""
    if not industry:
        return []

    try:
        query = f"{industry} {area} 成功事例 採用"
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                f"{settings.rag_service_url}/internal/v1/search/success-cases",
                json={
                    "query": query,
                    "industry": industry,
                    "area": area,
                    "tenant_id": str(tenant_id),
                    "limit": limit,
                },
                headers={
                    "X-Internal-Secret": settings.internal_api_secret,
                    "Content-Type": "application/json",
                },
            )
            if resp.status_code == 200:
                data = resp.json()
                return data.get("results", [])
            else:
                logger.warning("Success case search failed: status=%s", resp.status_code)
                return []
    except Exception as e:
        logger.warning("Success case search failed: %s", e)
        return []


def load_publication_records_for_proposal(
    db: Session,
    industry: str,
    area: str,
    limit: int = 10,
) -> list[dict]:
    """Load high-performing publication records for proposal context.

    Returns records sorted by application_count descending.
    """
    from app.services.publication_record_service import get_publication_records
    from app.services.pipeline_data_loaders import _map_industry_to_job_category

    if not industry:
        return []

    job_category = _map_industry_to_job_category(industry)

    try:
        records = get_publication_records(
            db=db,
            product_names=[],
            area=area,
            job_category=job_category,
            limit=limit,
        )

        return [
            {
                "plan_category": r.get("plan_category", ""),
                "prefecture": r.get("prefecture", ""),
                "job_category_large": r.get("job_category_large", ""),
                "job_title": r.get("job_title", ""),
                "catchcopy": r.get("catchcopy", ""),
                "pv_count": r.get("pv_count", 0),
                "application_count": r.get("application_count", 0),
                "hire_count": r.get("hire_count", 0),
                "wage_amount": r.get("wage_amount", 0),
            }
            for r in records
        ]
    except Exception as e:
        logger.warning("Publication records load failed: %s", e)
        return []
