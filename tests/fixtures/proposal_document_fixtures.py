"""
Fixtures for proposal document pipeline tests (Stage 6-10).
Provides mock data for Stage 0 context, Stage 1 output, KB results, and DB records.
"""
from uuid import uuid4


TENANT_ID = uuid4()
USER_ID = uuid4()
MINUTE_ID = uuid4()
PIPELINE_RUN_ID = uuid4()


def make_stage0_context(
    industry="警備",
    area="東京",
    job_type="施設警備",
    company_name="サンエス警備保障株式会社",
):
    """Stage 0 context mock — minimal version for Stage 6+ input."""
    return {
        "meeting": {
            "company_name": company_name,
            "industry": industry,
            "area": area,
            "raw_text": "警備員の採用が課題です。施設警備の求人を出しているが応募が集まらない。",
            "parsed_json": {
                "issues": ["応募数不足", "採用コスト高"],
                "needs": ["応募数増加", "コスト削減"],
            },
            "meeting_date": "2026-03-10",
            "next_action_date": "2026-03-20",
        },
        "kb_results": {},
        "product_data": [],
        "simulation_data": [],
        "wage_data": [],
        "publication_data": [],
        "campaign_data": [],
        "search_tenant_id": str(TENANT_ID),
    }


def make_stage1_output():
    """Stage 1 output mock — issues + BANT-C."""
    return {
        "issues": [
            {
                "id": "I-1",
                "category": "採用",
                "title": "施設警備員の応募数不足",
                "detail": "月間応募数が目標の半分以下",
                "evidence": "応募が集まらない",
                "bant_c": {
                    "budget": {"status": "把握済み", "detail": "月額30万円", "estimated_range": "30万円"},
                    "authority": {"status": "把握済み", "detail": "人事部長が決裁者"},
                    "need": {"status": "把握済み", "detail": "施設警備員5名採用"},
                    "timeline": {"status": "把握済み", "detail": "来月中"},
                    "competitor": {"status": "未把握", "detail": ""},
                },
            },
            {
                "id": "I-2",
                "category": "ブランディング",
                "title": "求職者の警備業界に対する誤解",
                "detail": "警備＝屋外のきつい仕事というイメージ",
                "evidence": "応募が集まらない",
                "bant_c": {
                    "budget": {"status": "未把握", "detail": ""},
                    "authority": {"status": "把握済み", "detail": "人事部長"},
                    "need": {"status": "把握済み", "detail": "イメージ改善"},
                    "timeline": {"status": "未把握", "detail": ""},
                    "competitor": {"status": "未把握", "detail": ""},
                },
            },
        ],
        "company_context": {
            "industry": "警備",
            "company_size": "中規模",
            "current_media": "マイナビバイト",
            "key_decision_maker": "人事部長",
        },
    }


def make_proposal_kb_chunks():
    """KB search results mock — approved proposal reference documents."""
    return [
        {
            "content": "【提案書】施設警備の差別化訴求。施設警備は屋内・空調完備で体力負担が少ない。交通誘導との比較表を提示し、求職者の誤解を解消。",
            "metadata": {"source": "proposal_kb", "industry": "警備"},
            "score": 0.85,
        },
        {
            "content": "【提案書】シニア層向け施設警備採用。60代の求職者が重視する4つの軸：体力・人間関係・通勤・社会貢献。各軸に対応したキャッチコピー例。",
            "metadata": {"source": "proposal_kb", "industry": "警備"},
            "score": 0.82,
        },
    ]


def make_end_user_psychology_chunks():
    """KB search results mock — end-user (job seeker) psychology patterns."""
    return [
        {
            "content": "【シニア求職者心理】体力への不安：年齢を重ねても無理なく続けられるか。人間関係の不安：若い人ばかりの職場で馴染めるか。社会貢献欲求：まだ社会の役に立ちたい。",
            "metadata": {"type": "end_user", "industry": "警備", "target": "シニア"},
            "score": 0.90,
        },
    ]


