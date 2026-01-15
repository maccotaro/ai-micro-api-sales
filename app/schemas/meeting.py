"""
Meeting Minutes and Proposal Schemas
"""
from datetime import datetime, date
from decimal import Decimal
from typing import Optional, List, Dict, Any
from uuid import UUID

from pydantic import BaseModel, Field


# =====================================================
# Meeting Minute Schemas
# =====================================================

class AttendeeInfo(BaseModel):
    """出席者情報"""
    name: str
    role: Optional[str] = None
    department: Optional[str] = None


class MeetingMinuteBase(BaseModel):
    """Meeting minute base schema"""
    company_name: str = Field(..., max_length=255)
    company_id: Optional[UUID] = None
    raw_text: str
    industry: Optional[str] = Field(None, max_length=100)
    area: Optional[str] = Field(None, max_length=100)
    meeting_date: Optional[date] = None
    attendees: Optional[List[Dict[str, Any]]] = Field(default_factory=list)
    next_action_date: Optional[date] = None


class MeetingMinuteCreate(MeetingMinuteBase):
    """Schema for creating a meeting minute"""
    pass


class MeetingMinuteUpdate(BaseModel):
    """Schema for updating a meeting minute"""
    company_name: Optional[str] = Field(None, max_length=255)
    company_id: Optional[UUID] = None
    raw_text: Optional[str] = None
    parsed_json: Optional[Dict[str, Any]] = None
    industry: Optional[str] = Field(None, max_length=100)
    area: Optional[str] = Field(None, max_length=100)
    meeting_date: Optional[date] = None
    attendees: Optional[List[Dict[str, Any]]] = None
    next_action_date: Optional[date] = None
    status: Optional[str] = Field(None, pattern="^(draft|analyzed|proposed|closed)$")


class MeetingMinuteResponse(MeetingMinuteBase):
    """Schema for meeting minute response"""
    id: UUID
    parsed_json: Optional[Dict[str, Any]] = None
    status: str
    created_by: UUID
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class MeetingMinuteListResponse(BaseModel):
    """Schema for paginated meeting minute list"""
    items: List[MeetingMinuteResponse]
    total: int
    page: int
    page_size: int


# =====================================================
# Meeting Analysis Schemas
# =====================================================

class ExtractedIssue(BaseModel):
    """抽出された課題"""
    issue: str
    category: Optional[str] = None
    priority: Optional[str] = Field(None, pattern="^(high|medium|low)$")
    details: Optional[str] = None


class ExtractedNeed(BaseModel):
    """抽出されたニーズ"""
    need: str
    urgency: Optional[str] = Field(None, pattern="^(high|medium|low)$")
    budget_hint: Optional[str] = None


class MeetingMinuteAnalysis(BaseModel):
    """議事録解析結果"""
    meeting_minute_id: UUID
    company_name: str
    industry: Optional[str] = None
    area: Optional[str] = None

    # 抽出情報
    issues: List[ExtractedIssue] = Field(default_factory=list)
    needs: List[ExtractedNeed] = Field(default_factory=list)
    keywords: List[str] = Field(default_factory=list)
    summary: str

    # 会社情報推定
    company_size_estimate: Optional[str] = None
    decision_maker_present: bool = False

    # 次アクション
    next_actions: List[str] = Field(default_factory=list)
    follow_up_date: Optional[date] = None

    # 分析メタデータ
    confidence_score: float = Field(ge=0, le=1)
    analysis_timestamp: datetime


# =====================================================
# Proposal Schemas
# =====================================================

class RecommendedProduct(BaseModel):
    """推奨商品"""
    product_id: UUID
    product_name: str
    category: str
    reason: str
    match_score: float = Field(ge=0, le=1)
    price_estimate: Optional[Decimal] = None


class ProposalContent(BaseModel):
    """提案内容"""
    title: str
    summary: str
    recommended_products: List[RecommendedProduct]
    talking_points: List[str] = Field(default_factory=list)
    objection_handlers: Dict[str, str] = Field(default_factory=dict)
    success_cases: List[UUID] = Field(default_factory=list)
    estimated_value: Optional[Decimal] = None


class ProposalCreate(BaseModel):
    """Schema for creating a proposal"""
    meeting_minute_id: UUID
    proposal_json: ProposalContent
    recommended_products: List[UUID] = Field(default_factory=list)
    simulation_results: Optional[Dict[str, Any]] = None


class ProposalResponse(BaseModel):
    """Schema for proposal response"""
    id: UUID
    meeting_minute_id: UUID
    proposal_json: Dict[str, Any]
    recommended_products: List[UUID]
    simulation_results: Optional[Dict[str, Any]] = None
    feedback: Optional[str] = None
    feedback_comment: Optional[str] = None
    created_by: UUID
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ProposalFeedback(BaseModel):
    """Schema for proposal feedback"""
    feedback: str = Field(..., pattern="^(accepted|rejected|modified|pending)$")
    feedback_comment: Optional[str] = None


class ProposalListResponse(BaseModel):
    """Schema for paginated proposal list"""
    items: List[ProposalResponse]
    total: int
    page: int
    page_size: int
