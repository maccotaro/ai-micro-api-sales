# ai-micro-api-sales コードスタイル・規約

## Pythonスタイル

### フォーマッター・リンター
- **Black**: コードフォーマット
- **Ruff**: リンティング
- **MyPy**: 型チェック

### 命名規則
- **クラス**: PascalCase (`MeetingMinute`, `ProposalService`)
- **関数/メソッド**: snake_case (`analyze_meeting`, `generate_proposal`)
- **変数**: snake_case (`meeting_id`, `analysis_result`)
- **定数**: UPPER_SNAKE_CASE (`MAX_TOKENS`, `DEFAULT_TEMPERATURE`)

### 型ヒント
- 必須: すべての関数引数と戻り値に型ヒント
- Pydantic: リクエスト/レスポンススキーマに使用

## サービス層パターン

```
services/
├── analysis_service.py   # 議事録解析（LLM呼び出し）
├── proposal_service.py   # 提案生成
├── simulation_service.py # シミュレーション計算
├── embedding_service.py  # ベクトル検索
└── graph/
    ├── neo4j_client.py   # Neo4j接続
    └── sales_graph_service.py
```

## LLM呼び出しパターン

```python
from app.services.llm_client import OllamaClient

async def analyze_meeting(content: str) -> AnalysisResult:
    client = OllamaClient()
    response = await client.generate(
        model="gemma2:9b",
        prompt=ANALYSIS_PROMPT.format(content=content),
        temperature=0.3  # 解析は低め
    )
    return parse_analysis(response)
```

## Neo4jクエリパターン

```python
async def get_recommendations(meeting_id: str) -> List[Recommendation]:
    query = """
    MATCH (m:Meeting {id: $meeting_id})-[:HAS_PROBLEM]->(p:Problem)
    MATCH (p)<-[:SOLVES]-(prod:Product)
    RETURN prod
    """
    return await self.client.run(query, {"meeting_id": meeting_id})
```

## api-rag連携パターン

```python
async def search_products(query: str, kb_id: str) -> SearchResult:
    response = await httpx.post(
        f"{settings.RAG_SERVICE_URL}/api/rag/search/hybrid",
        json={
            "query": query,
            "knowledge_base_ids": [kb_id],
            "top_k": 10
        }
    )
    return response.json()
```

## エラーハンドリング
- HTTPExceptionで適切なステータスコードを返す
- LLM/Neo4j呼び出し失敗時はフォールバック処理

## セキュリティ
- JWT認証必須
- ユーザー所有権チェック（自分のデータのみアクセス可能）
