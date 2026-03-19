"""Diff detection and pattern extraction for proposal document edits."""
import logging
from typing import Optional

from app.models.proposal_document import ProposalDocument

logger = logging.getLogger(__name__)


async def get_persona_id_for_document(
    doc: ProposalDocument, db,
) -> Optional[str]:
    """Get persona_id from the pipeline run's stage_results."""
    if not doc.pipeline_run_id:
        return None
    from sqlalchemy import text as sa_text
    row = db.execute(sa_text("""
        SELECT stage_results FROM proposal_pipeline_runs WHERE id = :run_id
    """), {"run_id": str(doc.pipeline_run_id)}).fetchone()
    if not row or not row[0]:
        return None
    stage_results = row[0] if isinstance(row[0], dict) else {}
    # Check _meta first (stored at pipeline start)
    meta = stage_results.get("_meta", {})
    if meta.get("persona_id"):
        return str(meta["persona_id"])
    return None


def build_diff_data(
    doc: ProposalDocument,
    existing: dict,
    updates: list,
    changed_pages: list[int],
) -> dict:
    """Build diff_data JSONB for persona_pattern_diffs."""
    diffs = []
    update_map = {u.page_number: u for u in updates}
    for pn in changed_pages:
        orig_page = existing.get(pn)
        upd = update_map.get(pn)
        if orig_page and upd:
            diffs.append({
                "page_number": pn,
                "original": (orig_page.markdown_content or "").strip(),
                "modified": upd.markdown_content.strip(),
            })
    return {
        "document_id": str(doc.id),
        "title": doc.title,
        "changed_page_count": len(changed_pages),
        "diffs": diffs,
    }


async def trigger_pattern_extraction(
    persona_id: str, user_id: str, document_id: str,
    pipeline_run_id: Optional[str], tenant_id: str,
    diff_data: dict,
) -> None:
    """Call api-admin to store diff and extract patterns."""
    import httpx
    from app.core.config import settings

    url = (
        f"{settings.admin_internal_url}/admin/personas/"
        f"{persona_id}/patterns/extract-from-diff"
    )
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            await client.post(url, json={
                "user_id": user_id,
                "document_id": document_id,
                "pipeline_run_id": pipeline_run_id,
                "tenant_id": tenant_id,
                "diff_data": diff_data,
            }, headers={
                "X-Internal-Secret": settings.internal_api_secret,
            })
    except Exception:
        logger.warning(
            "Failed to trigger pattern extraction for persona %s",
            persona_id, exc_info=True,
        )
