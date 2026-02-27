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
            yield _sse("error", {"message": "パイプラインが無効です"})
            return

        total_stages = sum(1 for i in range(6) if config.get_stage(i).enabled)
        yield _sse("pipeline_start", {
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
                yield _sse("stage_start", {"stage": 0, "name": STAGE_NAMES[0]})
                t0 = time.time()
                context = await stage0_collect_context(
                    minute_id, tenant_id, config, db
                )
                duration = int((time.time() - t0) * 1000)
                stage_results[0] = {"status": "completed", "duration_ms": duration}
                yield _sse("stage_info", {
                    "stage": 0,
                    "company_name": context["meeting"].get("company_name", ""),
                    "industry": context["meeting"].get("industry", ""),
                })
                # Send context summary as stage_chunk for display
                yield _sse("stage_chunk", {
                    "stage": 0,
                    "content": _format_context_summary(context),
                })
                yield _sse("stage_complete", {"stage": 0, "duration_ms": duration})

            if context is None:
                yield _sse("error", {"message": "Stage 0 is disabled but required"})
                return

            # Create pipeline run record
            run_id = await self._create_run(tenant_id, user_id, minute_id)

            # Stages 1-5
            outputs = {}
            for stage_num in range(1, 6):
                stage_cfg = config.get_stage(stage_num)
                if not stage_cfg.enabled:
                    yield _sse("stage_info", {
                        "stage": stage_num,
                        "name": STAGE_NAMES[stage_num],
                        "skipped": True,
                    })
                    stage_results[stage_num] = {"status": "skipped"}
                    continue

                yield _sse("stage_start", {
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
                    formatted = _format_stage_output(stage_num, output)
                    yield _sse("stage_chunk", {
                        "stage": stage_num,
                        "content": formatted,
                    })
                    yield _sse("stage_complete", {
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
                    yield _sse("stage_complete", {
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

            yield _sse("pipeline_complete", {
                "total_duration_ms": total_duration,
                "status": status,
            })
            yield _sse("result", {
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
            yield _sse("error", {"message": str(e)})

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
                prev_outputs.get(1, {}), prev_outputs.get(2, {}),
                prev_outputs.get(3, {}), prev_outputs.get(4),
                config, self.llm_client, tenant_id,
                pipeline_run_id=run_id_str,
            )
        raise ValueError(f"Unknown stage: {stage_num}")

    def _build_sections(self, config: PipelineConfigData, outputs: dict) -> list[dict]:
        """Build final output sections from stage outputs and template."""
        sections = []
        stage_to_content = {
            1: lambda o: _format_issues(o),
            2: lambda o: _format_proposals(o),
            3: lambda o: _format_action_plan(o),
            4: lambda o: _format_ad_copy(o),
            5: lambda o: _format_checklist_summary(o),
        }

        for section_def in config.output_template.sections:
            stage = section_def.stage
            output = outputs.get(stage)
            content = ""
            if output:
                formatter = stage_to_content.get(stage)
                content = formatter(output) if formatter else json.dumps(output, ensure_ascii=False)
                # Fallback if formatter returned empty (e.g. LLM returned raw_response)
                if not content.strip() and "raw_response" in output:
                    content = f"```\n{output['raw_response']}\n```"
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


# ============================================================
# Output Formatters
# ============================================================
def _sse(event_type: str, data: dict) -> str:
    """Format SSE event string."""
    data["type"] = event_type
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


def _format_context_summary(context: dict) -> str:
    """Format Stage 0 context collection as markdown summary."""
    lines = []
    meeting = context.get("meeting", {})
    lines.append(f"### 商談情報")
    lines.append(f"- **企業名**: {meeting.get('company_name', '不明')}")
    if meeting.get("industry"):
        lines.append(f"- **業種**: {meeting['industry']}")
    if meeting.get("area"):
        lines.append(f"- **地域**: {meeting['area']}")
    if meeting.get("meeting_date"):
        lines.append(f"- **商談日**: {meeting['meeting_date']}")
    lines.append("")

    # KB search results summary
    kb_results = context.get("kb_results", {})
    if kb_results:
        lines.append("### ナレッジベース検索結果")
        for cat_name, results in kb_results.items():
            lines.append(f"- **{cat_name}**: {len(results)}件取得")
        lines.append("")

    # Product data summary
    products = context.get("product_data", [])
    if products:
        lines.append(f"### 商品データ: {len(products)}件")
        for p in products[:5]:
            lines.append(f"- {p.get('name', '')}")
        if len(products) > 5:
            lines.append(f"- ...他 {len(products) - 5}件")
        lines.append("")

    # Publication records
    pub_data = context.get("publication_data", [])
    if pub_data:
        lines.append(f"### 前回掲載実績: {len(pub_data)}件")
        lines.append("")

    # Campaign data
    campaigns = context.get("campaign_data", [])
    if campaigns:
        lines.append(f"### キャンペーン情報: {len(campaigns)}件")
        lines.append("")

    # Simulation / Wage data
    sim = context.get("simulation_data", [])
    wage = context.get("wage_data", [])
    if sim:
        lines.append(f"### シミュレーションパラメータ: {len(sim)}件")
    if wage:
        lines.append(f"### 地域別時給データ: {len(wage)}件")

    return "\n".join(lines)


def _format_stage_output(stage_num: int, output: dict) -> str:
    """Format a stage output as markdown using the appropriate formatter."""
    formatters = {
        1: _format_issues,
        2: _format_proposals,
        3: _format_action_plan,
        4: _format_ad_copy,
        5: _format_checklist_summary,
    }
    formatter = formatters.get(stage_num)
    if formatter:
        result = formatter(output)
        if result.strip():
            return result
    # Fallback: if formatter returned empty or no formatter, show raw
    if "raw_response" in output:
        return f"```\n{output['raw_response']}\n```"
    return f"```json\n{json.dumps(output, ensure_ascii=False, indent=2)}\n```"


def _format_issues(output: dict) -> str:
    """Format Stage 1 issues as markdown."""
    lines = []
    for issue in output.get("issues", []):
        lines.append(f"### {issue.get('id', '')} {issue.get('title', '')}")
        lines.append(f"**カテゴリ**: {issue.get('category', '')}")
        lines.append(f"\n{issue.get('detail', '')}")
        bant = issue.get("bant_c", {})
        if bant:
            lines.append("\n| BANT-C | ステータス | 詳細 |")
            lines.append("|--------|-----------|------|")
            for key in ["budget", "authority", "need", "timeline", "competitor"]:
                item = bant.get(key, {})
                lines.append(f"| {key.upper()} | {item.get('status', '')} | {item.get('detail', '')} |")
        lines.append("")
    return "\n".join(lines)


def _format_proposals(output: dict) -> str:
    """Format Stage 2 proposals as markdown."""
    lines = []
    for prop in output.get("proposals", []):
        lines.append(f"### {prop.get('media_name', '')} - {prop.get('product_name', '')}")
        lines.append(f"**課題対応**: {prop.get('issue_id', '')}")
        lines.append(f"**プラン**: {prop.get('plan_detail', '')}")
        rc = prop.get("reverse_calc", {})
        if rc:
            lines.append(f"\n**逆算根拠**: 採用目標 {rc.get('hiring_goal', '-')}名")
            lines.append(f"→ 必要応募 {rc.get('required_applications', '-')}件")
            lines.append(f"→ 必要PV {rc.get('required_pv', '-')}")
        price = prop.get("price")
        if price:
            lines.append(f"\n**料金**: ¥{price:,}" if isinstance(price, (int, float)) else f"\n**料金**: {price}")
        lines.append("")

    total = output.get("total_budget")
    if total:
        lines.append(f"### 合計予算: ¥{total:,}" if isinstance(total, (int, float)) else f"### 合計予算: {total}")

    agenda = output.get("agenda_items", [])
    if agenda:
        lines.append("\n### 次回商談アジェンダ")
        for i, item in enumerate(agenda, 1):
            lines.append(f"{i}. {item}")

    return "\n".join(lines)


def _format_action_plan(output: dict) -> str:
    """Format Stage 3 action plan as markdown."""
    lines = []
    for action in output.get("action_plan", []):
        lines.append(f"### {action.get('id', '')} {action.get('title', '')}")
        lines.append(f"**優先度**: {action.get('priority', '')}")
        lines.append(f"**対応課題**: {action.get('related_issue_id', '')}")
        lines.append(f"\n{action.get('description', '')}")
        for st in action.get("subtasks", []):
            lines.append(f"- [ ] {st.get('title', '')}: {st.get('detail', '')}")
        lines.append("")
    return "\n".join(lines)


def _format_ad_copy(output: dict) -> str:
    """Format Stage 4 ad copy as markdown."""
    lines = []
    persona = output.get("target_persona", {})
    if persona:
        lines.append("### ターゲットペルソナ")
        lines.append(f"- **年齢層**: {persona.get('age_range', '')}")
        lines.append(f"- **現職**: {persona.get('current_job', '')}")
        lines.append(f"- **動機**: {persona.get('motivation', '')}")
        lines.append("")

    copies = output.get("catchcopy_proposals", [])
    if copies:
        lines.append("### キャッチコピー案")
        for i, c in enumerate(copies, 1):
            lines.append(f"{i}. **{c.get('copy', '')}**")
            lines.append(f"   {c.get('concept', '')}")
        lines.append("")

    draft = output.get("job_description_draft", {})
    if draft:
        lines.append(f"### 求人タイトル案: {draft.get('title', '')}")
        lines.append(f"\n**仕事内容**:\n{draft.get('work_content', '')}")
        lines.append(f"\n**応募資格**:\n{draft.get('qualifications', '')}")

    return "\n".join(lines)


def _format_checklist_summary(output: dict) -> str:
    """Format Stage 5 checklist and summary as markdown."""
    lines = []
    checklist = output.get("checklist", [])
    if checklist:
        lines.append("### チェックリスト")
        for item in checklist:
            lines.append(f"- [ ] **{item.get('category', '')}** ({item.get('related_issue_id', '')})")
            lines.append(f"  {item.get('item', '')}")
            q = item.get("question_example", "")
            if q:
                lines.append(f"  *質問例: {q}*")
        lines.append("")

    summary = output.get("summary", {})
    if summary:
        lines.append("### まとめ")
        lines.append(summary.get("overview", ""))
        lines.append("")
        for kp in summary.get("key_points", []):
            lines.append(f"- {kp.get('point', '')} (課題: {', '.join(kp.get('related_issues', []))})")
        ns = summary.get("next_steps", [])
        if ns:
            lines.append("\n### 次のステップ")
            for i, step in enumerate(ns, 1):
                lines.append(f"{i}. {step}")

    return "\n".join(lines)
