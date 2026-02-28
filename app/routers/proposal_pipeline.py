"""Router for proposal pipeline endpoints."""
import logging
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.core.config import settings
from app.core.security import require_sales_access
from app.db.session import get_db
from app.services.storage_service import get_storage_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/proposal-pipeline", tags=["proposal-pipeline"])

DEFAULT_TENANT_ID = UUID("00000000-0000-0000-0000-000000000000")


class PipelineRequest(BaseModel):
    minute_id: UUID
    area: str = Field(default="", description="Optional area filter")
    industry: str = Field(default="", description="Optional industry filter")


class PipelineRunResponse(BaseModel):
    id: str
    minute_id: str
    status: str
    total_duration_ms: int | None
    created_at: str
    error_stage: int | None = None
    error_message: str | None = None
    presentation_path: str | None = None
    presentation_format: str | None = None
    minio_object_key: str | None = None


class PresentationLinkRequest(BaseModel):
    presentation_path: str = Field(..., description="File path of the generated presentation")
    presentation_format: str = Field(..., pattern=r"^(pptx|pdf)$", description="pptx or pdf")


def _extract_ids(current_user: dict) -> tuple[UUID, UUID]:
    """Extract tenant_id and user_id from JWT claims."""
    tenant_id_str = current_user.get("tenant_id")
    tenant_id = UUID(tenant_id_str) if tenant_id_str else DEFAULT_TENANT_ID
    user_id_str = current_user.get("sub") or current_user.get("user_id")
    user_id = UUID(user_id_str) if user_id_str else DEFAULT_TENANT_ID
    return tenant_id, user_id


@router.post("/stream")
async def stream_pipeline(
    request: PipelineRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_sales_access),
):
    """Execute the 6-stage proposal pipeline with SSE streaming."""
    from app.services.proposal_pipeline_service import proposal_pipeline_service

    tenant_id, user_id = _extract_ids(current_user)

    return StreamingResponse(
        proposal_pipeline_service.stream_pipeline(
            minute_id=request.minute_id,
            tenant_id=tenant_id,
            user_id=user_id,
            db=db,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/generate")
async def generate_pipeline(
    request: PipelineRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_sales_access),
):
    """Execute the 6-stage proposal pipeline and return complete JSON."""
    from app.services.proposal_pipeline_service import proposal_pipeline_service

    tenant_id, user_id = _extract_ids(current_user)

    result = await proposal_pipeline_service.generate_pipeline(
        minute_id=request.minute_id,
        tenant_id=tenant_id,
        user_id=user_id,
        db=db,
    )

    if "error" in result:
        raise HTTPException(status_code=500, detail=result["error"])

    return result


@router.get("/health")
async def pipeline_health(
    current_user: dict = Depends(require_sales_access),
):
    """Check pipeline health status."""
    from app.services.pipeline_config import fetch_pipeline_config

    tenant_id_str = current_user.get("tenant_id")
    tenant_id = UUID(tenant_id_str) if tenant_id_str else DEFAULT_TENANT_ID

    try:
        config = await fetch_pipeline_config(tenant_id)
        return {
            "status": "ok",
            "pipeline_enabled": config.enabled,
            "pipeline_name": config.pipeline_name,
            "is_default_config": config.is_default,
            "kb_categories": list(config.kb_mapping.keys()),
            "enabled_stages": [i for i in range(6) if config.get_stage(i).enabled],
        }
    except Exception as e:
        return {"status": "error", "detail": str(e)}


@router.get("/runs")
async def list_pipeline_runs(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    minute_id: UUID | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_sales_access),
):
    """List pipeline execution history for the current tenant."""
    tenant_id, _ = _extract_ids(current_user)

    where_clause = "WHERE tenant_id = :tenant_id"
    params: dict = {"tenant_id": str(tenant_id)}

    if minute_id is not None:
        where_clause += " AND minute_id = :minute_id"
        params["minute_id"] = str(minute_id)

    offset = (page - 1) * page_size
    rows = db.execute(text(f"""
        SELECT id, minute_id, status, total_duration_ms,
               created_at, error_stage, error_message,
               presentation_path, presentation_format,
               minio_object_key
        FROM proposal_pipeline_runs
        {where_clause}
        ORDER BY created_at DESC
        LIMIT :limit OFFSET :offset
    """), {
        **params,
        "limit": page_size,
        "offset": offset,
    }).fetchall()

    count_result = db.execute(text(f"""
        SELECT COUNT(*) FROM proposal_pipeline_runs
        {where_clause}
    """), params).fetchone()

    total = count_result[0] if count_result else 0

    return {
        "runs": [
            {
                "id": str(r[0]),
                "minute_id": str(r[1]),
                "status": r[2],
                "total_duration_ms": r[3],
                "created_at": str(r[4]),
                "error_stage": r[5],
                "error_message": r[6],
                "presentation_path": r[7],
                "presentation_format": r[8],
                "minio_object_key": r[9],
            }
            for r in rows
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/runs/{run_id}")
async def get_pipeline_run(
    run_id: UUID,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_sales_access),
):
    """Get a single pipeline run with full sections output."""
    tenant_id, _ = _extract_ids(current_user)

    row = db.execute(text("""
        SELECT r.id, r.minute_id, r.status, r.total_duration_ms,
               r.created_at, r.error_stage, r.error_message,
               r.stage_results, r.sections,
               m.company_name, m.industry,
               r.presentation_path, r.presentation_format,
               r.minio_object_key
        FROM proposal_pipeline_runs r
        LEFT JOIN meeting_minutes m ON m.id = r.minute_id
        WHERE r.id = :run_id AND r.tenant_id = :tenant_id
    """), {
        "run_id": str(run_id),
        "tenant_id": str(tenant_id),
    }).fetchone()

    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Pipeline run not found",
        )

    return {
        "id": str(row[0]),
        "minute_id": str(row[1]),
        "status": row[2],
        "total_duration_ms": row[3],
        "created_at": str(row[4]),
        "error_stage": row[5],
        "error_message": row[6],
        "stage_results": row[7],
        "sections": row[8],
        "company_name": row[9],
        "industry": row[10],
        "presentation_path": row[11],
        "presentation_format": row[12],
        "minio_object_key": row[13],
    }


