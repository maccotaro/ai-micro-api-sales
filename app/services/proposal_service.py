"""
Proposal Generation Service

Generates sales proposals based on meeting analysis and product matching.
"""
import logging
import json
from datetime import datetime
from decimal import Decimal
from typing import Optional, Dict, Any, List
from uuid import UUID

from langchain_ollama import ChatOllama
from sqlalchemy.orm import Session
from sqlalchemy import and_

from app.core.config import settings
from app.models.meeting import MeetingMinute, ProposalHistory
from app.models.master import Product, Campaign
from app.schemas.meeting import (
    MeetingMinuteAnalysis,
    ProposalContent,
    RecommendedProduct,
    ProposalResponse,
)

logger = logging.getLogger(__name__)


PROPOSAL_PROMPT = """あなたは営業支援AIアシスタントです。以下の情報を基に、最適な提案を作成してください。

## 顧客情報
会社名: {company_name}
業種: {industry}
地域: {area}

## 議事録から抽出した情報
課題:
{issues}

ニーズ:
{needs}

キーワード: {keywords}

## 推奨商品候補
{products}

## 出力形式（JSON）
以下のJSON形式で出力してください。

{{
    "title": "提案タイトル",
    "summary": "提案の概要（3-5文）",
    "recommended_products": [
        {{
            "product_id": "商品ID",
            "product_name": "商品名",
            "category": "カテゴリ",
            "reason": "推奨理由（課題・ニーズとの関連を具体的に）",
            "match_score": 0.0-1.0
        }}
    ],
    "talking_points": [
        "トークポイント1",
        "トークポイント2"
    ],
    "objection_handlers": {{
        "価格が高い": "価格に対する回答",
        "導入が難しい": "導入に対する回答"
    }}
}}
"""


