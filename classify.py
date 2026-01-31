"""
Email classification logic using OpenAI.

Transforms normalized emails into classification requests and
processes AI responses to determine flagging decisions.
"""
import re
from typing import Any

from ai_client import get_ai_client
from settings import OPENAI_MAX_BODY_CHARS


# System prompt for the classifier
SYSTEM_PROMPT = """You are an email triage classifier that helps prioritize inbox messages.

Your job is to analyze emails and determine:
1. The type of email (action request, question, FYI, etc.)
2. Whether it requires the recipient's attention/action
3. Any deadlines or requested actions

IMPORTANT RULES:
- Only use the content provided. Do not infer project context from outside the email.
- Do not invent or hallucinate dates/deadlines that aren't explicitly stated.
- If unclear about classification or deadline, choose "unknown" with low confidence.
- Be conservative: only flag emails that genuinely need action.
- Consider whether the email is addressed directly TO the recipient vs just CC'd.
- Look for question marks, imperative verbs, and urgency indicators."""


# Patterns for detecting noise/automated emails
NOISE_PATTERNS = [
    re.compile(r"noreply|no-reply|do-not-reply|donotreply", re.IGNORECASE),
    re.compile(r"notification|automated|auto-generated", re.IGNORECASE),
    re.compile(r"newsletter|digest|weekly\s+update", re.IGNORECASE),
    re.compile(r"unsubscribe", re.IGNORECASE),
]


def should_skip_email(msg: dict[str, Any], user_email: str | None = None) -> tuple[bool, str]:
    """
    Determine if an email should skip AI classification.

    Args:
        msg: Normalized email message.
        user_email: Optional user's email address for To: field check.

    Returns:
        Tuple of (should_skip, reason).
    """
    body_text = msg.get("body_text") or ""
    body_preview = msg.get("body_preview") or ""
    subject = msg.get("subject") or ""
    from_email = (msg.get("from") or {}).get("email") or ""
    to_list = msg.get("to") or []

    # Skip if both body and preview are empty
    if not body_text.strip() and not body_preview.strip():
        return True, "empty_body"

    # Check for noise patterns in subject or sender
    for pattern in NOISE_PATTERNS:
        if pattern.search(subject) or pattern.search(from_email):
            # But don't skip if user is in To: field (directly addressed)
            if user_email and user_email.lower() in [e.lower() for e in to_list]:
                continue
            return True, "noise_pattern"

    return False, ""


def truncate_body(body_text: str | None, max_chars: int = OPENAI_MAX_BODY_CHARS) -> str:
    """
    Truncate body text to max characters.

    Args:
        body_text: The body text to truncate.
        max_chars: Maximum characters allowed.

    Returns:
        Truncated text with ellipsis if needed.
    """
    if not body_text:
        return ""
    if len(body_text) <= max_chars:
        return body_text
    return body_text[:max_chars - 3] + "..."


def build_user_prompt(msg: dict[str, Any]) -> str:
    """
    Build the user prompt from a normalized email.

    Args:
        msg: Normalized email message.

    Returns:
        Formatted prompt string for the AI.
    """
    from_info = msg.get("from") or {}
    from_name = from_info.get("name") or "Unknown"
    from_email = from_info.get("email") or "unknown@unknown.com"

    to_list = msg.get("to") or []
    cc_list = msg.get("cc") or []

    subject = msg.get("subject") or "(No Subject)"
    received_at = msg.get("received_at") or "Unknown"
    body_text = truncate_body(msg.get("body_text"))

    # Use preview as fallback if body is empty
    if not body_text.strip():
        body_text = truncate_body(msg.get("body_preview"))

    prompt = f"""Analyze this email:

FROM: {from_name} <{from_email}>
TO: {", ".join(to_list) if to_list else "Unknown"}
CC: {", ".join(cc_list) if cc_list else "None"}
SUBJECT: {subject}
RECEIVED: {received_at}

BODY:
{body_text if body_text else "(Empty)"}

Classify this email and determine if it requires the recipient's action."""

    return prompt


def compute_final_flag(
    ai_result: dict[str, Any],
    min_confidence: float = 0.75,
) -> bool:
    """
    Compute the final flagging decision based on AI output.

    Deterministic logic that overrides model's should_flag:
    - Flag if classification in {action_request, direct_question, meeting_request}
    - AND confidence >= min_confidence
    - AND asks_me_specifically is True

    Args:
        ai_result: The AI classification result.
        min_confidence: Minimum confidence threshold.

    Returns:
        True if email should be flagged.
    """
    classification = ai_result.get("classification", "unknown")
    confidence = ai_result.get("confidence", 0.0)
    asks_me = ai_result.get("asks_me_specifically", False)

    flaggable_types = {"action_request", "direct_question", "meeting_request"}

    return (
        classification in flaggable_types
        and confidence >= min_confidence
        and asks_me
    )


