"""Helper functions for the proposal pipeline (JSON parsing, evidence validation)."""
import json
import logging
from typing import Optional

logger = logging.getLogger(__name__)


def parse_json_response(text: str) -> dict:
    """Parse JSON from LLM response, handling markdown code blocks and truncation."""
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        lines = lines[1:]  # Remove first ```json line
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines)

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Try to repair truncated JSON by closing open brackets/braces
        repaired = _try_repair_truncated_json(text)
        if repaired is not None:
            logger.warning("Repaired truncated JSON response successfully")
            return repaired
        logger.warning("Failed to parse LLM JSON response, returning as raw text")
        return {"raw_response": text}


def _try_repair_truncated_json(text: str) -> Optional[dict]:
    """Attempt to repair truncated JSON by closing unclosed brackets/braces."""
    stripped = text.rstrip()

    in_string = False
    escape_next = False
    stack = []
    last_valid_pos = 0

    for i, ch in enumerate(stripped):
        if escape_next:
            escape_next = False
            continue
        if ch == '\\' and in_string:
            escape_next = True
            continue
        if ch == '"':
            in_string = not in_string
            if not in_string:
                last_valid_pos = i
            continue
        if in_string:
            continue
        if ch in '{[':
            stack.append(ch)
            continue
        if ch in '}]':
            if stack:
                stack.pop()
            last_valid_pos = i
            continue
        if ch in ',: \t\n\r':
            if ch in ',:':
                last_valid_pos = i
            continue
        # digits, true, false, null etc.
        last_valid_pos = i

    if not stack:
        return None

    # If we ended inside a string, truncate at last closed quote
    if in_string:
        last_quote = stripped.rfind('"', 0, len(stripped) - 1)
        if last_quote > 0:
            stripped = stripped[:last_quote + 1]
            # Recompute stack
            in_string = False
            escape_next = False
            stack = []
            for ch in stripped:
                if escape_next:
                    escape_next = False
                    continue
                if ch == '\\' and in_string:
                    escape_next = True
                    continue
                if ch == '"':
                    in_string = not in_string
                    continue
                if in_string:
                    continue
                if ch in '{[':
                    stack.append(ch)
                if ch in '}]':
                    if stack:
                        stack.pop()
        else:
            return None

    # Remove trailing comma if present
    stripped = stripped.rstrip().rstrip(',')

    # Close remaining open brackets/braces
    closers = {'[': ']', '{': '}'}
    for opener in reversed(stack):
        stripped += closers.get(opener, '')

    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        return None


def validate_evidence(result: dict, raw_text: str) -> dict:
    """Validate that each issue's evidence actually appears in the meeting text.

    Issues with fabricated evidence (not found in raw_text) are removed.
    This prevents LLM hallucination of issues not grounded in the meeting.
    """
    if not isinstance(result.get("issues"), list):
        return result

    # Normalize whitespace for comparison
    normalized_text = "".join(raw_text.split())
    validated_issues = []
    removed_count = 0

    for issue in result["issues"]:
        evidence = issue.get("evidence", "")
        if not evidence:
            removed_count += 1
            continue

        # Normalize evidence whitespace for comparison
        normalized_evidence = "".join(evidence.split())

        # Check if a significant substring of the evidence exists in meeting text
        # Use sliding window: at least 15 consecutive chars must match
        found = False
        if len(normalized_evidence) >= 15:
            for start in range(0, len(normalized_evidence) - 14, 5):
                chunk = normalized_evidence[start:start + 20]
                if chunk in normalized_text:
                    found = True
                    break
        elif len(normalized_evidence) >= 8:
            found = normalized_evidence in normalized_text
        else:
            # Too short to validate meaningfully
            found = True

        if found:
            validated_issues.append(issue)
        else:
            removed_count += 1
            logger.warning(
                "Removed fabricated issue '%s': evidence not found in meeting text",
                issue.get("title", "unknown"),
            )

    if removed_count > 0:
        logger.info(
            "Evidence validation: kept %d issues, removed %d fabricated issues",
            len(validated_issues), removed_count,
        )

    # Re-number issue IDs
    for i, issue in enumerate(validated_issues):
        issue["id"] = f"I-{i + 1}"

    result["issues"] = validated_issues
    return result
