"""Stage 0-5 implementations for the 6-stage proposal pipeline.

Stage 0: Context collection (non-LLM)
Stage 1: Issue structuring + BANT-C check (LLM)
Stage 2: Reverse-calculation planning (LLM)
Stage 3: Action plan generation (LLM)
Stage 4: Ad copy / draft proposal (LLM)
Stage 5: Checklist + summary (LLM)
"""
import asyncio
import json
import logging
from typing import Optional
from uuid import UUID

import httpx
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.model_settings_client import get_chat_num_ctx
from app.db.session import SessionLocal
from app.models.meeting import MeetingMinute
from app.models.master import Product, Campaign, SimulationParam, WageData, MediaPricing
from app.services.llm_client import LLMClient
from app.services.publication_record_service import get_publication_records
from app.services.pipeline_config import PipelineConfigData, KBMappingCategory
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
    """Collect all context needed by subsequent stages.

    Returns dict with: meeting_minute, kb_results, product_data,
    simulation_data, wage_data.
    """
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

    # 3. Load product/pricing data from salesdb
    product_data = _load_product_data(db, meeting_data)

    # 4. Load simulation params
    simulation_data = _load_simulation_data(db, meeting_data)

    # 5. Load wage data
    wage_data = _load_wage_data(db, meeting_data)

    # 6. Load publication records (前回掲載実績)
    product_names = [p["name"] for p in product_data if p.get("name")]
    publication_data = _load_publication_records(db, product_names, meeting_data)

    # 7. Load campaign data
    campaign_data = _load_campaign_data(db)

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
    """Stage 1: Extract and structure issues with BANT-C analysis."""
    stage_cfg = config.get_stage(1)
    kb_cats = config.get_kb_categories_for_stage(1)
    search_tid = context.get("search_tenant_id", tenant_id)
    kb_results = await _search_kbs(kb_cats, context["meeting"], search_tid)
    _merge_kb_results(context["kb_results"], kb_results)

    prompt = STAGE1_SYSTEM_PROMPT.format(
        meeting_text=context["meeting"]["raw_text"],
        parsed_json=json.dumps(context["meeting"]["parsed_json"], ensure_ascii=False, indent=2),
        kb_context=build_kb_context_block(context["kb_results"]),
    )

    return await _call_llm(llm_client, prompt, stage_cfg, tenant_id, stage_num=1, pipeline_run_id=pipeline_run_id)


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

    prompt = STAGE2_SYSTEM_PROMPT.format(
        stage1_output=json.dumps(stage1_output, ensure_ascii=False, indent=2),
        kb_context=build_kb_context_block(kb_results),
        product_data=json.dumps(context["product_data"], ensure_ascii=False, indent=2),
        simulation_data=json.dumps(sim_data, ensure_ascii=False, indent=2),
        wage_data=json.dumps(wage, ensure_ascii=False, indent=2),
        publication_data=json.dumps(context.get("publication_data", []), ensure_ascii=False, indent=2),
        campaign_data=json.dumps(context.get("campaign_data", []), ensure_ascii=False, indent=2),
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
    )

    return await _call_llm(llm_client, prompt, stage_cfg, tenant_id, stage_num=4, pipeline_run_id=pipeline_run_id)


