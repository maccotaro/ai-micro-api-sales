"""Stage 6-10 implementations for the proposal document pipeline.

Stage 6:  Proposal context collection (non-LLM)
Stage 7:  Industry & target analysis (LLM)
Stage 8:  Appeal strategy planning (LLM)
Stage 9:  Story structure design (LLM)
Stage 10: Page-by-page Markdown generation (LLM)
"""
import json
import logging
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.proposal_document import (
    ProposalDocument, ProposalDocumentPage,
)
from app.services.llm_client import LLMClient
from app.services.pipeline_config import PipelineConfigData
from app.core.model_settings_client import get_chat_num_ctx
from app.services.pipeline_stages import _search_kbs, _call_llm, _build_issues_summary
from app.services.pipeline_helpers import parse_json_response
from app.services.proposal_pipeline_prompts import (
    build_stage7_prompt, build_stage8_prompt,
    build_stage9_prompt, build_stage10_page_prompt,
)
from app.utils.markdown_table_fixer import fix_markdown_tables
from app.services.proposal_data_loaders import (
    load_success_cases, load_publication_records_for_proposal,
)

logger = logging.getLogger(__name__)


# ============================================================
# Stage 6: Proposal Context Collection (non-LLM)
# ============================================================

async def stage6_proposal_context(
    context: dict,
    stage1_output: dict,
    config: PipelineConfigData,
    db: Session,
    tenant_id: UUID,
) -> dict:
    """Collect proposal-generation context without LLM.

    Searches:
    - proposal_reference KB (approved proposals)
    - target_psychology_end_user KB
    - target_psychology_decision_maker KB
    - success_case_embeddings
    - publication_records (high-performing)
    """
    meeting = context.get("meeting", {})

    # KB searches (parallel)
    stage6_categories = {
        name: cat
        for name, cat in config.kb_mapping.items()
        if name in (
            "proposal_reference",
            "target_psychology_end_user",
            "target_psychology_decision_maker",
        )
    }
    issues_sum = _build_issues_summary(stage1_output, meeting)
    kb_results = await _search_kbs(stage6_categories, meeting, tenant_id, issues_summary=issues_sum)

    # Success case embeddings
    success_cases = await load_success_cases(
        industry=meeting.get("industry", ""),
        area=meeting.get("area", ""),
        tenant_id=tenant_id,
    )

    # Publication records (high-performing)
    pub_records = load_publication_records_for_proposal(
        db=db,
        industry=meeting.get("industry", ""),
        area=meeting.get("area", ""),
    )

    return {
        "proposal_kb_chunks": kb_results.get("proposal_reference", []),
        "end_user_psychology_chunks": kb_results.get("target_psychology_end_user", []),
        "decision_maker_psychology_chunks": kb_results.get("target_psychology_decision_maker", []),
        "success_cases": success_cases,
        "publication_records": pub_records,
    }


# ============================================================
# Stage 7: Industry & Target Analysis (LLM)
# ============================================================

async def stage7_industry_target_analysis(
    context: dict,
    stage1_output: dict,
    stage6_output: dict,
    config: PipelineConfigData,
    llm_client: LLMClient,
    tenant_id: UUID,
    pipeline_run_id: Optional[str] = None,
    persona_id: Optional[str] = None,
) -> dict:
    """Analyze industry structure and target psychology."""
    stage_cfg = config.get_stage(7)
    meeting = context.get("meeting", {})

    has_psychology_kb = bool(
        stage6_output.get("end_user_psychology_chunks")
        or stage6_output.get("decision_maker_psychology_chunks")
    )

    prompt = build_stage7_prompt(
        meeting=meeting,
        stage1_issues=stage1_output.get("issues", []),
        proposal_kb_chunks=stage6_output.get("proposal_kb_chunks", []),
        end_user_chunks=stage6_output.get("end_user_psychology_chunks", []),
        decision_maker_chunks=stage6_output.get("decision_maker_psychology_chunks", []),
        publication_records=stage6_output.get("publication_records", []),
    )

    result = await _call_llm(
        llm_client, prompt, stage_cfg, tenant_id, 7, pipeline_run_id,
        persona_id=persona_id,
    )

    result["source"] = "kb_data" if has_psychology_kb else "general_knowledge"
    result["_prompt"] = prompt
    return result


# ============================================================
# Stage 8: Appeal Strategy Planning (LLM)
# ============================================================

async def stage8_appeal_strategy(
    context: dict,
    stage1_output: dict,
    stage6_output: dict,
    stage7_output: dict,
    config: PipelineConfigData,
    llm_client: LLMClient,
    tenant_id: UUID,
    pipeline_run_id: Optional[str] = None,
    persona_id: Optional[str] = None,
) -> dict:
    """Design strategy-based proposal axes with catchcopy-psychology linkage."""
    stage_cfg = config.get_stage(8)

    prompt = build_stage8_prompt(
        stage1_issues=stage1_output.get("issues", []),
        stage7_output=stage7_output,
        decision_maker_chunks=stage6_output.get("decision_maker_psychology_chunks", []),
        success_cases=stage6_output.get("success_cases", []),
        publication_records=stage6_output.get("publication_records", []),
    )

    result = await _call_llm(
        llm_client, prompt, stage_cfg, tenant_id, 8, pipeline_run_id,
        persona_id=persona_id,
    )
    result["_prompt"] = prompt
    return result


