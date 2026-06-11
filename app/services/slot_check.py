"""Required-slot definition and missing-alert computation (抜け漏れチェッカー).

PoC requirement: define the information a proposal needs (必須スロット) and,
deterministically, surface any unmet slot as an alert with a sample question.
Detection draws from the meeting's parsed_json, Stage 1 BANT-C output, and the
Stage 2 proposal output. This is non-blocking by default (warning only); the
caller may block generation when config.block_on_missing_slots is True.
"""
import logging
from typing import Optional

logger = logging.getLogger(__name__)


def _nonempty(value) -> bool:
    """True if a parsed_json section / field carries real content."""
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, dict)):
        return len(value) > 0
    return bool(value)


def _any_bant(stage1_output: dict, key: str) -> bool:
    """True if any extracted issue carries a non-empty BANT-C field."""
    issues = (stage1_output or {}).get("issues") or []
    for issue in issues:
        bant = (issue or {}).get("bant_c") or {}
        if _nonempty(bant.get(key)):
            return True
    return False


def _issue_label(issue: dict) -> str:
    return (issue or {}).get("title") or (issue or {}).get("issue") or (issue or {}).get("id") or "課題"


def _addressed_issue_ids(stage2_output: dict) -> set:
    """Issue ids that have a proposal or cross-sell entry in Stage 2."""
    ids: set = set()
    s2 = stage2_output or {}
    for p in s2.get("proposals") or []:
        if isinstance(p, dict) and p.get("issue_id"):
            ids.add(str(p["issue_id"]))
    for c in s2.get("cross_sell") or []:
        if isinstance(c, dict) and c.get("issue_id"):
            ids.add(str(c["issue_id"]))
    return ids


def compute_missing_alerts(
    parsed_json: Optional[dict],
    stage1_output: Optional[dict],
    stage2_output: Optional[dict],
) -> list[dict]:
    """Return a list of unmet required-slot alerts.

    Each alert: {slot, label, reason, question_example}.
    """
    pj = parsed_json or {}
    s1 = stage1_output or {}
    alerts: list[dict] = []

    # Slot 1: 採用ターゲット (target) — parsed_json section_3
    if not _nonempty(pj.get("section_3")):
        alerts.append({
            "slot": "recruitment_target",
            "label": "採用ターゲット",
            "reason": "議事録に採用ターゲット（年齢層・属性・スキル）の記載が見当たりません。",
            "question_example": "今回の募集で狙いたい年齢層や人物像（例: シニア層、主婦層、学生）はありますか？",
        })

    # Slot 2: 予算・条件 (budget/conditions) — section_9 or BANT-C budget
    if not _nonempty(pj.get("section_9")) and not _any_bant(s1, "budget"):
        alerts.append({
            "slot": "budget_conditions",
            "label": "予算・条件",
            "reason": "採用予算や掲載条件（金額・期間・希望）の情報が不足しています。",
            "question_example": "今回の採用にかけられるご予算や、掲載期間・条件のご希望はございますか？",
        })

    # Slot 3: 意思決定プロセス (decision process) — section_10 or BANT-C authority
    if not _nonempty(pj.get("section_10")) and not _any_bant(s1, "authority"):
        alerts.append({
            "slot": "decision_process",
            "label": "意思決定プロセス",
            "reason": "決裁ルート・意思決定者・承認プロセスが把握できていません。",
            "question_example": "ご発注のご判断は、どなたがどのような流れで決定されますか？",
        })

    # Slot 4: 各課題に対応する提案の有無 (every issue addressed)
    addressed = _addressed_issue_ids(stage2_output or {})
    for issue in s1.get("issues") or []:
        iid = str((issue or {}).get("id") or "")
        if iid and iid not in addressed:
            label = _issue_label(issue)
            alerts.append({
                "slot": "issue_uncovered",
                "label": f"提案未対応の課題: {label}",
                "reason": f"課題「{label}」（{iid}）に対応する提案が生成されていません。",
                "question_example": f"課題「{label}」を解決する提案を追加で検討しますか？",
                "issue_id": iid,
            })

    return alerts


def attach_missing_alerts(
    stage5_output: dict,
    parsed_json: Optional[dict],
    stage1_output: Optional[dict],
    stage2_output: Optional[dict],
    blocking: bool = False,
) -> dict:
    """Compute and attach `missing_alerts` to the Stage 5 output."""
    if not isinstance(stage5_output, dict):
        stage5_output = {"_raw": stage5_output}
    alerts = compute_missing_alerts(parsed_json, stage1_output, stage2_output)
    stage5_output["missing_alerts"] = alerts
    stage5_output["missing_alerts_blocking"] = bool(blocking and alerts)
    if alerts:
        logger.info("Missing-slot alerts: %d (blocking=%s)", len(alerts), blocking)
    return stage5_output
