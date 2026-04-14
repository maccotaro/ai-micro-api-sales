"""
KB-based transcription correction service.

Uses api-rag to find domain terminology from knowledge bases,
then api-llm to correct STT transcription with those terms.
"""
import logging
from typing import Optional
from uuid import UUID

import httpx
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.meeting import MeetingMinute, MeetingMinuteVersion

logger = logging.getLogger(__name__)

# Correction prompt template
CORRECTION_PROMPT = """以下は会議の文字起こしテキストです。音声認識による誤変換が含まれている可能性があります。

ナレッジベースから取得した用語リストを参考に、テキスト内の誤変換を修正してください。
- 固有名詞（社名、人名、製品名）の修正を優先
- 一般的な単語は変更しない
- 文の構造は変更しない
- 修正箇所が特にない場合はそのまま返す

## 用語リスト（参考）
{terms}

## 文字起こしテキスト
{text}

## 修正後テキスト"""


async def search_kb_terms(
    tenant_id: str,
    text: str,
    meeting_type: str = "sales",
) -> list[str]:
    """Search KB for domain-specific terms relevant to the transcription."""
    try:
        search_url = f"{settings.rag_service_url}/internal/v1/search/hybrid"
        # Use first 500 chars as query to find relevant KB entries
        query = text[:500]

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                search_url,
                json={
                    "query": query,
                    "tenant_id": tenant_id,
                    "top_k": 10,
                    "enable_graph": False,
                    "strategy": "quick",
                },
                headers={
                    "X-Internal-Secret": settings.internal_api_secret,
                },
            )

        if response.status_code != 200:
            logger.warning(f"KB search failed: {response.status_code} {response.text[:200]}")
            return []

        data = response.json()
        # Extract unique terms/phrases from search results
        terms = []
        for result in data.get("results", []):
            content = result.get("content", "")
            if content:
                # Take first line or up to 100 chars as a term reference
                term = content.split("\n")[0][:100]
                if term and term not in terms:
                    terms.append(term)
        return terms

    except Exception as e:
        logger.warning(f"KB search error: {e}")
        return []


async def correct_with_llm(text: str, terms: list[str]) -> Optional[str]:
    """Use LLM to correct transcription based on KB terms."""
    if not terms:
        return None

    try:
        terms_text = "\n".join(f"- {t}" for t in terms)
        prompt = CORRECTION_PROMPT.format(terms=terms_text, text=text)

        llm_url = f"{settings.llm_service_url}/llm/v1/generate"
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                llm_url,
                json={
                    "prompt": prompt,
                    "task_type": "stt_correction",
                    "service_name": "api-sales",
                    "temperature": 0.1,
                    "max_tokens": len(text) * 2,  # Allow some expansion
                },
                headers={
                    "X-Internal-Secret": settings.internal_api_secret,
                },
            )

        if response.status_code != 200:
            logger.warning(f"LLM correction failed: {response.status_code}")
            return None

        data = response.json()
        return data.get("text", "").strip() or None

    except Exception as e:
        logger.warning(f"LLM correction error: {e}")
        return None


async def run_kb_correction(minutes_id: UUID, db: Session) -> bool:
    """Run KB correction pipeline for a meeting_minutes record.

    Returns True if correction was applied, False if skipped/failed.
    """
    minute = db.query(MeetingMinute).filter(MeetingMinute.id == minutes_id).first()
    if not minute:
        logger.error(f"MeetingMinute {minutes_id} not found")
        return False

    if minute.minutes_status != "raw":
        logger.info(f"MeetingMinute {minutes_id} not in raw status, skipping")
        return False

    raw_text = minute.raw_text
    tenant_id = str(minute.tenant_id) if minute.tenant_id else None

    if not tenant_id or not raw_text:
        # No tenant or text: copy raw_text as-is
        _save_corrected(minute, raw_text, db, kb_skipped=True, reason="no_tenant_or_text")
        return True

    # Step 1: Search KB for domain terms
    terms = await search_kb_terms(tenant_id, raw_text, minute.status or "sales")

    if not terms:
        # No KB terms found: copy raw_text as-is (graceful degradation)
        _save_corrected(minute, raw_text, db, kb_skipped=True, reason="no_kb_terms")
        return True

    # Step 2: LLM correction
    corrected = await correct_with_llm(raw_text, terms)

    if not corrected:
        # LLM failed: copy raw_text as-is
        _save_corrected(minute, raw_text, db, kb_skipped=True, reason="llm_failed")
        return True

    # Step 3: Save corrected text
    _save_corrected(minute, corrected, db, kb_skipped=False)
    return True


def _save_corrected(
    minute: MeetingMinute,
    text: str,
    db: Session,
    kb_skipped: bool = False,
    reason: str = "",
) -> None:
    """Save corrected text and create version record."""
    # Save version of raw text before updating
    version = MeetingMinuteVersion(
        minutes_id=minute.id,
        version=minute.version,
        status=minute.minutes_status,
        text=minute.raw_text,
        changed_by=minute.created_by,
    )
    db.add(version)

    # Update minute
    minute.corrected_text = text
    minute.minutes_status = "corrected"
    minute.version = (minute.version or 1) + 1

    if kb_skipped:
        # Record skip reason in parsed_json metadata
        metadata = minute.parsed_json or {}
        metadata["kb_correction"] = {"skipped": True, "reason": reason}
        minute.parsed_json = metadata

    db.commit()
    logger.info(
        f"KB correction {'skipped' if kb_skipped else 'applied'} for "
        f"minutes_id={minute.id}, reason={reason}"
    )
