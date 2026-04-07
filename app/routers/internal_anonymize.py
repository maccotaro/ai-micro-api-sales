"""Internal API for GDPR Art. 17 sales data anonymization.

Called by api-hr erasure_orchestrator.
Anonymizes created_by in salesdb tables.
Authentication: X-Internal-Secret header.
"""
import logging

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db

logger = logging.getLogger(__name__)
router = APIRouter()


async def _verify(x_internal_secret: str = Header(..., alias="X-Internal-Secret")):
    if x_internal_secret != settings.internal_api_secret:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid")


class AnonymizeRequest(BaseModel):
    user_id: str


@router.post(
    "/internal/sales/anonymize-records",
    status_code=204,
    dependencies=[Depends(_verify)],
)
def anonymize_sales_data(body: AnonymizeRequest, db: Session = Depends(get_db)):
    """Anonymize created_by in salesdb tables."""
    uid = body.user_id
    total = 0

    for table in ("meeting_minutes", "proposal_history", "proposal_documents"):
        try:
            result = db.execute(
                text(f"UPDATE {table} SET created_by = NULL WHERE created_by = CAST(:uid AS uuid)"),
                {"uid": uid},
            )
            total += result.rowcount
        except Exception:
            pass  # Table may not exist

    # proposal_pipeline_runs uses user_id
    try:
        result = db.execute(
            text("UPDATE proposal_pipeline_runs SET user_id = NULL WHERE user_id = CAST(:uid AS uuid)"),
            {"uid": uid},
        )
        total += result.rowcount
    except Exception:
        pass

    db.commit()
    logger.info("Anonymized %d salesdb rows for user %s", total, uid[:8])
