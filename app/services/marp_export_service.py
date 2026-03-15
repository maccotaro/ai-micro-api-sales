"""Marp export service for proposal documents.

Converts proposal document pages to PPTX/PDF via Marp CLI.
Falls back to Markdown download if Marp CLI is not installed.
"""
import io
import logging
import os
import shutil
import subprocess
import tempfile
from typing import Optional
from uuid import UUID

from fastapi import HTTPException
from fastapi.responses import StreamingResponse, Response

from app.core.config import settings
from app.models.proposal_document import ProposalDocument

logger = logging.getLogger(__name__)

# Check if Marp CLI is available
_marp_available: Optional[bool] = None


def _check_marp_available() -> bool:
    global _marp_available
    if _marp_available is None:
        _marp_available = shutil.which("marp") is not None or shutil.which("npx") is not None
    return _marp_available


def _build_marp_markdown(doc: ProposalDocument) -> str:
    """Concatenate all pages into a single Marp-compatible Markdown."""
    theme = doc.marp_theme or "default"
    title = (doc.title or "提案書").replace('"', '\\"')
    frontmatter = f"""---
marp: true
theme: {theme}
paginate: true
size: 16:9
footer: "{title}"
style: |
  section {{
    font-size: 18px;
    padding: 40px 60px;
    overflow: hidden;
  }}
  h1 {{
    font-size: 36px;
    color: #1a365d;
    border-bottom: 3px solid #3182ce;
    padding-bottom: 12px;
    margin-bottom: 20px;
  }}
  h2 {{
    font-size: 28px;
    color: #2d3748;
    margin-top: 16px;
    margin-bottom: 12px;
  }}
  h3 {{
    font-size: 18px;
    color: #4a5568;
  }}
  table {{
    font-size: 18px;
    width: 100%;
    border-collapse: collapse;
    margin: 12px 0;
  }}
  th {{
    background: #edf2f7;
    padding: 8px 12px;
    text-align: left;
    font-weight: 600;
  }}
  td {{
    padding: 6px 12px;
    border-bottom: 1px solid #e2e8f0;
  }}
  ul, ol {{
    font-size: 20px;
    line-height: 1.6;
    margin: 8px 0;
  }}
  blockquote {{
    border-left: 4px solid #3182ce;
    background: #ebf8ff;
    padding: 12px 16px;
    margin: 12px 0;
    font-size: 18px;
    border-radius: 0 8px 8px 0;
  }}
  strong {{
    color: #2b6cb0;
  }}
  footer {{
    font-size: 12px;
    color: #a0aec0;
  }}
---

"""
    pages_sorted = sorted(doc.pages, key=lambda p: p.page_number)
    page_markdowns = [p.markdown_content for p in pages_sorted]
    return frontmatter + "\n\n---\n\n".join(page_markdowns)


async def export_to_marp(doc: ProposalDocument, fmt: str) -> dict:
    """Export proposal document to PPTX/PDF via Marp CLI, or Markdown fallback.

    Marp CLI requires Chromium for PPTX/PDF. If unavailable, --html is tried.
    Final fallback: upload Marp Markdown directly.
    """
    markdown = _build_marp_markdown(doc)
    doc_id_str = str(doc.id)

    with tempfile.TemporaryDirectory() as tmpdir:
        input_path = os.path.join(tmpdir, "presentation.md")
        with open(input_path, "w", encoding="utf-8") as f:
            f.write(markdown)

        # Try Marp CLI with --html first (no Chromium needed)
        html_path = os.path.join(tmpdir, "presentation.html")
        try:
            result = subprocess.run(
                ["npx", "@marp-team/marp-cli", input_path, "-o", html_path, "--html"],
                capture_output=True, text=True, timeout=60,
            )
            if result.returncode == 0 and os.path.exists(html_path):
                with open(html_path, "rb") as f:
                    html_bytes = f.read()
                object_key = await _upload_to_minio(doc_id_str, html_bytes, "presentation.html",
                                                     "text/html; charset=utf-8")
                return {"download_url": f"/api/sales/proposal-documents/{doc_id_str}/export/download",
                        "object_key": object_key, "format": "html",
                        "note": "HTMLスライドとしてエクスポートしました。ブラウザで開けます。"}
        except (FileNotFoundError, subprocess.TimeoutExpired) as e:
            logger.warning("Marp CLI HTML export failed: %s", e)

        # Fallback: upload Markdown directly
        md_bytes = markdown.encode("utf-8")
        object_key = await _upload_to_minio(doc_id_str, md_bytes, "presentation.md",
                                             "text/markdown; charset=utf-8")
        return {"download_url": f"/api/sales/proposal-documents/{doc_id_str}/export/download",
                "object_key": object_key, "format": "md",
                "note": "Markdownファイルとしてエクスポートしました。"}


async def _upload_to_minio(doc_id: str, data: bytes, filename: str, content_type: str) -> str:
    """Upload bytes to MinIO using StorageService."""
    from app.services.storage_service import get_storage_service
    storage = get_storage_service()
    if storage is None:
        raise HTTPException(status_code=500, detail="MinIO storage is not enabled")
    object_key = await storage.upload_bytes(
        data=data,
        tenant_id="proposal-documents",
        run_id=doc_id,
        filename=filename,
        content_type=content_type,
    )
    return object_key


async def download_export_file(document_id: UUID) -> Response:
    """Download exported file from MinIO."""
    from app.services.storage_service import get_storage_service
    storage = get_storage_service()
    if storage is None:
        raise HTTPException(status_code=500, detail="MinIO storage is not enabled")

    doc_id_str = str(document_id)
    FORMATS = {
        "html": "text/html; charset=utf-8",
        "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        "pdf": "application/pdf",
        "md": "text/markdown; charset=utf-8",
    }

    for fmt, media_type in FORMATS.items():
        # Use same key structure as _upload_to_minio → storage.upload_bytes
        # which builds: {prefix}/{tenant_id}/{run_id}/{filename}
        object_key = storage._object_key("proposal-documents", doc_id_str, f"presentation.{fmt}")
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
