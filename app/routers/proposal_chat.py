"""
Proposal Chat Router

商材提案RAGシステムのチャットAPI。
顧客要件を入力として、RAG検索→料金取得→提案生成のフローを提供する。
"""
import logging
from typing import Optional, List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request

# デフォルトテナントID（tenant_idがない場合に使用）
DEFAULT_TENANT_ID = UUID("00000000-0000-0000-0000-000000000000")
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.core.security import require_sales_access
from app.services.proposal_chat_service import proposal_chat_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/proposal-chat", tags=["proposal-chat"])


# =============================================================================
# Request/Response Schemas
# =============================================================================

class ProposalChatRequest(BaseModel):
    """提案チャットリクエスト"""
    query: str = Field(
        ...,
        min_length=10,
        max_length=10000,
        description="顧客要件または議事録テキスト",
    )
    knowledge_base_id: UUID = Field(
        ...,
        description="商材ナレッジベースのID",
    )
    area: Optional[str] = Field(
        None,
        description="エリアフィルタ（例: 関東、関西）",
    )
    pipeline: Optional[str] = Field(
        None,
        description="パイプラインバージョン（例: v1, v2）",
    )
    model: Optional[str] = Field(
        None,
        description="使用するチャットモデル名",
    )
    think: Optional[bool] = Field(
        None,
        description="思考モード（extended thinking）を有効にするか",
    )


class ProposalResponse(BaseModel):
    """提案レスポンス（非ストリーミング）"""
    proposal: str = Field(..., description="生成された提案文")
    media_names: List[str] = Field(default=[], description="マッチした媒体名一覧")
    total_products: int = Field(default=0, description="検索された商材数")
    total_pricing: int = Field(default=0, description="取得された料金プラン数")
    generated_at: str = Field(..., description="生成日時")


# =============================================================================
# Endpoints
# =============================================================================

@router.post("/stream")
async def stream_proposal_chat(
    request: ProposalChatRequest,
    http_request: Request,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_sales_access),
):
    """
    商材提案をストリーミング生成。

    SSE (Server-Sent Events) 形式でレスポンスを返す。

    **イベントタイプ:**
    - `start`: 処理開始（status: searching）
    - `info`: 処理状況（message, media_names, status）
    - `thinking`: 思考プロセスの断片（think=true時のみ）
    - `content`: 提案テキストの断片
    - `done`: 処理完了（media_names, total_products, total_pricing）
    - `error`: エラー発生

    **使用例:**
    ```javascript
    const response = await fetch('/api/sales/proposal-chat/stream', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            query: '飲食店の人材採用で困っている。予算は50万円程度',
            knowledge_base_id: 'xxx-xxx-xxx'
        })
    });
    const reader = response.body.getReader();
    while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        // Parse SSE data
    }
    ```
    """
    # Extract JWT token from request
    auth_header = http_request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Authorization header required")

    jwt_token = auth_header[7:]
    # tenant_idがない場合はデフォルトを使用
    tenant_id_str = current_user.get("tenant_id")
    tenant_id = UUID(tenant_id_str) if tenant_id_str else DEFAULT_TENANT_ID

    logger.info(
        f"Starting proposal chat stream for KB {request.knowledge_base_id} "
        f"by user {current_user.get('user_id', 'unknown')} "
        f"(tenant: {tenant_id})"
    )

    return StreamingResponse(
        proposal_chat_service.stream_proposal(
            query=request.query,
            knowledge_base_id=request.knowledge_base_id,
            tenant_id=tenant_id,
            jwt_token=jwt_token,
            db=db,
            area=request.area,
            pipeline_version=request.pipeline,
            model=request.model,
            think=request.think,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        },
    )


@router.post("/generate", response_model=ProposalResponse)
async def generate_proposal(
    request: ProposalChatRequest,
    http_request: Request,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_sales_access),
):
    """
    商材提案を生成（非ストリーミング）。

    完全な提案文を一度に返す。レスポンス時間は長くなるが、
    結果を一括で取得したい場合に使用。
    """
    # Extract JWT token from request
    auth_header = http_request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Authorization header required")

    jwt_token = auth_header[7:]
    # tenant_idがない場合はデフォルトを使用
    tenant_id_str = current_user.get("tenant_id")
    tenant_id = UUID(tenant_id_str) if tenant_id_str else DEFAULT_TENANT_ID

    logger.info(
        f"Generating proposal for KB {request.knowledge_base_id} "
        f"by user {current_user.get('user_id', 'unknown')} "
        f"(tenant: {tenant_id})"
    )

    try:
        result = await proposal_chat_service.generate_proposal(
            query=request.query,
            knowledge_base_id=request.knowledge_base_id,
            tenant_id=tenant_id,
            jwt_token=jwt_token,
            db=db,
            area=request.area,
            pipeline_version=request.pipeline,
            model=request.model,
            think=request.think,
        )

        return ProposalResponse(
            proposal=result["proposal"],
            media_names=result["media_names"],
            total_products=len(result["search_results"]),
            total_pricing=sum(len(p) for p in result["pricing_info"].values()),
            generated_at=result["generated_at"],
        )

    except Exception as e:
        logger.error(f"Proposal generation failed: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"提案生成中にエラーが発生しました: {str(e)}",
        )


@router.get("/health")
async def health_check():
    """
    商材提案チャットサービスのヘルスチェック。
    """
    return {
        "status": "healthy",
        "service": "proposal-chat",
        "features": [
            "RAG search integration",
            "Pricing lookup",
            "LLM proposal generation",
            "SSE streaming",
        ],
    }
