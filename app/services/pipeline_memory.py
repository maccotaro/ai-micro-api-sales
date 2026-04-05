"""SharedMemory and MessageBus helpers for the proposal pipeline.

Provides:
- Factory functions for creating SharedMemory/MessageBus instances
- Stage output save/load helpers
- Stage summary extraction for LLM prompt optimization
- Pipeline resume logic
"""
import json
import logging
import time
from typing import Any, Optional
from uuid import UUID

logger = logging.getLogger(__name__)


def create_pipeline_memory(redis_url: str, redis_sm_db: int):
    """Create SharedMemory and MessageBus instances, returning (sm, mb) tuple.

    Returns (None, None) if imports or connections fail.
    """
    try:
        from app.services.shared_memory import SharedMemory
        from app.services.message_bus import MessageBus

        sm = SharedMemory(redis_url=redis_url, db=redis_sm_db)
        mb = MessageBus(redis_url=redis_url, db=redis_sm_db)
        return sm, mb
    except Exception as e:
        logger.warning("Failed to create SharedMemory/MessageBus: %s", e)
        return None, None


def _sm_key(tenant_id: UUID, run_id: str, stage_num: int) -> str:
    """Build SharedMemory key for a pipeline stage."""
    return f"sm:pipeline:{tenant_id}:{run_id}:stage:{stage_num}"


def save_stage_output(
    shared_memory, tenant_id: UUID, run_id: Optional[str],
    stage_num: int, output: Any,
) -> None:
    """Save stage output to SharedMemory if available."""
    if shared_memory and run_id:
        try:
            shared_memory.set(_sm_key(tenant_id, run_id, stage_num), output)
        except Exception as e:
            logger.warning("Failed to save stage %d to SharedMemory: %s", stage_num, e)


def load_stage_output(
    shared_memory, tenant_id: UUID, run_id: str, stage_num: int,
) -> Optional[Any]:
    """Load stage output from SharedMemory."""
    if not shared_memory:
        return None
    try:
        return shared_memory.get(_sm_key(tenant_id, run_id, stage_num))
    except Exception as e:
        logger.warning("Failed to load stage %d from SharedMemory: %s", stage_num, e)
        return None


def find_resume_point(shared_memory, tenant_id: UUID, run_id: str) -> tuple[dict, int]:
    """Find where to resume a pipeline from SharedMemory.

    Returns:
        (outputs_dict, first_missing_stage) where outputs_dict contains
        all completed stage outputs and first_missing_stage is the stage
        to start execution from.
    """
    outputs = {}
    first_missing = 0
    for stage_num in range(11):
        data = load_stage_output(shared_memory, tenant_id, run_id, stage_num)
        if data is not None:
            outputs[stage_num] = data
        else:
            first_missing = stage_num
            break
    else:
        # All 11 stages completed
        first_missing = 11
    return outputs, first_missing


def publish_stage_event(
    message_bus, run_id: Optional[str],
    stage_num: int, status: str,
    stage_name: str = "", duration_ms: int = 0, error: str = "",
) -> None:
    """Publish a stage progress event to MessageBus."""
    if not message_bus or not run_id:
        return
    try:
        event = {
            "stage": stage_num,
            "status": status,
            "total_stages": 11,
        }
        if status == "started":
            event["stage_name"] = stage_name
        elif status == "completed":
            event["duration_ms"] = duration_ms
        elif status == "failed":
            event["error"] = error
        message_bus.publish(f"mb:pipeline:progress:{run_id}", event)
    except Exception as e:
        logger.warning("Failed to publish stage event: %s", e)


# ============================================================
# Stage Summary Extraction
# ============================================================

def extract_stage_summary(stage_num: int, output: dict, max_chars: int = 500) -> str:
    """Extract a concise summary from a stage output for use in LLM prompts.

    Instead of passing full stage outputs to subsequent LLM prompts,
    we extract only the key conclusion fields.
    """
    if not output or not isinstance(output, dict):
        return ""

    if stage_num == 1:
        return _summarize_stage1(output, max_chars)
    elif stage_num == 2:
        return _summarize_stage2(output, max_chars)
    elif stage_num == 3:
        return _summarize_stage3(output, max_chars)
    elif stage_num == 4:
        return _summarize_stage4(output, max_chars)
    elif stage_num == 5:
        return _summarize_stage5(output, max_chars)
    elif stage_num == 7:
        return _summarize_stage7(output, max_chars)
    elif stage_num == 8:
        return _summarize_stage8(output, max_chars)
    elif stage_num == 9:
        return _summarize_stage9(output, max_chars)
    else:
        # Stages 0, 6, 10: no standard summary
        return json.dumps(output, ensure_ascii=False)[:max_chars]


