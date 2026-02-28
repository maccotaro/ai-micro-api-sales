"""
Meeting Minutes Analysis Service

Uses LLM to analyze meeting minutes and extract key information.
Integrates with Neo4j graph database for relationship-based recommendations.
"""
import logging
import json
from datetime import datetime
from typing import Optional, Dict, Any, List
from uuid import UUID

import httpx
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.model_settings_client import get_chat_num_ctx
from app.services.llm_client import LLMClient
from app.models.meeting import MeetingMinute
from app.schemas.meeting import MeetingMinuteAnalysis, ExtractedIssue, ExtractedNeed
from app.services.graph.sales_graph_service import sales_graph_service

logger = logging.getLogger(__name__)


EXTRACTION_PROMPT = """以下の議事録テキストから、顧客企業の「業種」と「地域」を推定してください。
JSONのみ出力し、他の説明は不要です。

会社名: {company_name}
テキスト（冒頭部分）:
{raw_text}

出力形式:
{{"industry": "業種（例: IT, 飲食, フィットネス, 製造, 不動産, 医療等）またはnull", "area": "地域（例: 東京, 関東, 大阪, 関西等）またはnull"}}
"""


ANALYSIS_PROMPT = """あなたは営業支援AIアシスタントです。以下の議事録を分析し、JSON形式で結果を出力してください。

## 議事録
会社名: {company_name}
業種: {industry}
地域: {area}
日付: {meeting_date}

{raw_text}

## 出力形式（JSON）
以下のJSON形式で出力してください。JSONのみ出力し、他の説明は不要です。

{{
    "issues": [
        {{"issue": "課題内容", "category": "カテゴリ", "priority": "high/medium/low", "details": "詳細"}}
    ],
    "needs": [
        {{"need": "ニーズ内容", "urgency": "high/medium/low", "budget_hint": "予算のヒント"}}
    ],
    "keywords": ["キーワード1", "キーワード2"],
    "summary": "議事録の要約（3-5文）",
    "company_size_estimate": "small/medium/large/enterprise",
    "decision_maker_present": true/false,
    "next_actions": ["アクション1", "アクション2"],
    "confidence_score": 0.0-1.0
}}

## 注意事項
- 課題とニーズは具体的に抽出してください
- 予算に関するヒントがあれば記載してください
- 決裁者の参加有無は出席者情報から推測してください
- confidence_scoreは分析の確信度です（情報が少ない場合は低く）
"""


