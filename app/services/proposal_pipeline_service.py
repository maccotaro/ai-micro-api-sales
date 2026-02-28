"""Proposal pipeline orchestrator: 6-stage execution with SSE streaming."""
import json
import logging
import time
from collections.abc import AsyncGenerator
from typing import Optional
from uuid import UUID

from sqlalchemy.orm import Session
from sqlalchemy import text

from app.core.config import settings
from app.db.session import SessionLocal
from app.services.llm_client import LLMClient
from app.services.pipeline_config import PipelineConfigData, fetch_pipeline_config
from app.services.pipeline_formatters import (
    sse_event,
    format_context_summary,
    format_stage_output,
    format_section_content,
)
from app.services.pipeline_stages import (
    stage0_collect_context,
    stage1_issue_structuring,
    stage2_reverse_planning,
    stage3_action_plan,
    stage4_ad_copy,
    stage5_checklist_summary,
)

logger = logging.getLogger(__name__)

STAGE_FUNCTIONS = {
    1: stage1_issue_structuring,
    2: stage2_reverse_planning,
    3: stage3_action_plan,
    4: stage4_ad_copy,
    5: stage5_checklist_summary,
}

STAGE_NAMES = {
    0: "コンテキスト収集",
    1: "課題構造化 + BANT-Cチェック",
    2: "逆算プランニング",
    3: "アクションプラン詳細化",
    4: "原稿提案生成",
    5: "チェックリスト + まとめ",
}


