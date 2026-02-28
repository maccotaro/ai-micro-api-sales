"""Stage 0-5 implementations for the 6-stage proposal pipeline."""
import asyncio
import json
import logging
from datetime import datetime
from typing import Optional
from uuid import UUID

import httpx
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.model_settings_client import get_chat_num_ctx
from app.models.meeting import MeetingMinute
from app.services.llm_client import LLMClient
from app.services.pipeline_config import PipelineConfigData, KBMappingCategory
from app.services.pipeline_data_loaders import (
    load_product_data,
    load_simulation_data,
    load_wage_data,
    load_publication_records,
    load_campaign_data,
    load_seasonal_data,
    load_document_links,
)
from app.services.pipeline_helpers import parse_json_response, validate_evidence
from app.services.pipeline_prompts import (
    STAGE1_SYSTEM_PROMPT,
    STAGE2_SYSTEM_PROMPT,
    STAGE3_SYSTEM_PROMPT,
    STAGE4_SYSTEM_PROMPT,
    STAGE5_SYSTEM_PROMPT,
    build_kb_context_block,
)

logger = logging.getLogger(__name__)


# ============================================================
# Stage 0: Context Collection (non-LLM)
# ============================================================
async def stage0_collect_context(
    minute_id: UUID,
    tenant_id: UUID,
    config: PipelineConfigData,
    db: Session,
) -> dict:
    """Collect all context needed by subsequent stages."""
    # 1. Load meeting minute
    minute = db.query(MeetingMinute).filter(MeetingMinute.id == minute_id).first()
    if not minute:
        raise ValueError(f"Meeting minute not found: {minute_id}")
    # super_admin (tenant_id=default) can access all tenants' data
    is_default_tenant = str(tenant_id) == "00000000-0000-0000-0000-000000000000"
    if minute.tenant_id and not is_default_tenant and str(minute.tenant_id) != str(tenant_id):
        raise PermissionError("Tenant mismatch for meeting minute")

    meeting_data = {
        "company_name": minute.company_name,
        "industry": minute.industry or "",
        "area": minute.area or "",
        "raw_text": minute.raw_text or "",
        "parsed_json": minute.parsed_json or {},
        "meeting_date": str(minute.meeting_date) if minute.meeting_date else "",
        "next_action_date": minute.next_action_date.isoformat() if minute.next_action_date else "",
    }

    # For super_admin (default tenant), use the minute's tenant_id for KB search
    # so that tenant filter matches the actual KB data
    search_tenant_id = tenant_id
    if is_default_tenant and minute.tenant_id:
        search_tenant_id = minute.tenant_id

    # 2. KB searches (parallel per category)
    kb_categories = config.get_kb_categories_for_stage(0)
    kb_results = await _search_kbs(
        kb_categories, meeting_data, search_tenant_id
    )

    # 3. Load DB data (products, simulation, wages, publications, campaigns)
    product_data = load_product_data(db, meeting_data)
    simulation_data = load_simulation_data(db, meeting_data)
    wage_data = load_wage_data(db, meeting_data)
    product_names = [p["product_name"] for p in product_data if p.get("product_name")]
    publication_data = load_publication_records(db, product_names, meeting_data)
    campaign_data = load_campaign_data(db)

    # 4. Load seasonal trend data
    current_month = datetime.now().month
    seasonal_data = load_seasonal_data(
        db, current_month, meeting_data.get("area", ""), meeting_data.get("industry", "")
    )
    document_links = load_document_links(db, meeting_data)

    return {
        "meeting": meeting_data,
        "kb_results": kb_results,
        "product_data": product_data,
        "simulation_data": simulation_data,
        "wage_data": wage_data,
        "publication_data": publication_data,
        "campaign_data": campaign_data,
        "seasonal_data": seasonal_data,
        "document_links": document_links,
        "search_tenant_id": search_tenant_id,
    }


# ============================================================
# Stage 1-5: LLM Stages
# ============================================================
async def stage1_issue_structuring(
    context: dict,
    config: PipelineConfigData,
    llm_client: LLMClient,
    tenant_id: UUID,
    pipeline_run_id: Optional[str] = None,
) -> dict:
    """Stage 1: Extract and structure issues with BANT-C analysis.

    KB context is intentionally excluded from Stage 1 to prevent
    the LLM from fabricating issues based on external KB content.
    Stage 1 must extract issues solely from the meeting text.
    KB results are still fetched and merged for use in later stages.
    """
    stage_cfg = config.get_stage(1)
    kb_cats = config.get_kb_categories_for_stage(1)
    search_tid = context.get("search_tenant_id", tenant_id)
    kb_results = await _search_kbs(kb_cats, context["meeting"], search_tid)
    _merge_kb_results(context["kb_results"], kb_results)

    prompt = STAGE1_SYSTEM_PROMPT.format(
        meeting_text=context["meeting"]["raw_text"],
        parsed_json=json.dumps(context["meeting"]["parsed_json"], ensure_ascii=False, indent=2),
    )

    result = await _call_llm(llm_client, prompt, stage_cfg, tenant_id, stage_num=1, pipeline_run_id=pipeline_run_id)

    # Post-process: validate evidence fields against actual meeting text
    raw_text = context["meeting"]["raw_text"]
    result = validate_evidence(result, raw_text)

    return result