def make_decision_maker_psychology_chunks():
    """KB search results mock — decision-maker psychology patterns."""
    return [
        {
            "content": "【採用担当者心理】費用対効果への関心：いくらかけたら何名採れるのか。過去施策の失敗体験：前の媒体では応募が来なかった。上申の必要性：上に説明できる根拠がほしい。",
            "metadata": {"type": "decision_maker", "industry": "警備", "role": "人事担当"},
            "score": 0.88,
        },
    ]


def make_success_case_results():
    """success_case_embeddings search results mock."""
    return [
        {
            "title": "警備会社A社：施設警備員採用成功事例",
            "industry": "警備",
            "area": "東京",
            "metrics": {"pv_increase": "7.4倍", "applications": 24, "hires": 8},
            "achievement": "原稿改善でPV7.4倍、応募24件、採用8名",
            "content": "キャッチコピーを「警備員急募」から「60歳からのセカンドキャリア。冷暖房完備の施設警備」に変更。",
        },
    ]


def make_publication_records():
    """publication_records query results mock — high-performing entries."""
    return [
        {
            "plan_category": "マイナビバイト - 求人AD",
            "prefecture": "東京都",
            "job_category_large": "警備・清掃",
            "job_title": "施設警備員",
            "catchcopy": "60歳からのセカンドキャリア。冷暖房完備の施設警備",
            "pv_count": 890,
            "application_count": 24,
            "hire_count": 8,
            "wage_amount": 1200,
        },
        {
            "plan_category": "マイナビバイト - 求人AD",
            "prefecture": "東京都",
            "job_category_large": "警備・清掃",
            "job_title": "施設警備員",
            "catchcopy": "警備員急募！未経験歓迎",
            "pv_count": 120,
            "application_count": 3,
            "hire_count": 0,
            "wage_amount": 1100,
        },
    ]


def make_stage6_context():
    """Complete Stage 6 output mock."""
    return {
        "proposal_kb_chunks": make_proposal_kb_chunks(),
        "end_user_psychology_chunks": make_end_user_psychology_chunks(),
        "decision_maker_psychology_chunks": make_decision_maker_psychology_chunks(),
        "success_cases": make_success_case_results(),
        "publication_records": make_publication_records(),
    }


def make_stage7_output():
    """Stage 7 output mock — industry & target analysis."""
    return {
        "industry_analysis": {
            "industry_name": "警備",
            "job_types": [
                {
                    "name": "施設警備",
                    "characteristics": ["屋内勤務", "空調完備", "座り仕事あり"],
                    "common_misconceptions": ["警備＝屋外のきつい仕事"],
                    "actual_reality": "施設警備は屋内で安定した環境",
                },
                {
                    "name": "交通誘導",
                    "characteristics": ["屋外", "体力必要", "天候影響"],
                    "common_misconceptions": [],
                    "actual_reality": "",
                },
            ],
            "competitive_advantages": ["施設警備は他の警備職種と比べて離職率が低い"],
        },
        "target_insights": {
            "primary_target": "シニア層（60歳以上）",
            "psychological_axes": [
                {
                    "axis": "体力への不安",
                    "detail": "年齢を重ねても無理なく続けられるか",
                    "appeal_direction": "施設警備は座り仕事も多く体力負担が少ない",
                },
                {
                    "axis": "人間関係の不安",
                    "detail": "若い人ばかりの職場で馴染めるか",
                    "appeal_direction": "同年代の同僚が多い職場環境",
                },
                {
                    "axis": "社会貢献への欲求",
                    "detail": "まだ社会の役に立ちたい",
                    "appeal_direction": "地域の安全を守る社会的意義",
                },
            ],
        },
        "decision_maker_insights": {
            "role": "人事担当",
            "judgment_criteria": ["費用対効果", "応募数の予測可能性"],
            "common_concerns": ["前の媒体では応募が来なかった", "上に説明できる根拠がほしい"],
            "required_evidence": ["同業界の成功事例", "PV・応募数の実績データ"],
        },
        "source": "kb_data",
    }