class ProposalService:
    """Proposal generation service."""

    def __init__(self):
        self.llm = ChatOllama(
            model=settings.default_llm_model,
            base_url=settings.ollama_base_url,
            temperature=0.5,
        )

    async def generate_proposal(
        self,
        meeting: MeetingMinute,
        analysis: MeetingMinuteAnalysis,
        db: Session,
        user_id: UUID,
    ) -> ProposalHistory:
        """
        Generate a proposal based on meeting analysis.

        Args:
            meeting: The meeting minute
            analysis: Analysis results
            db: Database session
            user_id: ID of the user generating the proposal

        Returns:
            Created ProposalHistory
        """
        logger.info(f"Generating proposal for meeting: {meeting.id}")

        # Get matching products
        products = self._get_matching_products(analysis, db)

        # Prepare prompt
        issues_text = "\n".join([
            f"- {i.issue} (優先度: {i.priority or '不明'})"
            for i in analysis.issues
        ]) or "なし"

        needs_text = "\n".join([
            f"- {n.need} (緊急度: {n.urgency or '不明'})"
            for n in analysis.needs
        ]) or "なし"

        products_text = "\n".join([
            f"- {p.name} ({p.category}): {p.description or '説明なし'}"
            for p in products[:10]
        ]) or "商品情報なし"

        prompt = PROPOSAL_PROMPT.format(
            company_name=meeting.company_name,
            industry=analysis.industry or "不明",
            area=analysis.area or "不明",
            issues=issues_text,
            needs=needs_text,
            keywords=", ".join(analysis.keywords),
            products=products_text,
        )

        try:
            # Call LLM
            response = await self._call_llm(prompt)
            proposal_data = self._parse_proposal_response(response, products)

            # Get applicable campaigns
            campaigns = self._get_applicable_campaigns(
                [p.id for p in products],
                db
            )

            # Create proposal
            proposal = ProposalHistory(
                meeting_minute_id=meeting.id,
                proposal_json=proposal_data,
                recommended_products=[
                    UUID(p["product_id"]) for p in proposal_data.get("recommended_products", [])
                    if self._is_valid_uuid(p.get("product_id"))
                ],
                simulation_results={
                    "applicable_campaigns": [
                        {"id": str(c.id), "name": c.name, "discount_rate": float(c.discount_rate) if c.discount_rate else None}
                        for c in campaigns
                    ]
                },
                created_by=user_id,
            )

            db.add(proposal)

            # Update meeting status
            meeting.status = "proposed"
            db.commit()
            db.refresh(proposal)

            logger.info(f"Proposal created: {proposal.id}")
            return proposal

        except Exception as e:
            logger.error(f"Proposal generation failed: {e}")
            raise

    def _get_matching_products(
        self,
        analysis: MeetingMinuteAnalysis,
        db: Session,
    ) -> List[Product]:
        """Get products matching the analysis."""
        query = db.query(Product).filter(Product.is_active == True)

        # Filter by industry if available
        if analysis.industry:
            # Simple keyword matching in description
            query = query.filter(
                Product.description.ilike(f"%{analysis.industry}%")
            )

        # Order by sort_order and return top products
        products = query.order_by(Product.sort_order).limit(settings.max_proposal_products).all()

        # If no industry match, get any active products
        if not products:
            products = db.query(Product).filter(
                Product.is_active == True
            ).order_by(Product.sort_order).limit(settings.max_proposal_products).all()

        return products

    def _get_applicable_campaigns(
        self,
        product_ids: List[UUID],
        db: Session,
    ) -> List[Campaign]:
        """Get applicable campaigns for products."""
        from datetime import date
        today = date.today()

        campaigns = db.query(Campaign).filter(
            and_(
                Campaign.is_active == True,
                Campaign.start_date <= today,
                Campaign.end_date >= today,
            )
        ).all()

        # Filter campaigns that target these products
        applicable = []
        for campaign in campaigns:
            if not campaign.target_products:
                # Campaign applies to all products
                applicable.append(campaign)
            elif any(pid in (campaign.target_products or []) for pid in product_ids):
                applicable.append(campaign)

        return applicable

    async def _call_llm(self, prompt: str) -> str:
        """Call LLM and return response."""
        try:
            response = self.llm.invoke(prompt)
            return response.content
        except Exception as e:
            logger.error(f"LLM call failed: {e}")
            raise

    def _parse_proposal_response(
        self,
        response: str,
        products: List[Product],
    ) -> Dict[str, Any]:
        """Parse LLM response as JSON."""
        try:
            response = response.strip()

            # Handle markdown code blocks
            if response.startswith("```json"):
                response = response[7:]
            if response.startswith("```"):
                response = response[3:]
            if response.endswith("```"):
                response = response[:-3]

            data = json.loads(response.strip())

            # Validate and fix product IDs
            product_map = {p.name: str(p.id) for p in products}
            for rec in data.get("recommended_products", []):
                # Try to match product name to ID
                if rec.get("product_name") in product_map:
                    rec["product_id"] = product_map[rec["product_name"]]

            return data

        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse proposal response: {e}")
            # Return minimal structure with available products
            return {
                "title": "提案書",
                "summary": "自動生成された提案書です。",
                "recommended_products": [
                    {
                        "product_id": str(p.id),
                        "product_name": p.name,
                        "category": p.category,
                        "reason": "お客様のニーズに合致する可能性があります。",
                        "match_score": 0.5,
                    }
                    for p in products[:3]
                ],
                "talking_points": ["課題解決のご提案", "コスト削減効果"],
                "objection_handlers": {},
            }

    def _is_valid_uuid(self, value: Any) -> bool:
        """Check if value is a valid UUID string."""
        if not value:
            return False
        try:
            UUID(str(value))
            return True
        except (ValueError, TypeError):
            return False

    async def update_feedback(
        self,
        proposal_id: UUID,
        feedback: str,
        comment: Optional[str],
        db: Session,
    ) -> ProposalHistory:
        """Update proposal feedback."""
        proposal = db.query(ProposalHistory).filter(
            ProposalHistory.id == proposal_id
        ).first()

        if not proposal:
            raise ValueError(f"Proposal not found: {proposal_id}")

        proposal.feedback = feedback
        proposal.feedback_comment = comment
        db.commit()
        db.refresh(proposal)

        logger.info(f"Updated feedback for proposal: {proposal_id}")
        return proposal
