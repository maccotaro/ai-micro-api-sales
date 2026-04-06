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
from app.services.pipeline_memory import extract_stage_summary

logger = logging.getLogger(__name__)


# ============================================================
# Stage 0: Context Collection (non-LLM)
# ============================================================
async def stage0_collect_context(
    minute_id: UUID,
    tenant_id: UUID,
    config: PipelineConfigData,
    db: Session,
    user_id: Optional[UUID] = None,
    user_roles: Optional[list[str]] = None,
    user_clearance_level: Optional[str] = None,
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
        kb_categories, meeting_data, search_tenant_id, user_id=user_id,
        user_roles=user_roles, user_clearance_level=user_clearance_level,
    )

    # 3. Load DB data (products, simulation, wages, publications, campaigns)
    product_data = load_product_data(db, meeting_data)
    simulation_data = load_simulation_data(db, meeting_data)
    wage_data = load_wage_data(db, meeting_data)
    product_names = [p["product_name"] for p in product_data if p.get("product_name")]
    publication_data = load_publication_records(db, product_names, meeting_data)
    campaign_data = load_campaign_data(db)

    return {
        "meeting": meeting_data,
        "kb_results": kb_results,
        "product_data": product_data,
        "simulation_data": simulation_data,
        "wage_data": wage_data,
        "publication_data": publication_data,
        "campaign_data": campaign_data,
        "search_tenant_id": search_tenant_id,
    }


def _build_issues_summary(stage1_output: dict, meeting_data: dict) -> str:
    """Build a natural language summary of Stage 1 issues for KB search queries."""
    issues = stage1_output.get("issues", [])
    if not issues:
        return ""
    titles = "、".join(issue.get("title", "") for issue in issues[:3])
    return titles


# ============================================================
# Stage 1-5: LLM Stages
# ============================================================
async def stage1_issue_structuring(
    context: dict,
    config: PipelineConfigData,
    llm_client: LLMClient,
    tenant_id: UUID,
    pipeline_run_id: Optional[str] = None,
    persona_id: Optional[str] = None,
    user_id: Optional[UUID] = None,
    user_roles: Optional[list[str]] = None,
    user_clearance_level: Optional[str] = None,
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
    kb_results = await _search_kbs(
        kb_cats, context["meeting"], search_tid, user_id=user_id,
        user_roles=user_roles, user_clearance_level=user_clearance_level,
    )
    _merge_kb_results(context["kb_results"], kb_results)

    prompt = STAGE1_SYSTEM_PROMPT.format(
        meeting_text=context["meeting"]["raw_text"],
        parsed_json=json.dumps(context["meeting"]["parsed_json"], ensure_ascii=False, indent=2),
    )

    result = await _call_llm(llm_client, prompt, stage_cfg, tenant_id, stage_num=1, pipeline_run_id=pipeline_run_id, persona_id=persona_id)

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
    persona_id: Optional[str] = None,
    user_id: Optional[UUID] = None,
    user_roles: Optional[list[str]] = None,
    user_clearance_level: Optional[str] = None,
) -> dict:
    """Stage 2: Reverse-calculation planning with DB data."""
    stage_cfg = config.get_stage(2)
    kb_cats = config.get_kb_categories_for_stage(2)
    search_tid = context.get("search_tenant_id", tenant_id)
    issues_sum = _build_issues_summary(stage1_output, context["meeting"])
    kb_results = await _search_kbs(
        kb_cats, context["meeting"], search_tid, issues_summary=issues_sum,
        user_id=user_id, user_roles=user_roles, user_clearance_level=user_clearance_level,
    )
    _merge_kb_results(context["kb_results"], kb_results)

    # Check stage config flags for optional data inclusion
    sim_data = context["simulation_data"] if stage_cfg.use_simulation is not False else []
    wage = context["wage_data"] if stage_cfg.use_wage_data is not False else []

    # Extract budget info from Stage 1 BANT-C output
    budget_range = _extract_budget_range(stage1_output)

    # Get next_action_date and seasonal context from KB results
    next_action_date = context["meeting"].get("next_action_date", "")
    current_month = datetime.now().month
    seasonal_chunks = context.get("kb_results", {}).get("seasonal_knowledge", [])
    seasonal_text = _build_seasonal_text(seasonal_chunks, current_month)

    # Use concise summary for LLM prompt instead of full JSON
    stage1_summary = extract_stage_summary(1, stage1_output, max_chars=1500)
    prompt = STAGE2_SYSTEM_PROMPT.format(
        stage1_output=stage1_summary or json.dumps(stage1_output, ensure_ascii=False, indent=2)[:2000],
        kb_context=build_kb_context_block(kb_results),
        product_data=json.dumps(context["product_data"][:5], ensure_ascii=False, indent=2)[:1500],
        simulation_data=json.dumps(sim_data[:3], ensure_ascii=False, indent=2)[:800],
        wage_data=json.dumps(wage[:3], ensure_ascii=False, indent=2)[:600],
        publication_data=json.dumps(context.get("publication_data", [])[:3], ensure_ascii=False, indent=2)[:800],
        campaign_data=json.dumps(context.get("campaign_data", [])[:3], ensure_ascii=False, indent=2)[:600],
        budget_range=budget_range,
        next_action_date=next_action_date,
        current_month=str(current_month),
        seasonal_context=seasonal_text[:500],
    )

    return await _call_llm(llm_client, prompt, stage_cfg, tenant_id, stage_num=2, pipeline_run_id=pipeline_run_id, persona_id=persona_id)