async def stage5_checklist_summary(
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

    prompt = STAGE5_SYSTEM_PROMPT.format(
        stage1_output=json.dumps(stage1_output, ensure_ascii=False, indent=2),
        stage2_output=json.dumps(stage2_output, ensure_ascii=False, indent=2),
        stage3_output=json.dumps(stage3_output, ensure_ascii=False, indent=2),
        stage4_output=stage4_text,
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
    return _parse_json_response(response_text)


def _parse_json_response(text: str) -> dict:
    """Parse JSON from LLM response, handling markdown code blocks and truncation."""
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        lines = lines[1:]  # Remove first ```json line
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines)

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Try to repair truncated JSON by closing open brackets/braces
        repaired = _try_repair_truncated_json(text)
        if repaired is not None:
            logger.warning("Repaired truncated JSON response successfully")
            return repaired
        logger.warning("Failed to parse LLM JSON response, returning as raw text")
        return {"raw_response": text}


def _try_repair_truncated_json(text: str) -> Optional[dict]:
    """Attempt to repair truncated JSON by closing unclosed brackets/braces."""
    # Remove trailing incomplete string/value (cut at last complete value)
    # Strategy: find the last valid comma, colon or bracket, then close remaining
    stripped = text.rstrip()

    # Remove trailing partial string (e.g. truncated mid-value)
    # Look for last complete JSON structure point
    in_string = False
    escape_next = False
    stack = []
    last_valid_pos = 0

    for i, ch in enumerate(stripped):
        if escape_next:
            escape_next = False
            continue
        if ch == '\\' and in_string:
            escape_next = True
            continue
        if ch == '"':
            in_string = not in_string
            if not in_string:
                last_valid_pos = i
            continue
        if in_string:
            continue
        if ch in '{[':
            stack.append(ch)
            continue
        if ch in '}]':
            if stack:
                stack.pop()
            last_valid_pos = i
            continue
        if ch in ',: \t\n\r':
            if ch in ',:':
                last_valid_pos = i
            continue
        # digits, true, false, null etc.
        last_valid_pos = i

    if not stack:
        return None  # Nothing to repair (or text is valid but parse failed for other reason)

    # If we ended inside a string, truncate at last closed quote
    if in_string:
        # Find the last closing quote position
        last_quote = stripped.rfind('"', 0, len(stripped) - 1)
        if last_quote > 0:
            stripped = stripped[:last_quote + 1]
            # Recompute stack
            in_string = False
            escape_next = False
            stack = []
            for ch in stripped:
                if escape_next:
                    escape_next = False
                    continue
                if ch == '\\' and in_string:
                    escape_next = True
                    continue
                if ch == '"':
                    in_string = not in_string
                    continue
                if in_string:
                    continue
                if ch in '{[':
                    stack.append(ch)
                if ch in '}]':
                    if stack:
                        stack.pop()
        else:
            return None

    # Remove trailing comma if present
    stripped = stripped.rstrip().rstrip(',')

    # Close remaining open brackets/braces
    closers = {'[': ']', '{': '}'}
    for opener in reversed(stack):
        stripped += closers.get(opener, '')

    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        return None


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


def _load_product_data(db: Session, meeting_data: dict) -> list[dict]:
    """Load relevant product and pricing data from salesdb."""
    products = db.query(Product).filter(Product.is_active == True).limit(20).all()
    result = []
    for p in products:
        item = {
            "name": p.name,
            "category": p.category,
            "base_price": float(p.base_price) if p.base_price else None,
            "price_unit": p.price_unit,
            "description": p.description,
        }
        # Load pricing for this product's category
        pricings = db.query(MediaPricing).filter(
            MediaPricing.product_name == p.name
        ).limit(10).all()
        if pricings:
            item["pricing"] = [
                {
                    "media_name": pr.media_name,
                    "price": float(pr.price) if pr.price else None,
                    "listing_period": pr.listing_period,
                    "area": pr.area,
                }
                for pr in pricings
            ]
        result.append(item)
    return result


def _load_simulation_data(db: Session, meeting_data: dict) -> list[dict]:
    """Load simulation parameters for the meeting's area/industry."""
    query = db.query(SimulationParam)
    if meeting_data.get("area"):
        query = query.filter(SimulationParam.area == meeting_data["area"])
    if meeting_data.get("industry"):
        query = query.filter(SimulationParam.industry == meeting_data["industry"])
    params = query.limit(10).all()
    return [
        {
            "area": p.area,
            "industry": p.industry,
            "pv_coefficient": float(p.pv_coefficient) if p.pv_coefficient else None,
            "apply_rate": float(p.apply_rate) if p.apply_rate else None,
            "conversion_rate": float(p.conversion_rate) if p.conversion_rate else None,
        }
        for p in params
    ]


def _load_wage_data(db: Session, meeting_data: dict) -> list[dict]:
    """Load wage data for the meeting's area/industry."""
    query = db.query(WageData)
    if meeting_data.get("area"):
        query = query.filter(WageData.area == meeting_data["area"])
    if meeting_data.get("industry"):
        query = query.filter(WageData.industry == meeting_data["industry"])
    wages = query.limit(10).all()
    return [
        {
            "area": w.area,
            "industry": w.industry,
            "employment_type": w.employment_type,
            "min_wage": float(w.min_wage) if w.min_wage else None,
            "avg_wage": float(w.avg_wage) if w.avg_wage else None,
        }
        for w in wages
    ]


def _load_publication_records(db: Session, product_names: list, meeting_data: dict) -> list[dict]:
    """Load publication records for the given products and area."""
    area = meeting_data.get("area")
    return get_publication_records(db, product_names, area=area, limit=10)


def _load_campaign_data(db: Session) -> list[dict]:
    """Load currently active campaigns."""
    from datetime import date
    today = date.today()
    campaigns = db.query(Campaign).filter(
        Campaign.is_active == True,
        Campaign.start_date <= today,
        Campaign.end_date >= today,
    ).limit(10).all()
    return [
        {
            "name": c.name,
            "description": c.description,
            "start_date": str(c.start_date),
            "end_date": str(c.end_date),
            "discount_rate": float(c.discount_rate) if c.discount_rate else None,
            "discount_amount": float(c.discount_amount) if c.discount_amount else None,
            "conditions": c.conditions or {},
        }
        for c in campaigns
    ]