@router.patch("/runs/{run_id}/presentation")
async def update_run_presentation(
    run_id: UUID,
    body: PresentationLinkRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_sales_access),
):
    """Link a generated presentation to a pipeline run."""
    tenant_id, _ = _extract_ids(current_user)

    result = db.execute(text("""
        UPDATE proposal_pipeline_runs
        SET presentation_path = :path, presentation_format = :fmt
        WHERE id = :run_id AND tenant_id = :tenant_id
        RETURNING id
    """), {
        "run_id": str(run_id),
        "tenant_id": str(tenant_id),
        "path": body.presentation_path,
        "fmt": body.presentation_format,
    }).fetchone()
    db.commit()

    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Pipeline run not found",
        )

    # Upload to MinIO if enabled
    minio_object_key = None
    storage = get_storage_service()
    if storage:
        try:
            download_url = f"{settings.presenton_base_url}{body.presentation_path}"
            async with httpx.AsyncClient(timeout=60.0) as client:
                resp = await client.get(download_url)
                resp.raise_for_status()
                pptx_data = resp.content

            minio_object_key = await storage.upload_bytes(
                data=pptx_data,
                tenant_id=str(tenant_id),
                run_id=str(run_id),
            )
            db.execute(text("""
                UPDATE proposal_pipeline_runs
                SET minio_object_key = :key
                WHERE id = :run_id AND tenant_id = :tenant_id
            """), {
                "key": minio_object_key,
                "run_id": str(run_id),
                "tenant_id": str(tenant_id),
            })
            db.commit()
            logger.info(f"Uploaded presentation to MinIO: {minio_object_key}")
        except Exception as e:
            logger.error(f"Failed to upload presentation to MinIO: {e}")

    return {"ok": True, "minio_object_key": minio_object_key}


@router.get("/runs/{run_id}/download")
async def download_run_presentation(
    run_id: UUID,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_sales_access),
):
    """Download presentation file (MinIO or Presenton fallback)."""
    tenant_id, _ = _extract_ids(current_user)

    row = db.execute(text("""
        SELECT minio_object_key, presentation_path
        FROM proposal_pipeline_runs
        WHERE id = :run_id AND tenant_id = :tenant_id
    """), {
        "run_id": str(run_id),
        "tenant_id": str(tenant_id),
    }).fetchone()

    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Pipeline run not found",
        )

    minio_key, presentation_path = row[0], row[1]

    # Try MinIO first
    if minio_key:
        storage = get_storage_service()
        if storage:
            try:
                data = await storage.download_bytes(minio_key)
                filename = minio_key.rsplit("/", 1)[-1]
                return Response(
                    content=data,
                    media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
                    headers={
                        "Content-Disposition": f'attachment; filename="{filename}"',
                    },
                )
            except Exception as e:
                logger.warning(f"MinIO download failed, falling back to Presenton: {e}")

    # Fallback to Presenton proxy
    if not presentation_path:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No presentation file available",
        )

    download_url = f"{settings.presenton_base_url}{presentation_path}"
    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.get(download_url)
        if resp.status_code != 200:
            raise HTTPException(
                status_code=resp.status_code,
                detail="Failed to download from Presenton",
            )
        filename = presentation_path.rsplit("/", 1)[-1]
        return Response(
            content=resp.content,
            media_type=resp.headers.get("content-type", "application/octet-stream"),
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
            },
        )
