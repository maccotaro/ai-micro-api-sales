"""
Internal Proposal Pipeline Router

Internal API endpoints for Agent Loop (api-admin) to trigger proposal pipelines.
Authenticated via X-Internal-Secret header. Context (tenant_id, user_id) passed in body.
"""
import logging
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.core.config import settings
from app.db.session import get_db
from app.services.embedding_service import get_embedding_service, EmbeddingService

logger = logging.getLogger(__name__)

router = APIRouter(tags=["internal-proposal-pipeline"])


async def verify_internal_secret(
    x_internal_secret: str = Header(..., alias="X-Internal-Secret"),
) -> None:
    """Verify the shared secret for internal service-to-service calls."""
    if x_internal_secret != settings.internal_api_secret:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid internal API secret",
        )


# --- Request / Response schemas ---


class TriggerPipelineRequest(BaseModel):
    minute_id: UUID
    tenant_id: UUID
    user_id: UUID
    roles: Optional[list[str]] = Field(
        default=None, description="User roles for access control"
    )
    clearance_level: Optional[str] = Field(
        default=None, description="User clearance level for confidentiality filtering"
    )
    persona_id: Optional[str] = Field(
        default=None, description="Optional persona UUID"
    )


class TriggerPipelineResponse(BaseModel):
    id: str
    status: str
    total_duration_ms: Optional[int] = None
    minio_object_key: Optional[str] = None
    stages: list = Field(default_factory=list)
    error: Optional[str] = None


class PipelineStatusResponse(BaseModel):
    id: str
    minute_id: str
    status: str
    total_duration_ms: Optional[int] = None
    created_at: str
    error_stage: Optional[int] = None
    error_message: Optional[str] = None
    minio_object_key: Optional[str] = None
    stages: list = Field(default_factory=list)


class AnalyzeMeetingRequest(BaseModel):
    tenant_id: UUID
    user_id: UUID


class AnalyzeMeetingResponse(BaseModel):
    id: str
    status: str
    analysis: Optional[dict] = None
    error: Optional[str] = None


# --- Endpoints ---


@router.post(
    "/proposal-pipeline/trigger",
    response_model=TriggerPipelineResponse,
)
async def trigger_pipeline(
    request: TriggerPipelineRequest,
    background_tasks: BackgroundTasks = None,
    _: None = Depends(verify_internal_secret),
    db: Session = Depends(get_db),
):
    """Trigger the proposal pipeline (async, returns run_id immediately).

    Called by Agent Loop (api-admin) via rest_api action type.
    Returns run_id immediately. Use GET /proposal-pipeline/runs/{run_id}
    to poll status until completed.
    """
    from app.services.proposal_pipeline_service import proposal_pipeline_service

    # Create run record first so we have a run_id
    try:
        run_id = await proposal_pipeline_service._create_run(
            request.tenant_id, request.user_id, request.minute_id,
        )
    except Exception as e:
        logger.error("Failed to create pipeline run: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

    # Execute pipeline in background
    import asyncio

    async def _run_pipeline():
        from app.db.session import SessionLocal
        bg_db = SessionLocal()
        try:
            await proposal_pipeline_service.generate_pipeline(
                minute_id=request.minute_id,
                tenant_id=request.tenant_id,
                user_id=request.user_id,
                db=bg_db,
                persona_id=request.persona_id,
                run_id=str(run_id) if run_id else None,
                user_roles=request.roles,
                user_clearance_level=request.clearance_level,
            )
        except Exception as e:
            logger.error("Background pipeline failed: %s", e, exc_info=True)
            # Update run status to failed if we have a run_id
            if run_id:
                try:
                    from app.services.pipeline_run_db import update_pipeline_run
                    await update_pipeline_run(
                        run_id, {}, 0, "failed",
                        error_message=str(e),
                    )
                except Exception:
                    logger.error("Failed to update run status on error")
        finally:
            bg_db.close()

    asyncio.ensure_future(_run_pipeline())

    return TriggerPipelineResponse(
        id=str(run_id) if run_id else "",
        status="running",
        stages=[],
    )


@router.get(
    "/proposal-pipeline/runs/{run_id}",
    response_model=PipelineStatusResponse,
)
async def get_pipeline_status(
    run_id: UUID,
    _: None = Depends(verify_internal_secret),
    db: Session = Depends(get_db),
):
    """Get pipeline run status.

    Used by Agent Loop to poll status of long-running pipelines.
    """
    row = db.execute(
        text("""
            SELECT id, minute_id, status, total_duration_ms,
                   created_at, error_stage, error_message,
                   stage_results, minio_object_key
            FROM proposal_pipeline_runs
            WHERE id = :run_id
        """),
        {"run_id": str(run_id)},
    ).fetchone()

    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Pipeline run not found",
        )

    # Build stages list from stage_results JSON
    stages = []
    stage_results = row[7] or {}
    if isinstance(stage_results, dict):
        for stage_key, stage_data in sorted(
            stage_results.items(), key=lambda x: str(x[0])
        ):
            if isinstance(stage_data, dict):
                stages.append({
                    "stage": stage_key,
                    "status": stage_data.get("status", "unknown"),
                    "duration_ms": stage_data.get("duration_ms"),
                })

    return PipelineStatusResponse(
        id=str(row[0]),
        minute_id=str(row[1]),
        status=row[2],
        total_duration_ms=row[3],
        created_at=str(row[4]),
        error_stage=row[5],
        error_message=row[6],
        minio_object_key=row[8],
        stages=stages,
    )


