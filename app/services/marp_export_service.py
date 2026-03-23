"""Marp export service for proposal documents.

Delegates conversion to api-export service via HTTP.
Builds Marp Markdown locally (domain logic), sends to api-export for conversion.
"""
import logging
from uuid import UUID

import httpx
from fastapi import HTTPException

from app.utils.markdown_table_fixer import fix_markdown_tables
from fastapi.responses import Response

from app.core.config import settings
from app.models.proposal_document import ProposalDocument

logger = logging.getLogger(__name__)

EXPORT_TIMEOUT = 120.0


def _build_marp_markdown(doc: ProposalDocument) -> str:
    """Concatenate all pages into a single Marp-compatible Markdown."""
    theme = doc.marp_theme or "default"
    title = (doc.title or "提案書").replace('"', '\\"')
    frontmatter = f"""---
marp: true
html: true
theme: {theme}
paginate: true
size: 16:9
footer: "{title}"
style: |
  section {{
    font-family: 'Hiragino Kaku Gothic ProN', 'Noto Sans JP', 'YuGothic', sans-serif;
    font-size: 14px;
    line-height: 1.4;
    padding: 30px 50px;
    overflow: hidden;
  }}
  section.lead {{
    background: linear-gradient(135deg, #0f172a 0%, #1e3a5f 100%);
    color: white;
    text-align: center;
    justify-content: center;
  }}
  section.lead h1 {{
    color: #60a5fa;
    font-size: 36px;
    margin-bottom: 0.3em;
    border: none;
  }}
  section.lead h2 {{
    color: #94a3b8;
    font-size: 20px;
    border: none;
  }}
  section.lead p {{
    color: #cbd5e1;
  }}
  h1 {{
    color: #1e3a5f;
    font-size: 28px;
    border-bottom: 3px solid #3b82f6;
    padding-bottom: 8px;
    margin-bottom: 12px;
  }}
  h2 {{
    color: #1e40af;
    font-size: 20px;
    border-bottom: 2px solid #93c5fd;
    padding-bottom: 4px;
    margin-top: 8px;
    margin-bottom: 6px;
  }}
  h3 {{
    font-size: 16px;
    color: #334155;
  }}
  strong {{
    color: #dc2626;
  }}
  table {{
    font-size: 13px;
    width: 100%;
    border-collapse: collapse;
    margin: 6px 0;
  }}
  th {{
    background: #1e3a5f;
    color: white;
    padding: 5px 10px;
    text-align: left;
    font-weight: 600;
  }}
  td {{
    padding: 4px 10px;
    border-bottom: 1px solid #e2e8f0;
  }}
  section:not(.lead) tr:nth-child(even) td {{
    background: #f8fafc;
  }}
  ul, ol {{
    font-size: 14px;
    line-height: 1.5;
    margin: 6px 0;
  }}
  blockquote {{
    border-left: 4px solid #3b82f6;
    background: #eff6ff;
    padding: 8px 12px;
    margin: 8px 0;
    font-size: 13px;
    border-radius: 0 6px 6px 0;
    color: #475569;
  }}
  code {{
    background: #f1f5f9;
    padding: 1px 4px;
    border-radius: 3px;
    font-size: 12px;
  }}
  footer {{
    font-size: 10px;
    color: #94a3b8;
  }}
---

"""
    pages_sorted = sorted(doc.pages, key=lambda p: p.page_number)
    page_markdowns = []
    for i, p in enumerate(pages_sorted):
        md = _strip_marp_separators(fix_markdown_tables(p.markdown_content or ""))
        if i == 0:
            # Apply lead class to first page (cover slide)
            md = "<!-- _class: lead -->\n<!-- _footer: \"\" -->\n\n" + md
        page_markdowns.append(md)
    return frontmatter + "\n\n---\n\n".join(page_markdowns)


def _strip_marp_separators(md: str) -> str:
    """Remove leading/trailing ``---`` slide separators from a page.

    LLMs sometimes include ``---`` at the start or end of a page which,
    combined with the join separator, creates empty slides in Marp output.
    """
    lines = md.split("\n")
    # Strip trailing ---
    while lines and lines[-1].strip() == "---":
        lines.pop()
    # Strip leading ---
    while lines and lines[0].strip() == "---":
        lines.pop(0)
    return "\n".join(lines)


async def export_to_marp(doc: ProposalDocument, fmt: str) -> dict:
    """Export proposal document via api-export service."""
    markdown = _build_marp_markdown(doc)
    doc_id_str = str(doc.id)

    url = f"{settings.export_service_url}/convert"
    payload = {
        "markdown": markdown,
        "format": fmt,
        "filename": "proposal",
        "caller": f"proposal-documents/{doc_id_str}",
    }
    headers = {"X-Internal-Secret": settings.internal_api_secret}

    try:
        async with httpx.AsyncClient(timeout=EXPORT_TIMEOUT) as client:
            resp = await client.post(url, json=payload, headers=headers)
    except httpx.ConnectError:
        logger.error("Export service unreachable at %s", settings.export_service_url)
        raise HTTPException(status_code=502, detail="Export service unavailable")
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="Export service timed out")

    if resp.status_code != 200:
        detail = resp.text[:500] if resp.text else "Unknown error"
        logger.error("Export service returned %d: %s", resp.status_code, detail)
        raise HTTPException(status_code=502, detail=f"Export service error: {detail}")

    result = resp.json()
    return {
        "download_url": f"/api/sales/proposal-documents/{doc_id_str}/export/download",
        "object_key": result["object_key"],
        "format": result["format"],
    }


async def download_export_file(
    document_id: UUID,
    preferred_format: str | None = None,
) -> Response:
    """Download exported file from MinIO.

    When *preferred_format* is given, that format is tried first.
    Falls back to remaining formats so old download links keep working.
    """
    from app.services.storage_service import get_storage_service
    storage = get_storage_service()
    if storage is None:
        raise HTTPException(status_code=500, detail="MinIO storage is not enabled")

    doc_id_str = str(document_id)
    caller = f"proposal-documents/{doc_id_str}"
    ALL_FORMATS = {
        "pdf": "application/pdf",
        "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        "html": "text/html; charset=utf-8",
    }

    # Preferred format first, then the rest
    if preferred_format and preferred_format in ALL_FORMATS:
        order = [preferred_format] + [f for f in ALL_FORMATS if f != preferred_format]
    else:
        order = list(ALL_FORMATS.keys())

    for fmt in order:
        media_type = ALL_FORMATS[fmt]
        object_key = f"exports/{caller}/proposal.{fmt}"
        try:
            data = await storage.download_bytes(object_key)
            return Response(
                content=data,
                media_type=media_type,
                headers={
                    "Content-Disposition": f'attachment; filename="proposal.{fmt}"',
                },
            )
        except Exception:
            continue

    raise HTTPException(status_code=404, detail="Export file not found")