def classify_email(
    msg: dict[str, Any],
    min_confidence: float = 0.75,
    user_email: str | None = None,
) -> dict[str, Any]:
    """
    Classify a normalized email using AI.

    Args:
        msg: Normalized email message.
        min_confidence: Minimum confidence for flagging.
        user_email: Optional user's email for skip logic.

    Returns:
        AI classification result with final_should_flag added.
    """
    # Check if we should skip this email
    should_skip, skip_reason = should_skip_email(msg, user_email)
    if should_skip:
        return {
            "classification": "unknown" if skip_reason == "empty_body" else "spam_or_noise",
            "should_flag": False,
            "confidence": 0.0,
            "reason": f"Skipped: {skip_reason}",
            "summary": "Skipped by pre-filter",
            "requested_action": None,
            "deadline_iso": None,
            "asks_me_specifically": False,
            "signals": {
                "to_vs_cc": "unknown",
                "contains_question": False,
                "contains_imperative": False,
                "mentions_deadline": False,
            },
            "model_should_flag": False,
            "final_should_flag": False,
            "skipped": True,
            "skip_reason": skip_reason,
        }

    # Build prompt and call AI
    user_prompt = build_user_prompt(msg)
    client = get_ai_client()

    try:
        ai_result = client.classify_email(SYSTEM_PROMPT, user_prompt)
    except Exception as e:
        # Return error result if AI call fails
        return {
            "classification": "unknown",
            "should_flag": False,
            "confidence": 0.0,
            "reason": f"AI error: {str(e)[:100]}",
            "summary": "Classification failed",
            "requested_action": None,
            "deadline_iso": None,
            "asks_me_specifically": False,
            "signals": {
                "to_vs_cc": "unknown",
                "contains_question": False,
                "contains_imperative": False,
                "mentions_deadline": False,
            },
            "model_should_flag": False,
            "final_should_flag": False,
            "error": str(e),
        }

    # Store the model's raw flag decision
    ai_result["model_should_flag"] = ai_result.get("should_flag", False)

    # Compute our deterministic final flag
    ai_result["final_should_flag"] = compute_final_flag(ai_result, min_confidence)

    return ai_result


def classify_emails(
    messages: list[dict[str, Any]],
    max_ai: int = 50,
    min_confidence: float = 0.75,
    user_email: str | None = None,
) -> list[dict[str, Any]]:
    """
    Classify a list of normalized emails.

    Args:
        messages: List of normalized email messages.
        max_ai: Maximum number of emails to send to AI.
        min_confidence: Minimum confidence for flagging.
        user_email: Optional user's email for skip logic.

    Returns:
        List of emails with AI classification added under "ai" key.
    """
    enriched = []
    ai_count = 0

    for msg in messages:
        # Copy the message to avoid mutation
        enriched_msg = dict(msg)

        # Check if we've hit the AI limit
        if ai_count >= max_ai:
            enriched_msg["ai"] = {
                "classification": "unknown",
                "should_flag": False,
                "confidence": 0.0,
                "reason": "Skipped: max_ai limit reached",
                "summary": "Skipped",
                "requested_action": None,
                "deadline_iso": None,
                "asks_me_specifically": False,
                "signals": {
                    "to_vs_cc": "unknown",
                    "contains_question": False,
                    "contains_imperative": False,
                    "mentions_deadline": False,
                },
                "model_should_flag": False,
                "final_should_flag": False,
                "skipped": True,
                "skip_reason": "max_ai_limit",
            }
        else:
            # Classify this email
            ai_result = classify_email(msg, min_confidence, user_email)
            enriched_msg["ai"] = ai_result

            # Only count toward limit if we actually called the AI
            if not ai_result.get("skipped"):
                ai_count += 1

        enriched.append(enriched_msg)

    return enriched


def generate_report(
    enriched_messages: list[dict[str, Any]],
    top_n: int = 10,
) -> str:
    """
    Generate a markdown report of flagged emails.

    Args:
        enriched_messages: List of emails with AI classification.
        top_n: Number of top candidates to include.

    Returns:
        Markdown formatted report.
    """
    # Sort by confidence (descending) and filter to flagged
    flagged = [
        msg for msg in enriched_messages
        if msg.get("ai", {}).get("final_should_flag")
    ]
    flagged.sort(key=lambda m: m.get("ai", {}).get("confidence", 0), reverse=True)

    # Take top N
    top_flagged = flagged[:top_n]

    # Build report
    lines = [
        "# Email Triage Report",
        "",
        f"**Total emails processed:** {len(enriched_messages)}",
        f"**Flagged for action:** {len(flagged)}",
        "",
        "---",
        "",
        "## Top Flagged Emails",
        "",
    ]

    if not top_flagged:
        lines.append("*No emails flagged for action.*")
    else:
        for i, msg in enumerate(top_flagged, 1):
            ai = msg.get("ai", {})
            from_info = msg.get("from", {})
            sender = from_info.get("name") or from_info.get("email") or "Unknown"

            lines.extend([
                f"### {i}. {msg.get('subject', '(No Subject)')}",
                "",
                f"- **From:** {sender}",
                f"- **Received:** {msg.get('received_at', 'Unknown')}",
                f"- **Classification:** {ai.get('classification', 'unknown')}",
                f"- **Confidence:** {ai.get('confidence', 0):.0%}",
                f"- **Summary:** {ai.get('summary', 'N/A')}",
            ])

            if ai.get("requested_action"):
                lines.append(f"- **Action:** {ai['requested_action']}")
            if ai.get("deadline_iso"):
                lines.append(f"- **Deadline:** {ai['deadline_iso']}")

            lines.extend(["", "---", ""])

    return "\n".join(lines)


def get_summary_stats(enriched_messages: list[dict[str, Any]]) -> dict[str, Any]:
    """
    Get summary statistics for the classification run.

    Args:
        enriched_messages: List of emails with AI classification.

    Returns:
        Dictionary of summary statistics.
    """
    total = len(enriched_messages)
    flagged = sum(1 for m in enriched_messages if m.get("ai", {}).get("final_should_flag"))
    skipped = sum(1 for m in enriched_messages if m.get("ai", {}).get("skipped"))
    processed = total - skipped
    errors = sum(1 for m in enriched_messages if m.get("ai", {}).get("error"))

    return {
        "total": total,
        "processed_by_ai": processed,
        "skipped": skipped,
        "flagged": flagged,
        "errors": errors,
    }
