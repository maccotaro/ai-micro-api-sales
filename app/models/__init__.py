"""Sales API Models"""
from app.models.meeting import MeetingMinute, ProposalHistory
from app.models.master import Product, Campaign, SimulationParam, WageData
from app.models.chat import ChatConversation, ChatMessage

__all__ = [
    "MeetingMinute",
    "ProposalHistory",
    "Product",
    "Campaign",
    "SimulationParam",
    "WageData",
    "ChatConversation",
    "ChatMessage",
]