@router.post(
    "/meeting-minutes/{minute_id}/analyze",
    response_model=AnalyzeMeetingResponse,
)
async def analyze_meeting_minute(
    minute_id: UUID,
    request: AnalyzeMeetingRequest,
    _: None = Depends(verify_internal_secret),
    db: Session = Depends(get_db),
):
    """Analyze a meeting minute using AI (internal).

    Extracts issues, needs, keywords, summary, and next actions.
    Also stores results in Neo4j graph and generates embeddings.
    """
    from app.models.meeting import MeetingMinute
    from app.services.analysis_service import AnalysisService

    minute = db.query(MeetingMinute).filter(
        MeetingMinute.id == minute_id,
        MeetingMinute.tenant_id == request.tenant_id,
    ).first()

    if not minute:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Meeting minute not found",
        )

    try:
        analysis_service = AnalysisService()
        analysis_result = await analysis_service.analyze_meeting(
            meeting=minute,
            db=db,
            tenant_id=request.tenant_id,
        )
    except Exception as e:
        logger.error(
            "Meeting analysis failed for minute_id=%s: %s",
            minute_id, e, exc_info=True,
        )
        return AnalyzeMeetingResponse(
            id=str(minute_id),
            status="error",
            error=str(e),
        )

    return AnalyzeMeetingResponse(
        id=str(minute_id),
        status="completed",
        analysis=analysis_result.model_dump() if hasattr(analysis_result, "model_dump") else analysis_result,
    )


# --- Search & Graph internal endpoints ---


class SearchMeetingsRequest(BaseModel):
    query: str
    tenant_id: UUID
    user_id: UUID
    limit: int = Field(default=5, ge=1, le=20)
    threshold: float = Field(default=0.5, ge=0.0, le=1.0)


@router.post("/search/meetings")
async def search_similar_meetings(
    request: SearchMeetingsRequest,
    _: None = Depends(verify_internal_secret),
    db: Session = Depends(get_db),
):
    """Search similar meeting minutes by vector similarity (internal)."""
    embedding_service = await get_embedding_service()

    results = await embedding_service.search_similar_meetings(
        db=db,
        query=request.query,
        user_id=request.user_id,
        limit=request.limit,
        threshold=request.threshold,
    )

    return {"query": request.query, "total": len(results), "results": results}


@router.get("/graph/recommendations/{minute_id}")
async def get_graph_recommendations(
    minute_id: UUID,
    x_tenant_id: Optional[str] = Header(None, alias="X-Tenant-ID"),
    _: None = Depends(verify_internal_secret),
    db: Session = Depends(get_db),
):
    """Get graph-based recommendations for a meeting (internal)."""
    from app.models.meeting import MeetingMinute
    from app.services.graph.sales_graph_service import sales_graph_service

    meeting = db.query(MeetingMinute).filter(MeetingMinute.id == minute_id).first()
    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting minute not found")

    tenant_id = UUID(x_tenant_id) if x_tenant_id else UUID("00000000-0000-0000-0000-000000000000")

    if not await sales_graph_service.ensure_connected():
        raise HTTPException(status_code=503, detail="Graph service is unavailable")

    products = await sales_graph_service.find_products_with_relations(
        meeting_id=minute_id, tenant_id=tenant_id, limit=10,
    )
    similar_meetings = await sales_graph_service.find_similar_meetings(
        meeting_id=minute_id, tenant_id=tenant_id, limit=5,
    )
    success_cases = await sales_graph_service.find_success_cases_for_meeting(
        meeting_id=minute_id, tenant_id=tenant_id, limit=5,
    )

    return {
        "meeting_id": str(minute_id),
        "products": products,
        "similar_meetings": similar_meetings,
        "success_cases": success_cases,
    }
