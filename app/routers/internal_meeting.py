"""Internal API for receiving meeting transcripts from api-meeting."""
import asyncio
import logging
from datetime import datetime
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db, SessionLocal
from app.models.meeting import MeetingMinute

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


async def _run_kb_correction_background(minutes_id: UUID) -> None:
    """Run KB correction, then auto-trigger the 12-section parse.

    会議後に話者名・トランスクリプトを修正して「議事録生成」した時点で、
    KB補正 → 12セクション parse まで一気通貫で完走させる（finalize 待ちにしない）。
    """
    from app.services.kb_correction import run_kb_correction
    from app.core.celery_app import celery_app

    db = SessionLocal()
    try:
        await run_kb_correction(minutes_id, db)
    except Exception as e:
        logger.error(f"Background KB correction failed for {minutes_id}: {e}")
    finally:
        db.close()

    # KB補正の成否にかかわらず、12セクション parse を自動起動する
    # （parse タスクは corrected_text→raw_text の順で対象テキストを選ぶ）
    try:
        db2 = SessionLocal()
        try:
            minute = db2.query(MeetingMinute).filter(MeetingMinute.id == minutes_id).first()
            tenant_id = str(minute.tenant_id) if minute and minute.tenant_id else None
        finally:
            db2.close()
        celery_app.send_task(
            "app.tasks.parse_meeting_minutes.parse_meeting_minutes",
            kwargs={"meeting_id": str(minutes_id), "tenant_id": tenant_id},
            queue="llm",
        )
        logger.info(f"Enqueued 12-section parse after KB correction for {minutes_id}")
    except Exception as e:
        logger.error(f"Failed to enqueue parse after KB correction for {minutes_id}: {e}")


@router.post("/sales/meeting-transcript", status_code=202)
async def receive_meeting_transcript(
    payload: MeetingTranscriptPayload,
    background_tasks: BackgroundTasks,
    _=Depends(verify_internal_secret),
    db: Session = Depends(get_db),
):
    """Receive meeting transcript from api-meeting (sales type).

    Creates meeting_minutes record (idempotent on stt_job_id) and
    triggers KB correction pipeline asynchronously.
    """
    logger.info(
        f"Received sales meeting transcript: job={payload.stt_job_id}, "
        f"type={payload.meeting_type}, tenant={payload.tenant_id}, "
        f"text_len={len(payload.full_text)}"
    )

    # Idempotent: check if meeting_minutes already exists for this stt_job_id
    existing = (
        db.query(MeetingMinute)
        .filter(MeetingMinute.stt_job_id == payload.stt_job_id)
        .first()
    )
    if existing:
        logger.info(f"Duplicate dispatch for stt_job_id={payload.stt_job_id}, returning existing record")
        return {
            "status": "already_exists",
            "stt_job_id": str(payload.stt_job_id),
            "meeting_minutes_id": str(existing.id),
        }

    # Build attendees list as List[Dict] (matching MeetingMinuteResponse schema)
    seen_names = set()
    attendees_list = []
    for m in payload.speaker_mappings:
        name = m.get("participant_name") or m.get("speaker_label", "Unknown")
        if name not in seen_names:
            seen_names.add(name)
            attendees_list.append({"name": name, "role": "participant"})
    company_name = payload.title or f"STT Meeting ({payload.meeting_type})"

    # Create meeting_minutes record
    minute = MeetingMinute(
        company_name=company_name,
        raw_text=payload.full_text,
        status="draft",
        minutes_status="raw",
        stt_job_id=payload.stt_job_id,
        tenant_id=payload.tenant_id,
        created_by=payload.created_by,
        meeting_date=datetime.utcnow().date(),
        attendees=attendees_list,
        version=1,
    )
    db.add(minute)
    db.commit()
    db.refresh(minute)

    logger.info(
        f"Created meeting_minutes id={minute.id} for stt_job_id={payload.stt_job_id}"
    )

    # Trigger KB correction pipeline asynchronously
    background_tasks.add_task(_run_kb_correction_background, minute.id)

    return {
        "status": "accepted",
        "stt_job_id": str(payload.stt_job_id),
        "meeting_minutes_id": str(minute.id),
    }
