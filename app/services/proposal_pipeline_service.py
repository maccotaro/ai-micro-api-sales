"""Proposal pipeline orchestrator: 11-stage execution with SSE streaming."""
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
from app.services.proposal_stages import (
    stage6_proposal_context,
    stage7_industry_target_analysis,
    stage8_appeal_strategy,
    stage9_story_structure,
    stage10_page_generation,
)
from app.services.proposal_formatters import (
    format_stage7 as _format_stage7,
    format_stage8 as _format_stage8,
    format_stage9 as _format_stage9,
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
    6: "提案コンテキスト収集",
    7: "業界・ターゲット分析",
    8: "訴求戦略立案",
    9: "ストーリー構成",
    10: "ページ生成",
}


class ProposalPipelineService:
    """Orchestrates the 6-stage proposal pipeline."""

    def __init__(self):
        self.llm_client = LLMClient(
            base_url=settings.llm_service_url,
            secret=settings.internal_api_secret,
            timeout=300.0,
        )

    async def stream_pipeline(
        self,
        minute_id: UUID,
        tenant_id: UUID,
        user_id: UUID,
        db: Session,
        persona_id: Optional[str] = None,
        run_id: Optional[str] = None,
    ) -> AsyncGenerator[str, None]:
        """Execute pipeline with SSE event streaming."""
        pipeline_start = time.time()
        config = await fetch_pipeline_config(tenant_id)

        if not config.enabled:
            yield sse_event("error", {"message": "パイプラインが無効です"})
            return

        total_stages = sum(1 for i in range(11) if config.get_stage(i).enabled)
        yield sse_event("pipeline_start", {
            "pipeline_name": config.pipeline_name,
            "total_stages": total_stages,
            "enabled_stages": [i for i in range(11) if config.get_stage(i).enabled],
        })

        stage_results = {}
        if persona_id:
            stage_results["_meta"] = {"persona_id": persona_id}
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
                yield sse_event("stage_sections", {
                    "stage": 0,
                    "sections": [{
                        "id": "context",
                        "title": STAGE_NAMES[0],
                        "stage": 0,
                        "content": format_context_summary(context),
                        "has_data": True,
                    }],
                })

            if context is None:
                yield sse_event("error", {"message": "Stage 0 is disabled but required"})
                return

            # Create pipeline run record (skip if already provided by caller)
            if not run_id:
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
                        persona_id=persona_id,
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
                    # Emit structured sections for immediate display
                    stage_secs = self._build_stage_sections(config, stage_num, output)
                    if stage_secs:
                        yield sse_event("stage_sections", {
                            "stage": stage_num,
                            "sections": stage_secs,
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

            # Stage 6-10: Proposal document generation
            proposal_doc_result = None
            logger.info("Stage 6-10 check: stage6_enabled=%s, outputs_keys=%s",
                        config.get_stage(6).enabled, list(outputs.keys()))
            if config.get_stage(6).enabled and outputs.get(1):
                async for sse_or_result in self._stream_proposal_stages(
                    context, outputs, config, tenant_id, user_id,
                    run_id, minute_id, db, stage_results,
                    persona_id=persona_id,
                ):
                    if isinstance(sse_or_result, str):
                        yield sse_or_result
                    elif isinstance(sse_or_result, dict):
                        proposal_doc_result = sse_or_result

            # Build final sections
            total_duration = int((time.time() - pipeline_start) * 1000)
            sections = self._build_sections(config, outputs)
            # Prepend Stage 0 context collection summary
            if context:
                sections.insert(0, {
                    "id": "context",
                    "title": STAGE_NAMES[0],
                    "stage": 0,
                    "content": format_context_summary(context),
                    "has_data": True,
                })
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
            result_data = {
                "run_id": str(run_id) if run_id else None,
                "sections": sections,
                "stage_results": {
                    str(k): {kk: vv for kk, vv in v.items() if kk != "output"}
                    for k, v in stage_results.items()
                },
                "total_duration_ms": total_duration,
                "pipeline_name": config.pipeline_name,
            }
            if proposal_doc_result and proposal_doc_result.get("document_id"):
                result_data["document_id"] = proposal_doc_result["document_id"]
            yield sse_event("result", result_data)

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
        persona_id: Optional[str] = None,
        run_id: Optional[str] = None,
    ) -> dict:
        """Execute pipeline and return complete JSON result."""
        result = {}
        async for event_str in self.stream_pipeline(
            minute_id, tenant_id, user_id, db,
            persona_id=persona_id, run_id=run_id,
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
        persona_id: Optional[str] = None,
    ) -> dict:
        """Execute a single LLM stage."""
        run_id_str = str(pipeline_run_id) if pipeline_run_id else None
        if stage_num == 1:
            return await stage1_issue_structuring(
                context, config, self.llm_client, tenant_id,
                pipeline_run_id=run_id_str, persona_id=persona_id,
            )
        elif stage_num == 2:
            return await stage2_reverse_planning(
                context, prev_outputs.get(1, {}), config,
                self.llm_client, tenant_id,
                pipeline_run_id=run_id_str, persona_id=persona_id,
            )
        elif stage_num == 3:
            return await stage3_action_plan(
                context, prev_outputs.get(1, {}), prev_outputs.get(2, {}),
                config, self.llm_client, tenant_id,
                pipeline_run_id=run_id_str, persona_id=persona_id,
            )
        elif stage_num == 4:
            return await stage4_ad_copy(
                context, prev_outputs.get(1, {}), prev_outputs.get(2, {}),
                config, self.llm_client, tenant_id,
                pipeline_run_id=run_id_str, persona_id=persona_id,
            )
        elif stage_num == 5:
            return await stage5_checklist_summary(
                context, prev_outputs.get(1, {}), prev_outputs.get(2, {}),
                prev_outputs.get(3, {}), prev_outputs.get(4),
                config, self.llm_client, tenant_id,
                pipeline_run_id=run_id_str, persona_id=persona_id,
            )
        raise ValueError(f"Unknown stage: {stage_num}")

    async def _stream_proposal_stages(
        self, context, outputs, config, tenant_id, user_id,
        run_id, minute_id, db, stage_results,
        persona_id: Optional[str] = None,
    ):
        """Execute Stage 6-10, yielding SSE events and final dict result."""
        run_id_str = str(run_id) if run_id else None
        proposal_stages_map = {
            6: ("提案コンテキスト収集", None),
            7: ("業界・ターゲット分析", None),
            8: ("訴求戦略立案", None),
            9: ("ストーリー構成", None),
            10: ("ページ生成", None),
        }

        try:
            for sn in range(6, 11):
                if not config.get_stage(sn).enabled:
                    stage_results[sn] = {"status": "skipped"}
                    continue
                # Check dependencies
                if sn == 7 and not outputs.get(6):
                    break
                if sn == 8 and not outputs.get(7):
                    break
                if sn == 9 and (not outputs.get(7) or not outputs.get(8)):
                    break
                if sn == 10 and not outputs.get(9):
                    break

                yield sse_event("stage_start", {"stage": sn, "name": STAGE_NAMES[sn]})
                t0 = time.time()

                if sn == 6:
                    out = await stage6_proposal_context(
                        context, outputs.get(1, {}), config, db, tenant_id,
                    )
                elif sn == 7:
                    out = await stage7_industry_target_analysis(
                        context, outputs.get(1, {}), outputs[6],
                        config, self.llm_client, tenant_id, run_id_str,
                        persona_id=persona_id,
                    )
                elif sn == 8:
                    out = await stage8_appeal_strategy(
                        context, outputs.get(1, {}), outputs[6], outputs[7],
                        config, self.llm_client, tenant_id, run_id_str,
                        persona_id=persona_id,
                    )
                elif sn == 9:
                    out = await stage9_story_structure(
                        outputs.get(1, {}), outputs[7], outputs[8],
                        config, self.llm_client, tenant_id, run_id_str,
                        persona_id=persona_id,
                    )
                elif sn == 10:
                    out = await stage10_page_generation(
                        context, outputs.get(1, {}), outputs.get(2, {}),
                        outputs[6],
                        outputs.get(7, {}), outputs.get(8, {}), outputs[9],
                        config, self.llm_client, db,
                        tenant_id, user_id, run_id_str, minute_id,
                        persona_id=persona_id,
                    )

                outputs[sn] = out
                duration = int((time.time() - t0) * 1000)
                # Save prompt and output for debugging (Stage 7-9 include _prompt)
                result_entry = {"status": "completed", "duration_ms": duration}
                if isinstance(out, dict):
                    if out.get("_prompt"):
                        result_entry["prompt"] = out["_prompt"][:5000]
                    # Save output without _prompt and large internal fields
                    clean_out = {k: v for k, v in out.items() if not k.startswith("_")}
                    result_entry["output"] = clean_out
                stage_results[sn] = result_entry
                logger.info("Proposal stage %d completed in %dms", sn, duration)

                # Emit stage_chunk with formatted content
                if sn == 6 and isinstance(out, dict):
                    from app.services.proposal_formatters import format_stage6
                    yield sse_event("stage_chunk", {"stage": 6, "content": format_stage6(out)})
                elif sn == 7 and isinstance(out, dict):
                    yield sse_event("stage_chunk", {
                        "stage": 7,
                        "content": _format_stage7(out),
                    })
                elif sn == 8 and isinstance(out, dict):
                    yield sse_event("stage_chunk", {
                        "stage": 8,
                        "content": _format_stage8(out),
                    })
                elif sn == 9 and isinstance(out, dict):
                    yield sse_event("stage_chunk", {
                        "stage": 9,
                        "content": _format_stage9(out),
                    })
                elif sn == 10 and isinstance(out, dict) and "pages" in out:
                    for page in out["pages"]:
                        yield sse_event("stage_chunk", {
                            "stage": 10,
                            "content": f"### ページ {page['page_number']}: {page.get('title', '')}\n\n{page['markdown_content']}",
                            "page_number": page["page_number"],
                        })

                yield sse_event("stage_complete", {"stage": sn, "duration_ms": duration})

            # Return final result (document_id)
            if outputs.get(10) and isinstance(outputs[10], dict):
                yield outputs[10]

        except Exception as e:
            logger.error("Proposal stages failed: %s", e, exc_info=True)

    def _build_stage_sections(self, config: PipelineConfigData, stage_num: int, output: dict) -> list[dict]:
        """Build template sections for a single completed stage."""
        sections = []
        for sec in config.output_template.sections:
            if sec.stage == stage_num:
                content = format_section_content(sec.id, sec.stage, output)
                sections.append({
                    "id": sec.id,
                    "title": sec.title,
                    "stage": sec.stage,
                    "content": content,
                    "has_data": bool(content.strip()),
                })
        return sections

    def _build_sections(self, config: PipelineConfigData, outputs: dict) -> list[dict]:
        """Build final output sections from stage outputs and template."""
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

    async def _create_run(self, tenant_id, user_id, minute_id):
        from app.services.pipeline_run_db import create_pipeline_run
        return await create_pipeline_run(tenant_id, user_id, minute_id)

    async def _update_run(self, run_id, stage_results, total_duration, status,
                          error_stage=None, error_message=None, sections=None):
        from app.services.pipeline_run_db import update_pipeline_run
        await update_pipeline_run(run_id, stage_results, total_duration, status,
                                  error_stage, error_message, sections)


# Module-level singleton
proposal_pipeline_service = ProposalPipelineService()