# ============================================================
# Stage 9: Story Structure (LLM)
# ============================================================

async def stage9_story_structure(
    stage1_output: dict,
    stage7_output: dict,
    stage8_output: dict,
    config: PipelineConfigData,
    llm_client: LLMClient,
    tenant_id: UUID,
    pipeline_run_id: Optional[str] = None,
    persona_id: Optional[str] = None,
) -> dict:
    """Design the proposal document's story structure."""
    stage_cfg = config.get_stage(9)

    prompt = build_stage9_prompt(
        stage1_issues=stage1_output.get("issues", []),
        stage7_output=stage7_output,
        stage8_output=stage8_output,
    )

    result = await _call_llm(
        llm_client, prompt, stage_cfg, tenant_id, 9, pipeline_run_id,
        persona_id=persona_id,
    )

    # Validate page count range
    pages = result.get("pages", [])
    if len(pages) < 5:
        logger.warning("Stage 9 produced %d pages (< 5), using as-is", len(pages))
    elif len(pages) > 10:
        logger.warning("Stage 9 produced %d pages (> 10), truncating to 10", len(pages))
        result["pages"] = pages[:10]

    result["_prompt"] = prompt
    return result


# ============================================================
# Stage 10: Page-by-page Markdown Generation (LLM)
# ============================================================

async def stage10_page_generation(
    context: dict,
    stage1_output: dict,
    stage2_output: dict,
    stage6_output: dict,
    stage7_output: dict,
    stage8_output: dict,
    stage9_output: dict,
    config: PipelineConfigData,
    llm_client: LLMClient,
    db: Session,
    tenant_id: UUID,
    user_id: UUID,
    pipeline_run_id: Optional[str] = None,
    minute_id: Optional[UUID] = None,
    persona_id: Optional[str] = None,
) -> dict:
    """Generate Marp-compatible Markdown for each page."""
    stage_cfg = config.get_stage(10)
    story_theme = stage9_output.get("story_theme", "")
    pages_spec = stage9_output.get("pages", [])

    # Resolve data sources for each page
    all_sources = _build_data_source_map(
        context, stage1_output, stage2_output,
        stage6_output, stage7_output, stage8_output,
    )

    # Generate each page individually
    generated_pages = []
    for page_spec in pages_spec:
        page_data = _extract_page_data(page_spec, all_sources)
        prompt = build_stage10_page_prompt(
            story_theme=story_theme,
            page_title=page_spec.get("title", ""),
            page_purpose=page_spec.get("purpose", ""),
            key_points=page_spec.get("key_points", []),
            page_data=page_data,
        )

        # Stage 10 uses direct LLM call (not _call_llm) because output is
        # Markdown, not JSON. _call_llm adds "JSON形式で出力" user message
        # which conflicts with Markdown output instruction.
        messages = [
            {"role": "system", "content": prompt},
            {"role": "user", "content": "上記の情報に基づいて、プレゼンテーション用のMarkdownスライドを1ページ分作成してください。"},
        ]
        async def _call_page_llm(msgs):
            return await llm_client.chat(
                messages=msgs, service_name="api-sales",
                model=stage_cfg.model, temperature=stage_cfg.temperature or 0.3,
                max_tokens=stage_cfg.max_tokens, tenant_id=str(tenant_id),
                pipeline_stage=10, pipeline_run_id=pipeline_run_id,
                provider_options={"num_ctx": get_chat_num_ctx()},
                persona_id=persona_id,
            )

        result = await _call_page_llm(messages)
        markdown = fix_markdown_tables(result.get("response", ""))
        line_count = len([l for l in markdown.strip().split("\n") if l.strip()])

        if line_count > 28:
            # Too long: ask LLM to split into 2 pages
            split_msgs = [
                {"role": "system", "content": f"以下のスライド内容を2ページに分割してください。各ページは16行以内に収めてください。ページ区切りは「---PAGE_BREAK---」で示してください。\n\n{markdown}"},
                {"role": "user", "content": "2ページに分割してください。"},
            ]
            split_result = await _call_page_llm(split_msgs)
            split_text = split_result.get("response", markdown)
            if "---PAGE_BREAK---" in split_text:
                parts = split_text.split("---PAGE_BREAK---", 1)
                markdown = fix_markdown_tables(parts[0].strip())
                # Insert extra page after current
                extra_page = {
                    "page_number": page_spec["page_number"] + 0.5,
                    "title": page_spec.get("title", "") + "（続き）",
                    "purpose": page_spec.get("purpose", ""),
                    "markdown_content": fix_markdown_tables(parts[1].strip()),
                    "data_sources": page_spec.get("data_sources", []),
                    "generation_context": {"story_theme": story_theme, "page_spec": page_spec, "page_data": page_data, "split": True},
                }
                generated_pages.append(extra_page)
            else:
                markdown = split_text
        elif line_count > 20:
            # Slightly over: ask LLM to condense
            condense_msgs = [
                {"role": "system", "content": f"以下のスライド内容を16行以内に要約してください。重要な数値やキーポイントは残してください。\n\n{markdown}"},
                {"role": "user", "content": "16行以内に要約してください。"},
            ]
            condense_result = await _call_page_llm(condense_msgs)
            markdown = fix_markdown_tables(condense_result.get("response", markdown))

        generated_pages.append({
            "page_number": page_spec["page_number"],
            "title": page_spec.get("title", ""),
            "purpose": page_spec.get("purpose", ""),
            "markdown_content": markdown,
            "data_sources": page_spec.get("data_sources", []),
            "generation_context": {
                "story_theme": story_theme,
                "page_spec": page_spec,
                "page_data": page_data,
            },
        })

    # Renumber pages sequentially (splits may have created .5 numbers)
    generated_pages.sort(key=lambda p: p["page_number"])
    for i, page in enumerate(generated_pages, 1):
        page["page_number"] = i

    # Save to database
    doc_id = _save_proposal_document(
        db=db,
        tenant_id=tenant_id,
        user_id=user_id,
        pipeline_run_id=pipeline_run_id,
        minute_id=minute_id,
        story_structure=stage9_output,
        pages=generated_pages,
        title=story_theme,
    )

    return {
        "document_id": str(doc_id),
        "pages": generated_pages,
    }


