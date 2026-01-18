"""Sales API Schemas"""
from app.schemas.meeting import (
    MeetingMinuteCreate,
    MeetingMinuteUpdate,
    MeetingMinuteResponse,
    MeetingMinuteListResponse,
    MeetingMinuteAnalysis,
    ProposalCreate,
    ProposalResponse,
    ProposalFeedback,
)
from app.schemas.simulation import (
    SimulationRequest,
    SimulationResult,
)
from app.schemas.chat import (
    ChatMessageCreate,
    ChatMessageResponse,
    ChatConversationCreate,
    ChatConversationResponse,
    ChatHistoryResponse,
    StreamChunk,
    ChatStreamRequest,
)

__all__ = [
    "MeetingMinuteCreate",
    "MeetingMinuteUpdate",
    "MeetingMinuteResponse",
    "MeetingMinuteListResponse",
    "MeetingMinuteAnalysis",
    "ProposalCreate",
    "ProposalResponse",
    "ProposalFeedback",
    "SimulationRequest",
    "SimulationResult",
    "ChatMessageCreate",
    "ChatMessageResponse",
    "ChatConversationCreate",
    "ChatConversationResponse",
    "ChatHistoryResponse",
    "StreamChunk",
    "ChatStreamRequest",
]