def make_stage8_output():
    """Stage 8 output mock — appeal strategy."""
    return {
        "strategy_axes": [
            {
                "id": "S-1",
                "title": "施設警備と交通誘導の差別化訴求",
                "rationale": "求職者の「警備＝きつい屋外作業」という誤解を解消",
                "target_psychology": "体力への不安",
                "catchcopies": [
                    {
                        "text": "60歳から始めるセカンドキャリア。施設警備は座り仕事も多いんです。",
                        "psychology_link": "体力への不安 → 座り仕事の訴求で安心感",
                    },
                ],
            },
            {
                "id": "S-2",
                "title": "シニア層のニーズ対応",
                "rationale": "4つの心理軸に直接応答",
                "target_psychology": "複合的な不安",
                "catchcopies": [
                    {
                        "text": "同世代の仲間と、地域の安全を守る仕事です。",
                        "psychology_link": "人間関係の不安 + 社会貢献欲求への訴求",
                    },
                ],
            },
        ],
        "success_case_references": [
            {
                "case_summary": "警備会社A社: 施設警備員募集",
                "before": {"catchcopy": "警備員急募！", "pv": 120, "applications": 3},
                "after": {"catchcopy": "60歳からのセカンドキャリア。冷暖房完備の施設警備", "pv": 890, "applications": 24},
                "improvement": "PV 7.4倍、応募 8倍",
            },
        ],
    }


def make_stage9_output():
    """Stage 9 output mock — story structure."""
    return {
        "story_theme": "シニア層の施設警備採用における不安解消と実績訴求",
        "pages": [
            {
                "page_number": 1,
                "title": "本日のご提案",
                "purpose": "アジェンダ提示",
                "key_points": ["3つの戦略軸の概要"],
                "data_sources": ["stage8_strategy_axes"],
            },
            {
                "page_number": 2,
                "title": "御社の採用課題",
                "purpose": "課題提起・共感",
                "key_points": ["現状の応募数とギャップ", "業界全体の傾向"],
                "data_sources": ["stage1_issues", "stage6_publication_data"],
            },
            {
                "page_number": 3,
                "title": "施設警備の本当の姿",
                "purpose": "業界洞察・求職者の誤解を解消",
                "key_points": ["施設警備vs交通誘導の比較", "求職者の誤解と実態のギャップ"],
                "data_sources": ["stage7_industry_analysis"],
            },
            {
                "page_number": 4,
                "title": "シニア求職者が本当に求めていること",
                "purpose": "ターゲットインサイト",
                "key_points": ["3つの心理軸", "各軸への訴求方向"],
                "data_sources": ["stage7_target_insights"],
            },
            {
                "page_number": 5,
                "title": "提案①：施設警備の差別化訴求",
                "purpose": "戦略提案",
                "key_points": ["差別化の根拠", "キャッチコピー例"],
                "data_sources": ["stage8_strategy_axes"],
            },
            {
                "page_number": 6,
                "title": "提案②：シニア層へのニーズ対応",
                "purpose": "戦略提案",
                "key_points": ["心理軸への対応", "キャッチコピー例"],
                "data_sources": ["stage8_strategy_axes"],
            },
            {
                "page_number": 7,
                "title": "成功事例",
                "purpose": "エビデンス",
                "key_points": ["Before/After比較", "PV・応募・採用の数値"],
                "data_sources": ["stage8_success_case_references"],
            },
            {
                "page_number": 8,
                "title": "次のステップ",
                "purpose": "クロージング",
                "key_points": ["具体的なアクション", "スケジュール"],
                "data_sources": ["stage1_issues"],
            },
        ],
    }