class AnalysisService:
    """Meeting minutes analysis service using LLM."""

    def __init__(self):
        self.llm_client = LLMClient(
            base_url=settings.llm_service_url,
            secret=settings.internal_api_secret,
        )

    async def analyze_meeting(
        self,
        meeting: MeetingMinute,
        db: Session,
        tenant_id: Optional[UUID] = None,
        store_in_graph: bool = True,
    ) -> MeetingMinuteAnalysis:
        """
        Analyze a meeting minute using LLM.

        Args:
            meeting: The meeting minute to analyze
            db: Database session
            tenant_id: Tenant ID for multi-tenancy (optional)
            store_in_graph: Whether to store analysis in Neo4j graph

        Returns:
            MeetingMinuteAnalysis with extracted information
        """
        logger.info(f"Analyzing meeting minute: {meeting.id}")

        # Prepare prompt
        prompt = ANALYSIS_PROMPT.format(
            company_name=meeting.company_name,
            industry=meeting.industry or "不明",
            area=meeting.area or "不明",
            meeting_date=meeting.meeting_date.isoformat() if meeting.meeting_date else "不明",
            raw_text=meeting.raw_text[:settings.max_meeting_text_length],
        )

        try:
            # Call LLM
            response = await self._call_llm(prompt)

            # Parse response
            analysis_data = self._parse_analysis_response(response)

            # Create analysis result
            analysis = MeetingMinuteAnalysis(
                meeting_minute_id=meeting.id,
                company_name=meeting.company_name,
                industry=meeting.industry,
                area=meeting.area,
                issues=[ExtractedIssue(**i) for i in analysis_data.get("issues", [])],
                needs=[ExtractedNeed(**n) for n in analysis_data.get("needs", [])],
                keywords=analysis_data.get("keywords", []),
                summary=analysis_data.get("summary", ""),
                company_size_estimate=analysis_data.get("company_size_estimate"),
                decision_maker_present=analysis_data.get("decision_maker_present", False),
                next_actions=analysis_data.get("next_actions", []),
                follow_up_date=meeting.next_action_date,
                confidence_score=analysis_data.get("confidence_score", 0.5),
                analysis_timestamp=datetime.utcnow(),
            )

            # Update meeting status and parsed_json
            meeting.parsed_json = analysis_data
            meeting.status = "analyzed"
            db.commit()

            # Extract v2 entities via api-admin internal API
            entity_data = None
            if store_in_graph:
                entity_data = await self._extract_v2_entities(meeting, db)

            # Store analysis in Neo4j graph using v2 schema
            if store_in_graph:
                try:
                    graph_tenant_id = tenant_id or UUID("00000000-0000-0000-0000-000000000000")
                    graph_data = {
                        "company_name": meeting.company_name,
                        "industry": meeting.industry,
                        "target_persona": analysis_data.get("company_size_estimate"),
                        "issues": [i.get("issue", "") for i in analysis_data.get("issues", [])],
                        "needs": [n.get("need", "") for n in analysis_data.get("needs", [])],
                    }
                    await sales_graph_service.store_meeting_analysis_v2(
                        meeting_id=meeting.id,
                        tenant_id=graph_tenant_id,
                        user_id=meeting.created_by,
                        analysis_result=graph_data,
                        entity_data=entity_data,
                    )
                    logger.info(f"Stored v2 analysis in graph for meeting: {meeting.id}")
                except Exception as e:
                    logger.warning(f"Failed to store v2 analysis in graph: {e}")

            logger.info(f"Analysis completed for meeting: {meeting.id}")
            return analysis

        except Exception as e:
            logger.error(f"Analysis failed for meeting {meeting.id}: {e}")
            raise

    async def _extract_v2_entities(
        self,
        meeting: MeetingMinute,
        db: Session,
    ) -> Optional[Dict[str, Any]]:
        """Extract v2 entities via api-admin internal API.

        Splits meeting text into ~3000 char segments and calls the
        internal entity extraction endpoint. Saves results to meeting record.
        Returns entity_data on success, None on failure.
        """
        try:
            meeting.entity_extraction_status = "processing"
            db.commit()

            # Split raw_text into segments of ~3000 chars
            raw_text = meeting.raw_text or ""
            segment_size = 3000
            texts = []
            for i in range(0, len(raw_text), segment_size):
                segment = raw_text[i:i + segment_size]
                if segment.strip():
                    texts.append(segment)

            if not texts:
                meeting.entity_extraction_status = "completed"
                meeting.entity_data = {
                    "entities": {}, "relations": [],
                    "statistics": {"total_entities": 0},
                }
                db.commit()
                return meeting.entity_data

            url = f"{settings.admin_service_url}/internal/graph/extract-entities"
            async with httpx.AsyncClient(timeout=330.0) as client:
                resp = await client.post(
                    url,
                    json={
                        "texts": texts,
                        "source_id": str(meeting.id),
                        "source_type": "meeting",
                        "timeout": 300,
                    },
                    headers={"X-Internal-Secret": settings.internal_api_secret},
                )

            if resp.status_code == 200:
                result = resp.json()
                if result.get("success"):
                    meeting.entity_data = result.get("entity_data")
                    meeting.entity_extraction_status = "completed"
                    db.commit()
                    logger.info(f"V2 entity extraction completed for meeting {meeting.id}")
                    return meeting.entity_data

            # Non-200 or unsuccessful
            logger.warning(
                f"V2 entity extraction failed for meeting {meeting.id}: "
                f"status={resp.status_code}"
            )
            meeting.entity_extraction_status = "failed"
            db.commit()
            return None

        except Exception as e:
            logger.warning(f"V2 entity extraction error for meeting {meeting.id}: {e}")
            try:
                meeting.entity_extraction_status = "failed"
                db.commit()
            except Exception:
                pass
            return None

    async def extract_industry_area(
        self, raw_text: str, company_name: str
    ) -> Dict[str, Optional[str]]:
        """Extract industry and area from meeting text using a lightweight LLM call.

        Returns {"industry": str|None, "area": str|None}.
        Never raises; returns nulls on failure.
        """
        try:
            prompt = EXTRACTION_PROMPT.format(
                company_name=company_name,
                raw_text=raw_text[:3000],
            )
            result = await self.llm_client.generate(
                prompt=prompt,
                task_type="extraction",
                service_name="api-sales",
                temperature=0.1,
                max_tokens=500,
                format="json",
            )
            response = result.get("response", "")
            data = self._parse_json_response(response)
            industry = data.get("industry")
            area = data.get("area")
            # Treat literal "null" string as None
            if isinstance(industry, str) and industry.lower() in ("null", "none", "不明", ""):
                industry = None
            if isinstance(area, str) and area.lower() in ("null", "none", "不明", ""):
                area = None
            # Enforce max_length=100
            if industry and len(industry) > 100:
                industry = industry[:100]
            if area and len(area) > 100:
                area = area[:100]
            return {"industry": industry, "area": area}
        except Exception as e:
            logger.warning(f"Failed to extract industry/area: {e}")
            return {"industry": None, "area": None}

    def _parse_json_response(self, response: str) -> Dict[str, Any]:
        """Parse a JSON response from LLM, handling common formatting issues."""
        import re

        response = response.strip()
        # Strip markdown code blocks
        code_match = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', response, re.DOTALL | re.IGNORECASE)
        if code_match:
            response = code_match.group(1).strip()

        # Try direct parse
        try:
            return json.loads(response)
        except json.JSONDecodeError:
            pass

        # Try to find JSON object
        json_match = re.search(r'\{[\s\S]*\}', response)
        if json_match:
            try:
                return json.loads(json_match.group(0))
            except json.JSONDecodeError:
                # Fix trailing commas and single quotes
                fixed = re.sub(r',\s*([}\]])', r'\1', json_match.group(0))
                fixed = fixed.replace("'", '"')
                try:
                    return json.loads(fixed)
                except json.JSONDecodeError:
                    pass

        return {}

    async def _call_llm(self, prompt: str) -> str:
        """Call LLM via api-llm and return response."""
        try:
            result = await self.llm_client.generate(
                prompt=prompt,
                task_type="analysis",
                service_name="api-sales",
                temperature=0.3,
                provider_options={"num_ctx": get_chat_num_ctx()},
            )
            return result.get("response", "")
        except Exception as e:
            logger.error(f"LLM call failed: {e}")
            raise

    def _parse_analysis_response(self, response: str) -> Dict[str, Any]:
        """Parse LLM response as JSON."""
        import re

        try:
            # Try to extract JSON from response
            original_response = response
            response = response.strip()

            # Handle markdown code blocks with various formats
            # Match ```json, ``` json, ```JSON, etc.
            code_block_pattern = r'```(?:json)?\s*\n?(.*?)\n?```'
            code_match = re.search(code_block_pattern, response, re.DOTALL | re.IGNORECASE)
            if code_match:
                response = code_match.group(1).strip()
            else:
                # Try simpler patterns
                if response.startswith("```json"):
                    response = response[7:]
                elif response.startswith("```"):
                    response = response[3:]
                if response.endswith("```"):
                    response = response[:-3]
                response = response.strip()

            # Try direct JSON parse first
            try:
                return json.loads(response)
            except json.JSONDecodeError:
                pass

            # Try to find JSON object in the response
            json_pattern = r'\{[\s\S]*\}'
            json_match = re.search(json_pattern, response)
            if json_match:
                json_str = json_match.group(0)
                try:
                    return json.loads(json_str)
                except json.JSONDecodeError:
                    # Try to fix common JSON issues
                    # Fix trailing commas
                    json_str = re.sub(r',\s*([}\]])', r'\1', json_str)
                    # Fix single quotes to double quotes
                    json_str = json_str.replace("'", '"')
                    try:
                        return json.loads(json_str)
                    except json.JSONDecodeError:
                        pass

            logger.warning(f"Failed to parse LLM response as JSON, response: {response[:200]}")
            # Return minimal structure with parsed summary
            return {
                "issues": [],
                "needs": [],
                "keywords": [],
                "summary": "解析結果のパースに失敗しました。再解析をお試しください。",
                "confidence_score": 0.3,
            }
        except Exception as e:
            logger.error(f"Unexpected error parsing LLM response: {e}")
            return {
                "issues": [],
                "needs": [],
                "keywords": [],
                "summary": "解析中にエラーが発生しました。",
                "confidence_score": 0.1,
            }

    async def extract_keywords(self, text: str) -> List[str]:
        """Extract keywords from text."""
        prompt = f"""以下のテキストから重要なキーワードを10個以内で抽出してください。
カンマ区切りで出力してください。

テキスト:
{text[:5000]}

キーワード:"""

        response = await self._call_llm(prompt)
        keywords = [k.strip() for k in response.split(",") if k.strip()]
        return keywords[:10]

    async def summarize_text(self, text: str, max_length: int = 500) -> str:
        """Summarize text."""
        prompt = f"""以下のテキストを{max_length}文字以内で要約してください。

テキスト:
{text[:10000]}

要約:"""

        response = await self._call_llm(prompt)
        return response[:max_length]