class ProposalPipelineService:
    """Orchestrates the 6-stage proposal pipeline."""

    def __init__(self):
        self.llm_client = LLMClient(
            base_url=settings.llm_service_url,
            secret=settings.internal_api_secret,
        )

    async def stream_pipeline(
        self,
        minute_id: UUID,
        tenant_id: UUID,
        user_id: UUID,
        db: Session,
    ) -> AsyncGenerator[str, None]:
        """Execute pipeline with SSE event streaming."""
        pipeline_start = time.time()
        config = await fetch_pipeline_config(tenant_id)

        if not config.enabled:
            yield sse_event("error", {"message": "パイプラインが無効です"})
            return

        total_stages = sum(1 for i in range(6) if config.get_stage(i).enabled)
        yield sse_event("pipeline_start", {
            "pipeline_name": config.pipeline_name,
            "total_stages": total_stages,
            "enabled_stages": [i for i in range(6) if config.get_stage(i).enabled],
        })

        stage_results = {}
        context = None
        run_id = None

        try:
            # Stage 0: Context Collection
            if config.get_stage(0).enabled:
                yield sse_event("stage_start", {"stage": 0, "name": STAGE_NAMES[0]})
                t0 = time.time()
                context = await stage0_collect_context(
                    minute_id, tenant_id, config, db
                )
                duration = int((time.time() - t0) * 1000)
                stage_results[0] = {"status": "completed", "duration_ms": duration}
                yield sse_event("stage_info", {
                    "stage": 0,
                    "company_name": context["meeting"].get("company_name", ""),
                    "industry": context["meeting"].get("industry", ""),
                })
                # Send context summary as stage_chunk for display
                yield sse_event("stage_chunk", {
                    "stage": 0,
                    "content": format_context_summary(context),
                })
                yield sse_event("stage_complete", {"stage": 0, "duration_ms": duration})

            if context is None:
                yield sse_event("error", {"message": "Stage 0 is disabled but required"})
                return

            # Create pipeline run record
            run_id = await self._create_run(tenant_id, user_id, minute_id)

            # Stages 1-5
            outputs = {}
            for stage_num in range(1, 6):
                stage_cfg = config.get_stage(stage_num)
                if not stage_cfg.enabled:
                    yield sse_event("stage_info", {
                        "stage": stage_num,
                        "name": STAGE_NAMES[stage_num],
                        "skipped": True,
                    })
                    stage_results[stage_num] = {"status": "skipped"}
                    continue

                yield sse_event("stage_start", {
                    "stage": stage_num,
                    "name": stage_cfg.name or STAGE_NAMES[stage_num],
                })
                t0 = time.time()

                try:
                    output = await self._execute_stage(
                        stage_num, context, outputs, config,
                        tenant_id,
                        pipeline_run_id=run_id,
                    )
                    outputs[stage_num] = output
                    duration = int((time.time() - t0) * 1000)
                    stage_results[stage_num] = {
                        "status": "completed",
                        "duration_ms": duration,
                        "output": output,
                    }
                    formatted = format_stage_output(stage_num, output)
                    yield sse_event("stage_chunk", {
                        "stage": stage_num,
                        "content": formatted,
                    })
                    yield sse_event("stage_complete", {
                        "stage": stage_num,
                        "duration_ms": duration,
                    })
                except Exception as e:
                    duration = int((time.time() - t0) * 1000)
                    logger.error("Stage %d failed: %s", stage_num, e)
                    stage_results[stage_num] = {
                        "status": "failed",
                        "duration_ms": duration,
                        "error": str(e),
                    }
                    yield sse_event("stage_complete", {
                        "stage": stage_num,
                        "duration_ms": duration,
                        "error": str(e),
                    })
                    # Continue with partial results
                    break

            # Build final sections
            total_duration = int((time.time() - pipeline_start) * 1000)
            sections = self._build_sections(config, outputs)
            status = "completed" if all(
                sr.get("status") in ("completed", "skipped")
                for sr in stage_results.values()
            ) else "partial"

            # Update run record
            if run_id:
                await self._update_run(
                    run_id, stage_results, total_duration, status,
                    sections=sections,
                )

            yield sse_event("pipeline_complete", {
                "total_duration_ms": total_duration,
                "status": status,
            })
            yield sse_event("result", {
                "run_id": str(run_id) if run_id else None,
                "sections": sections,
                "stage_results": {
                    str(k): {kk: vv for kk, vv in v.items() if kk != "output"}
                    for k, v in stage_results.items()
                },
                "total_duration_ms": total_duration,
                "pipeline_name": config.pipeline_name,
            })

        except Exception as e:
            logger.error("Pipeline execution failed: %s", e, exc_info=True)
            total_duration = int((time.time() - pipeline_start) * 1000)
            if run_id:
                err_stage = max(stage_results.keys()) if stage_results else 0
                await self._update_run(
                    run_id, stage_results, total_duration, "failed",
                    error_stage=err_stage, error_message=str(e),
                )
            yield sse_event("error", {"message": str(e)})

    async def generate_pipeline(
        self,
        minute_id: UUID,
        tenant_id: UUID,
        user_id: UUID,
        db: Session,
    ) -> dict:
        """Execute pipeline and return complete JSON result."""
        result = {}
        async for event_str in self.stream_pipeline(
            minute_id, tenant_id, user_id, db
        ):
            # Parse SSE to extract result event
            if event_str.startswith("data: "):
                try:
                    data = json.loads(event_str[6:].strip())
                    if data.get("type") == "result":
                        result = data
                    elif data.get("type") == "error":
                        result = {"error": data.get("message")}
                except json.JSONDecodeError:
                    pass
        return result

    async def _execute_stage(
        self,
        stage_num: int,
        context: dict,
        prev_outputs: dict,
        config: PipelineConfigData,
        tenant_id: UUID,
        pipeline_run_id: Optional[str] = None,
    ) -> dict:
        """Execute a single LLM stage."""
        run_id_str = str(pipeline_run_id) if pipeline_run_id else None
        if stage_num == 1:
            return await stage1_issue_structuring(
                context, config, self.llm_client, tenant_id,
                pipeline_run_id=run_id_str,
            )
        elif stage_num == 2:
            return await stage2_reverse_planning(
                context, prev_outputs.get(1, {}), config,
                self.llm_client, tenant_id,
                pipeline_run_id=run_id_str,
            )
        elif stage_num == 3:
            return await stage3_action_plan(
                context, prev_outputs.get(1, {}), prev_outputs.get(2, {}),
                config, self.llm_client, tenant_id,
                pipeline_run_id=run_id_str,
            )
        elif stage_num == 4:
            return await stage4_ad_copy(
                context, prev_outputs.get(1, {}), prev_outputs.get(2, {}),
                config, self.llm_client, tenant_id,
                pipeline_run_id=run_id_str,
            )
        elif stage_num == 5:
            return await stage5_checklist_summary(
                context, prev_outputs.get(1, {}), prev_outputs.get(2, {}),
                prev_outputs.get(3, {}), prev_outputs.get(4),
                config, self.llm_client, tenant_id,
                pipeline_run_id=run_id_str,
            )
        raise ValueError(f"Unknown stage: {stage_num}")

    def _build_sections(self, config: PipelineConfigData, outputs: dict) -> list[dict]:
        """Build final output sections from stage outputs and template.

        Uses per-section formatters so that sections sharing a stage
        (e.g. 'agenda' & 'proposal' both stage 2) receive different content.
        Only 'proposal' gets JSON (for ShochikubaiComparison); others get markdown.
        """
        sections = []
        for section_def in config.output_template.sections:
            stage = section_def.stage
            output = outputs.get(stage)
            content = ""
            if output:
                content = format_section_content(section_def.id, stage, output)
            elif section_def.required:
                content = "（このセクションのデータは生成されませんでした）"

            sections.append({
                "id": section_def.id,
                "title": section_def.title,
                "stage": stage,
                "content": content,
                "has_data": bool(output),
            })
        return sections

    async def _create_run(self, tenant_id: UUID, user_id: UUID, minute_id: UUID) -> Optional[UUID]:
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

    async def _update_run(
        self, run_id: UUID, stage_results: dict,
        total_duration: int, status: str,
        error_stage: int = None, error_message: str = None,
        sections: list[dict] = None,
    ) -> None:
        """Update pipeline run record."""
        try:
            own_db = SessionLocal()
            # Remove raw output from stage_results for storage
            clean_results = {}
            for k, v in stage_results.items():
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


# Module-level singleton
proposal_pipeline_service = ProposalPipelineService()
