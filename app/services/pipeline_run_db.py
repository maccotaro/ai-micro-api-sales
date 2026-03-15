"""Database operations for pipeline run records.

Extracted from proposal_pipeline_service.py for 500-line limit compliance.
"""
import json
import logging
from typing import Optional
from uuid import UUID

from sqlalchemy import text

from app.db.session import SessionLocal

logger = logging.getLogger(__name__)


async def create_pipeline_run(
    tenant_id: UUID, user_id: UUID, minute_id: UUID,
) -> Optional[UUID]:
    """Insert pipeline run record into salesdb."""
    try:
        own_db = SessionLocal()
        result = own_db.execute(text("""
            INSERT INTO proposal_pipeline_runs (tenant_id, user_id, minute_id, status)
            VALUES (:tenant_id, :user_id, :minute_id, 'running')
            RETURNING id
        """), {
            "tenant_id": str(tenant_id),
            "user_id": str(user_id),
            "minute_id": str(minute_id),
        })
        own_db.commit()
        row = result.fetchone()
        return row[0] if row else None
    except Exception as e:
        logger.error("Failed to create pipeline run: %s", e)
        return None
    finally:
        own_db.close()


async def update_pipeline_run(
    run_id: UUID, stage_results: dict,
    total_duration: int, status: str,
    error_stage: int = None, error_message: str = None,
    sections: list[dict] = None,
) -> None:
    """Update pipeline run record."""
    try:
        own_db = SessionLocal()
        clean_results = {}
        for k, v in stage_results.items():
            # Stage 0-5: exclude "output" (large, displayed via sections)
            # Stage 6-10: keep "output" and "prompt" for debugging
            stage_num = int(k) if str(k).isdigit() else -1
            if stage_num >= 6:
                clean = {kk: vv for kk, vv in v.items()}
            else:
                clean = {kk: vv for kk, vv in v.items() if kk != "output"}
            clean_results[str(k)] = clean

        own_db.execute(text("""
            UPDATE proposal_pipeline_runs
            SET stage_results = :stage_results,
                total_duration_ms = :total_duration,
                status = :status,
                error_stage = :error_stage,
                error_message = :error_message,
                sections = :sections
            WHERE id = :run_id
        """), {
            "stage_results": json.dumps(clean_results),
            "total_duration": total_duration,
            "status": status,
            "error_stage": error_stage,
            "error_message": error_message,
            "sections": json.dumps(sections) if sections is not None else None,
            "run_id": str(run_id),
        })
        own_db.commit()
    except Exception as e:
        logger.error("Failed to update pipeline run: %s", e)
    finally:
        own_db.close()