async def stage2_reverse_planning(
    context: dict,
    stage1_output: dict,
    config: PipelineConfigData,
    llm_client: LLMClient,
    tenant_id: UUID,
    pipeline_run_id: Optional[str] = None,
) -> dict:
    """Stage 2: Reverse-calculation planning with DB data."""
    stage_cfg = config.get_stage(2)
    kb_cats = config.get_kb_categories_for_stage(2)
    search_tid = context.get("search_tenant_id", tenant_id)
    kb_results = await _search_kbs(kb_cats, context["meeting"], search_tid)
    _merge_kb_results(context["kb_results"], kb_results)

    # Check stage config flags for optional data inclusion
    sim_data = context["simulation_data"] if stage_cfg.use_simulation is not False else []
    wage = context["wage_data"] if stage_cfg.use_wage_data is not False else []

    # Extract budget info from Stage 1 BANT-C output
    budget_range = _extract_budget_range(stage1_output)

    # Get next_action_date and seasonal context
    next_action_date = context["meeting"].get("next_action_date", "")
    current_month = datetime.now().month
    seasonal_text = _build_seasonal_text(context.get("seasonal_data", {}), current_month)

    prompt = STAGE2_SYSTEM_PROMPT.format(
        stage1_output=json.dumps(stage1_output, ensure_ascii=False, indent=2),
        kb_context=build_kb_context_block(kb_results),
        product_data=json.dumps(context["product_data"], ensure_ascii=False, indent=2),
        simulation_data=json.dumps(sim_data, ensure_ascii=False, indent=2),
        wage_data=json.dumps(wage, ensure_ascii=False, indent=2),
        publication_data=json.dumps(context.get("publication_data", []), ensure_ascii=False, indent=2),
        campaign_data=json.dumps(context.get("campaign_data", []), ensure_ascii=False, indent=2),
        budget_range=budget_range,
        next_action_date=next_action_date,
        current_month=str(current_month),
        seasonal_context=seasonal_text,
    )

    return await _call_llm(llm_client, prompt, stage_cfg, tenant_id, stage_num=2, pipeline_run_id=pipeline_run_id)


async def stage3_action_plan(
    context: dict,
    stage1_output: dict,
    stage2_output: dict,
    config: PipelineConfigData,
    llm_client: LLMClient,
    tenant_id: UUID,
    pipeline_run_id: Optional[str] = None,
) -> dict:
    """Stage 3: Detailed action plan generation."""
    stage_cfg = config.get_stage(3)
    kb_cats = config.get_kb_categories_for_stage(3)
    search_tid = context.get("search_tenant_id", tenant_id)
    kb_results = await _search_kbs(kb_cats, context["meeting"], search_tid)

    prompt = STAGE3_SYSTEM_PROMPT.format(
        stage1_output=json.dumps(stage1_output, ensure_ascii=False, indent=2),
        stage2_output=json.dumps(stage2_output, ensure_ascii=False, indent=2),
        kb_context=build_kb_context_block(kb_results),
        company_name=context["meeting"].get("company_name", ""),
    )

    return await _call_llm(llm_client, prompt, stage_cfg, tenant_id, stage_num=3, pipeline_run_id=pipeline_run_id)


async def stage4_ad_copy(
    context: dict,
    stage1_output: dict,
    stage2_output: dict,
    config: PipelineConfigData,
    llm_client: LLMClient,
    tenant_id: UUID,
    pipeline_run_id: Optional[str] = None,
) -> dict:
    """Stage 4: Ad copy / draft proposal generation."""
    stage_cfg = config.get_stage(4)
    kb_cats = config.get_kb_categories_for_stage(4)
    search_tid = context.get("search_tenant_id", tenant_id)
    kb_results = await _search_kbs(kb_cats, context["meeting"], search_tid)

    catchcopy_count = stage_cfg.catchcopy_count or 5 if stage_cfg.generate_catchcopy is not False else 0
    prompt = STAGE4_SYSTEM_PROMPT.format(
        stage1_output=json.dumps(stage1_output, ensure_ascii=False, indent=2),
        stage2_output=json.dumps(stage2_output, ensure_ascii=False, indent=2),
        kb_context=build_kb_context_block(kb_results),
        catchcopy_count=catchcopy_count,
        meeting_text=context["meeting"]["raw_text"],
    )

    return await _call_llm(llm_client, prompt, stage_cfg, tenant_id, stage_num=4, pipeline_run_id=pipeline_run_id)