def _summarize_stage1(output: dict, max_chars: int) -> str:
    """Stage 1: Extract issue titles and BANT-C scores."""
    issues = output.get("issues", [])
    parts = []
    for issue in issues[:3]:
        title = issue.get("title", "")
        severity = issue.get("severity", "")
        bant = issue.get("bant_c", {})
        bant_summary = ", ".join(
            f"{k}={v.get('score', '?')}" for k, v in bant.items()
            if isinstance(v, dict) and "score" in v
        )
        parts.append(f"- {title} (重要度: {severity}, BANT-C: {bant_summary})")
    return "\n".join(parts)[:max_chars]


def _summarize_stage2(output: dict, max_chars: int) -> str:
    """Stage 2: Extract plan names and key recommendations."""
    plans = output.get("plans", [])
    if not plans:
        # Try alternative structure
        rec = output.get("recommendation", "")
        if rec:
            return str(rec)[:max_chars]
        return json.dumps(output, ensure_ascii=False)[:max_chars]
    parts = []
    for plan in plans[:3]:
        name = plan.get("name", plan.get("plan_name", ""))
        total = plan.get("total_cost", plan.get("monthly_cost", ""))
        parts.append(f"- {name}: {total}")
    return "\n".join(parts)[:max_chars]


def _summarize_stage3(output: dict, max_chars: int) -> str:
    """Stage 3: Extract action items and timeline."""
    actions = output.get("action_items", output.get("actions", []))
    if not actions:
        return json.dumps(output, ensure_ascii=False)[:max_chars]
    parts = []
    for act in actions[:5]:
        task = act.get("task", act.get("title", ""))
        deadline = act.get("deadline", "")
        parts.append(f"- {task} ({deadline})")
    return "\n".join(parts)[:max_chars]


def _summarize_stage4(output: dict, max_chars: int) -> str:
    """Stage 4: Extract catchcopy and key proposals."""
    catchcopies = output.get("catchcopies", output.get("catch_copy", []))
    if isinstance(catchcopies, list):
        cc_text = "、".join(str(c) for c in catchcopies[:3])
    else:
        cc_text = str(catchcopies)[:200]
    draft = output.get("draft_summary", output.get("proposal_summary", ""))
    return f"キャッチコピー: {cc_text}\n概要: {str(draft)[:200]}"[:max_chars]


def _summarize_stage5(output: dict, max_chars: int) -> str:
    """Stage 5: Extract checklist and summary."""
    summary = output.get("summary", output.get("executive_summary", ""))
    return str(summary)[:max_chars]


def _summarize_stage7(output: dict, max_chars: int) -> str:
    """Stage 7: Extract industry analysis and target insights."""
    industry = output.get("industry_analysis", {})
    target = output.get("target_insights", {})
    parts = []
    if isinstance(industry, dict):
        trends = industry.get("trends", industry.get("key_trends", ""))
        parts.append(f"業界: {str(trends)[:150]}")
    if isinstance(target, dict):
        needs = target.get("primary_needs", target.get("needs", ""))
        parts.append(f"ターゲット: {str(needs)[:150]}")
    return "\n".join(parts)[:max_chars]


def _summarize_stage8(output: dict, max_chars: int) -> str:
    """Stage 8: Extract strategy axes."""
    axes = output.get("strategy_axes", [])
    if not axes:
        return json.dumps(output, ensure_ascii=False)[:max_chars]
    parts = []
    for ax in axes[:3]:
        name = ax.get("axis_name", ax.get("name", ""))
        msg = ax.get("key_message", ax.get("message", ""))
        parts.append(f"- {name}: {msg}")
    return "\n".join(parts)[:max_chars]


def _summarize_stage9(output: dict, max_chars: int) -> str:
    """Stage 9: Extract story theme and page titles."""
    theme = output.get("story_theme", "")
    pages = output.get("pages", [])
    page_titles = ", ".join(p.get("title", "") for p in pages[:8])
    return f"テーマ: {theme}\nページ構成: {page_titles}"[:max_chars]


# ============================================================
# Section Building (extracted from ProposalPipelineService)
# ============================================================

def build_stage_sections(config, stage_num: int, output: dict) -> list[dict]:
    """Build template sections for a single completed stage."""
    from app.services.pipeline_formatters import format_section_content

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


def build_all_sections(config, outputs: dict) -> list[dict]:
    """Build final output sections from stage outputs and template."""
    from app.services.pipeline_formatters import format_section_content

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
