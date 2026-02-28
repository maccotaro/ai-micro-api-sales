"""Sales API Models"""
from app.models.meeting import MeetingMinute, ProposalHistory
from app.models.master import Campaign, SimulationParam, WageData, SeasonalTrend, DocumentLink
from app.models.chat import ChatConversation, ChatMessage

__all__ = [
    "MeetingMinute",
    "ProposalHistory",
    "Campaign",
    "SimulationParam",
    "WageData",
    "SeasonalTrend",
    "DocumentLink",
    "ChatConversation",
    "ChatMessage",
]