async def stage3_action_plan(
    context: dict,
    stage1_output: dict,
    stage2_output: dict,
    config: PipelineConfigData,
    llm_client: LLMClient,
    tenant_id: UUID,
    pipeline_run_id: Optional[str] = None,
    persona_id: Optional[str] = None,
    user_id: Optional[UUID] = None,
    user_roles: Optional[list[str]] = None,
    user_clearance_level: Optional[str] = None,
) -> dict:
    """Stage 3: Detailed action plan generation."""
    stage_cfg = config.get_stage(3)
    kb_cats = config.get_kb_categories_for_stage(3)
    search_tid = context.get("search_tenant_id", tenant_id)
    issues_sum = _build_issues_summary(stage1_output, context["meeting"])
    kb_results = await _search_kbs(
        kb_cats, context["meeting"], search_tid, issues_summary=issues_sum,
        user_id=user_id, user_roles=user_roles, user_clearance_level=user_clearance_level,
    )

    stage1_summary = extract_stage_summary(1, stage1_output, max_chars=1000)
    stage2_summary = extract_stage_summary(2, stage2_output, max_chars=1500)
    prompt = STAGE3_SYSTEM_PROMPT.format(
        stage1_output=stage1_summary or json.dumps(stage1_output, ensure_ascii=False, indent=2)[:1500],
        stage2_output=stage2_summary or json.dumps(stage2_output, ensure_ascii=False, indent=2)[:2000],
        kb_context=build_kb_context_block(kb_results),
        company_name=context["meeting"].get("company_name", ""),
    )

    return await _call_llm(llm_client, prompt, stage_cfg, tenant_id, stage_num=3, pipeline_run_id=pipeline_run_id, persona_id=persona_id)


async def stage4_ad_copy(
    context: dict,
    stage1_output: dict,
    stage2_output: dict,
    config: PipelineConfigData,
    llm_client: LLMClient,
    tenant_id: UUID,
    pipeline_run_id: Optional[str] = None,
    persona_id: Optional[str] = None,
    user_id: Optional[UUID] = None,
    user_roles: Optional[list[str]] = None,
    user_clearance_level: Optional[str] = None,
) -> dict:
    """Stage 4: Ad copy / draft proposal generation."""
    stage_cfg = config.get_stage(4)
    kb_cats = config.get_kb_categories_for_stage(4)
    search_tid = context.get("search_tenant_id", tenant_id)
    issues_sum = _build_issues_summary(stage1_output, context["meeting"])
    kb_results = await _search_kbs(
        kb_cats, context["meeting"], search_tid, issues_summary=issues_sum,
        user_id=user_id, user_roles=user_roles, user_clearance_level=user_clearance_level,
    )

    catchcopy_count = stage_cfg.catchcopy_count or 5 if stage_cfg.generate_catchcopy is not False else 0
    stage1_summary = extract_stage_summary(1, stage1_output, max_chars=1000)
    stage2_summary = extract_stage_summary(2, stage2_output, max_chars=1500)
    prompt = STAGE4_SYSTEM_PROMPT.format(
        stage1_output=stage1_summary or json.dumps(stage1_output, ensure_ascii=False, indent=2)[:1500],
        stage2_output=stage2_summary or json.dumps(stage2_output, ensure_ascii=False, indent=2)[:2000],
        kb_context=build_kb_context_block(kb_results),
        catchcopy_count=catchcopy_count,
        meeting_text=context["meeting"]["raw_text"][:2000],
    )

    return await _call_llm(llm_client, prompt, stage_cfg, tenant_id, stage_num=4, pipeline_run_id=pipeline_run_id, persona_id=persona_id)


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
    persona_id: Optional[str] = None,
) -> dict:
    """Stage 5: Checklist + summary generation."""
    stage_cfg = config.get_stage(5)

    stage4_text = json.dumps(stage4_output, ensure_ascii=False, indent=2) if stage4_output else "（Stage 4はスキップされました）"
    reference_chunks = context.get("kb_results", {}).get("reference_materials", [])
    doc_links_text = _build_document_links_text(reference_chunks)

    stage1_summary = extract_stage_summary(1, stage1_output, max_chars=800)
    stage2_summary = extract_stage_summary(2, stage2_output, max_chars=1000)
    stage3_summary = extract_stage_summary(3, stage3_output, max_chars=1000)
    stage4_summary = extract_stage_summary(4, stage4_output, max_chars=800) if stage4_output else stage4_text
    prompt = STAGE5_SYSTEM_PROMPT.format(
        stage1_output=stage1_summary or json.dumps(stage1_output, ensure_ascii=False, indent=2)[:1500],
        stage2_output=stage2_summary or json.dumps(stage2_output, ensure_ascii=False, indent=2)[:2000],
        stage3_output=stage3_summary or json.dumps(stage3_output, ensure_ascii=False, indent=2)[:1500],
        stage4_output=stage4_summary[:1500],
        meeting_text=context["meeting"]["raw_text"][:2000],
        document_links=doc_links_text[:1000],
    )

    return await _call_llm(llm_client, prompt, stage_cfg, tenant_id, stage_num=5, pipeline_run_id=pipeline_run_id, persona_id=persona_id)


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
    persona_id: Optional[str] = None,
) -> dict:
    """Call LLM and parse JSON response."""
    # Use prompt_override if configured
    final_prompt = stage_cfg.prompt_override if stage_cfg.prompt_override else system_prompt
    user_msg = "上記の情報に基づいて、指定されたJSON形式で出力してください。"
    messages = [
        {"role": "system", "content": final_prompt},
        {"role": "user", "content": user_msg},
    ]

    # Dynamic max_tokens: estimate input tokens, allocate rest to output
    context_len = get_chat_num_ctx() or 16384
    # Rough estimate: ~3 chars per token for mixed JP/EN
    estimated_input = (len(final_prompt) + len(user_msg)) // 3
    max_tokens = stage_cfg.max_tokens
    if not max_tokens:
        max_tokens = min(4096, max(512, context_len - estimated_input - 256))
        logger.info(
            "Stage %d: dynamic max_tokens=%d (context=%d, est_input=%d)",
            stage_num, max_tokens, context_len, estimated_input,
        )

    result = await llm_client.chat(
        messages=messages,
        service_name="api-sales",
        model=stage_cfg.model,
        temperature=stage_cfg.temperature or 0.3,
        max_tokens=max_tokens,
        tenant_id=str(tenant_id),
        pipeline_stage=stage_num,
        pipeline_run_id=pipeline_run_id,
        provider_options={"num_ctx": context_len},
        persona_id=persona_id,
    )

    response_text = result.get("response", "")
    return parse_json_response(response_text)


