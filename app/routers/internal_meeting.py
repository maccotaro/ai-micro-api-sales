"""Internal API for receiving meeting transcripts from api-meeting."""
import logging
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel

from app.core.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(tags=["internal"])


async def verify_internal_secret(
    x_internal_secret: str = Header(..., alias="X-Internal-Secret"),
) -> None:
    if x_internal_secret != settings.internal_api_secret:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid internal API secret",
        )


class MeetingTranscriptPayload(BaseModel):
    stt_job_id: UUID
    tenant_id: UUID
    meeting_type: str
    title: Optional[str] = None
    audio_duration_seconds: Optional[float] = None
    language: Optional[str] = None
    full_text: str
    segments: list = []
    speaker_mappings: list = []
    created_by: UUID


@router.post("/sales/meeting-transcript", status_code=202)
async def receive_meeting_transcript(
    payload: MeetingTranscriptPayload,
    _=Depends(verify_internal_secret),
):
    """Receive meeting transcript from api-meeting (sales type).

    Creates meeting minutes and triggers analysis pipeline.
    """
    logger.info(
        f"Received sales meeting transcript: job={payload.stt_job_id}, "
        f"type={payload.meeting_type}, tenant={payload.tenant_id}, "
        f"text_len={len(payload.full_text)}"
    )
    # TODO: Create meeting_minutes record and trigger analysis
    return {"status": "accepted", "stt_job_id": str(payload.stt_job_id)}