async def stage5_checklist_summary(
    context: dict,
    stage1_output: dict,
    stage2_output: dict,
    stage3_output: dict,
    stage4_output: Optional[dict],
    config: PipelineConfigData,
    llm_client: LLMClient,
    tenant_id: UUID,
    pipeline_run_id: Optional[str] = None,
) -> dict:
    """Stage 5: Checklist + summary generation."""
    stage_cfg = config.get_stage(5)

    stage4_text = json.dumps(stage4_output, ensure_ascii=False, indent=2) if stage4_output else "（Stage 4はスキップされました）"
    doc_links = json.dumps(context.get("document_links", []), ensure_ascii=False, indent=2)

    prompt = STAGE5_SYSTEM_PROMPT.format(
        stage1_output=json.dumps(stage1_output, ensure_ascii=False, indent=2),
        stage2_output=json.dumps(stage2_output, ensure_ascii=False, indent=2),
        stage3_output=json.dumps(stage3_output, ensure_ascii=False, indent=2),
        stage4_output=stage4_text,
        meeting_text=context["meeting"]["raw_text"],
        document_links=doc_links,
    )

    return await _call_llm(llm_client, prompt, stage_cfg, tenant_id, stage_num=5, pipeline_run_id=pipeline_run_id)


# ============================================================
# Helper Functions
# ============================================================
async def _call_llm(
    llm_client: LLMClient,
    system_prompt: str,
    stage_cfg,
    tenant_id: UUID,
    stage_num: int,
    pipeline_run_id: Optional[str] = None,
) -> dict:
    """Call LLM and parse JSON response."""
    # Use prompt_override if configured
    final_prompt = stage_cfg.prompt_override if stage_cfg.prompt_override else system_prompt
    messages = [
        {"role": "system", "content": final_prompt},
        {"role": "user", "content": "上記の情報に基づいて、指定されたJSON形式で出力してください。"},
    ]

    result = await llm_client.chat(
        messages=messages,
        service_name="api-sales",
        model=stage_cfg.model,
        temperature=stage_cfg.temperature or 0.3,
        max_tokens=stage_cfg.max_tokens,
        tenant_id=str(tenant_id),
        pipeline_stage=stage_num,
        pipeline_run_id=pipeline_run_id,
        provider_options={"num_ctx": get_chat_num_ctx()},
    )

    response_text = result.get("response", "")
    return parse_json_response(response_text)


async def _search_kbs(
    categories: dict[str, KBMappingCategory],
    meeting_data: dict,
    tenant_id: UUID,
) -> dict[str, list[str]]:
    """Search KBs for all categories in parallel."""
    if not categories:
        return {}

    async def _search_single(cat_name: str, cat: KBMappingCategory) -> tuple[str, list[str]]:
        if not cat.knowledge_base_ids:
            return cat_name, []

        query = cat.search_query_template.format(
            industry=meeting_data.get("industry", ""),
            media_name=meeting_data.get("company_name", ""),
            issue_category="",
            area=meeting_data.get("area", ""),
        )

        chunks = []
        for kb_id in cat.knowledge_base_ids:
            try:
                async with httpx.AsyncClient(timeout=15.0) as client:
                    resp = await client.post(
                        f"{settings.rag_service_url}/internal/search/hybrid",
                        json={
                            "query": query,
                            "knowledge_base_id": kb_id,
                            "tenant_id": str(tenant_id),
                            "top_k": cat.max_chunks,
                        },
                        headers={
                            "X-Internal-Secret": settings.internal_api_secret,
                            "Content-Type": "application/json",
                        },
                    )
                    if resp.status_code == 200:
                        data = resp.json()
                        results = data.get("results", [])
                        logger.info("KB search %s: %d results (kb=%s)", cat_name, len(results), kb_id)
                        chunks.extend(r.get("content", "") for r in results if r.get("content"))
                    else:
                        logger.warning(
                            "KB search %s failed: status=%s kb=%s",
                            cat_name, resp.status_code, kb_id,
                        )
            except Exception as e:
                logger.warning("KB search failed for %s/%s: %s", cat_name, kb_id, e)

        return cat_name, chunks[:cat.max_chunks]

    tasks = [_search_single(name, cat) for name, cat in categories.items()]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    kb_results = {}
    for r in results:
        if isinstance(r, tuple):
            kb_results[r[0]] = r[1]
    return kb_results


def _merge_kb_results(base: dict, new: dict) -> None:
    """Merge new KB results into base, extending chunk lists."""
    for key, chunks in new.items():
        if key in base:
            base[key].extend(chunks)
        else:
            base[key] = chunks


def _extract_budget_range(stage1_output: dict) -> str:
    """Extract budget info from Stage 1 BANT-C output."""
    for issue in stage1_output.get("issues", []):
        bant = issue.get("bant_c", {})
        budget = bant.get("budget", {})
        est = budget.get("estimated_range")
        if est and (est.get("min") is not None or est.get("max") is not None):
            return json.dumps(est, ensure_ascii=False)
    return "予算情報なし"


def _build_seasonal_text(seasonal_data: dict, current_month: int) -> str:
    """Build seasonal context text from loaded seasonal data."""
    if not seasonal_data:
        return "（季節データなし）"
    lines = [f"【{current_month}月の採用トレンド】"]
    lines.append(f"採用強度: {seasonal_data.get('hiring_intensity', '不明')}")
    lines.append(f"概要: {seasonal_data.get('trend_summary', '')}")
    factors = seasonal_data.get("key_factors", [])
    if factors:
        lines.append(f"要因: {', '.join(factors)}")
    lines.append(f"アドバイス: {seasonal_data.get('advice', '')}")
    return "\n".join(lines)