async def _search_kbs(
    categories: dict[str, KBMappingCategory],
    meeting_data: dict,
    tenant_id: UUID,
    issues_summary: str = "",
    user_id: Optional[UUID] = None,
    user_roles: Optional[list[str]] = None,
    user_clearance_level: Optional[str] = None,
) -> dict[str, list[str]]:
    """Search KBs for all categories in parallel.

    Args:
        issues_summary: Natural language summary of Stage 1 issues.
            Injected into query template via {issues} variable.
    """
    if not categories:
        return {}

    async def _search_single(cat_name: str, cat: KBMappingCategory) -> tuple[str, list[str]]:
        if not cat.knowledge_base_ids:
            return cat_name, []

        query = cat.search_query_template.format(
            industry=meeting_data.get("industry", ""),
            media_name=meeting_data.get("company_name", ""),
            area=meeting_data.get("area", ""),
            month=datetime.now().month,
            issues=issues_summary,
        )

        chunks = []
        for kb_id in cat.knowledge_base_ids:
            try:
                async with httpx.AsyncClient(timeout=15.0) as client:
                    search_body = {
                            "query": query,
                            "knowledge_base_id": kb_id,
                            "tenant_id": str(tenant_id),
                            "top_k": cat.max_chunks,
                    }
                    if user_clearance_level or user_roles:
                        search_body["user_filters"] = {
                            "clearance_level": user_clearance_level or "internal",
                            "roles": user_roles or [],
                        }
                    if user_id:
                        search_body["user_id"] = str(user_id)
                    resp = await client.post(
                        f"{settings.rag_service_url}/internal/v1/search/hybrid",
                        json=search_body,
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


def _build_document_links_text(kb_reference_chunks: list[str]) -> str:
    """Build reference materials text from KB search results."""
    if not kb_reference_chunks:
        return "（参考資料なし）"
    lines = ["【参考資料（KB検索結果）】"]
    for i, chunk in enumerate(kb_reference_chunks, 1):
        lines.append(f"{i}. {chunk.strip()}")
    return "\n".join(lines)


def _build_seasonal_text(kb_seasonal_chunks: list[str], current_month: int) -> str:
    """Build seasonal context text from KB search results."""
    if not kb_seasonal_chunks:
        return "（季節データなし）"
    lines = [f"【{current_month}月の採用トレンド（KB検索結果）】"]
    for chunk in kb_seasonal_chunks:
        lines.append(chunk.strip())
    return "\n".join(lines)