# ============================================================
# Helpers
# ============================================================

def _build_data_source_map(
    context: dict,
    stage1_output: dict,
    stage2_output: dict,
    stage6_output: dict,
    stage7_output: dict,
    stage8_output: dict,
) -> dict:
    """Build a mapping from data_source names to actual data."""
    return {
        # Stage 0: 商品・料金・シミュレーションデータ
        "stage0_product_data": json.dumps(
            context.get("product_data", [])[:5], ensure_ascii=False,
        )[:1200],
        "stage0_wage_data": json.dumps(
            context.get("wage_data", [])[:3], ensure_ascii=False,
        )[:600],
        "stage0_simulation_data": json.dumps(
            context.get("simulation_data", [])[:3], ensure_ascii=False,
        )[:600],
        # Stage 1: 課題・BANT-C
        "stage1_issues": json.dumps(
            stage1_output.get("issues", [])[:3], ensure_ascii=False,
        )[:1500],
        # Stage 2: 松竹梅プラン・料金提案
        "stage2_plans": json.dumps(
            stage2_output, ensure_ascii=False,
        )[:2000] if stage2_output else "（プラン情報なし）",
        # Stage 6: 提案コンテキスト
        "stage6_publication_data": json.dumps(
            stage6_output.get("publication_records", [])[:3], ensure_ascii=False,
        )[:1000],
        "stage6_success_cases": json.dumps(
            stage6_output.get("success_cases", [])[:2], ensure_ascii=False,
        )[:1000],
        # Stage 7: 業界・ターゲット分析
        "stage7_industry_analysis": json.dumps(
            stage7_output.get("industry_analysis", {}), ensure_ascii=False,
        )[:1000],
        "stage7_target_insights": json.dumps(
            stage7_output.get("target_insights", {}), ensure_ascii=False,
        )[:800],
        "stage7_decision_maker_insights": json.dumps(
            stage7_output.get("decision_maker_insights", {}), ensure_ascii=False,
        )[:600],
        # Stage 8: 訴求戦略
        "stage8_strategy_axes": json.dumps(
            stage8_output.get("strategy_axes", []), ensure_ascii=False,
        )[:1200],
        "stage8_success_case_references": json.dumps(
            stage8_output.get("success_case_references", []), ensure_ascii=False,
        )[:800],
    }


def _extract_page_data(page_spec: dict, all_sources: dict) -> str:
    """Extract only the data sources needed for a specific page."""
    sources = page_spec.get("data_sources", [])
    parts = []
    for source in sources:
        data = all_sources.get(source, "")
        if data:
            parts.append(f"【{source}】\n{data}")
    return "\n\n".join(parts) if parts else "（データソースなし）"


def _save_proposal_document(
    db: Session,
    tenant_id: UUID,
    user_id: UUID,
    pipeline_run_id: Optional[str],
    minute_id: Optional[UUID],
    story_structure: dict,
    pages: list[dict],
    title: str,
) -> UUID:
    """Save proposal document and pages to database."""
    doc = ProposalDocument(
        tenant_id=tenant_id,
        user_id=user_id,
        pipeline_run_id=pipeline_run_id,
        minute_id=minute_id,
        title=title[:255] if title else "提案書",
        story_structure=story_structure,
        status="draft",
    )
    db.add(doc)
    db.flush()

    for page_data in pages:
        page = ProposalDocumentPage(
            document_id=doc.id,
            page_number=page_data["page_number"],
            title=page_data.get("title"),
            markdown_content=page_data["markdown_content"],
            purpose=page_data.get("purpose"),
            data_sources=page_data.get("data_sources"),
            generation_context=page_data.get("generation_context"),
        )
        db.add(page)

    db.commit()
    return doc.id
