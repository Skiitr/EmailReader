"""
Deterministic rules for email triage.

Defines logic for identifying:
1. Flag Candidates (Strict): Actionable items requiring attention.
2. Surface Candidates (Lenient): Items worth a quick look even if not strictly flagged.
"""
import os
import re
from typing import Any

# User's email address to determine To vs Cc
M365_USER_EMAIL = os.environ.get("M365_USER_EMAIL", "").lower()

# Keywords indicating potential action/importance for offline mode or surface rules
ACTION_KEYWORDS = {
    "please",
    "can you",
    "need you to",
    "review",
    "approve",
    "confirm",
    "schedule",
    "deadline",
    "due by",
}

SURFACE_KEYWORDS = {
    "approval",
    "approve",
    "sign off",
    "quote ready",
    "ready for approval",
    "invoice",
    "agreement",
    "contract",
}

EXPIRY_KEYWORDS = {
    "expires in",
    "link expires",
    "access and download",
    "expiration",
}

AUTO_NOTIFICATION_PATTERNS = [
    "noreply",
    "no-reply",
    "notification",
    "alert",
    "automated",
]


def get_recipient_role(email: dict[str, Any]) -> str:
    """
    Determine if the user is in the 'to' or 'cc' list.
    
    Returns:
        "to", "cc", or "unknown"
    """
    if not M365_USER_EMAIL:
        return "unknown"
        
    to_list = [addr.lower() for addr in email.get("to", [])]
    if M365_USER_EMAIL in to_list:
        return "to"
        
    cc_list = [addr.lower() for addr in email.get("cc", [])]
    if M365_USER_EMAIL in cc_list:
        return "cc"
        
    return "unknown"


def is_auto_notification(email: dict[str, Any]) -> bool:
    """Check if email appears to be an automated notification."""
    sender_name = (email.get("from", {}).get("name") or "").lower()
    sender_email = (email.get("from", {}).get("email") or "").lower()
    subject = (email.get("subject") or "").lower()
    
    for pattern in AUTO_NOTIFICATION_PATTERNS:
        if pattern in sender_name or pattern in sender_email or pattern in subject:
            return True
    return False


def is_flag_candidate(
    email: dict[str, Any], ai_result: dict[str, Any] | None = None, min_conf: float = 0.75
) -> bool:
    """
    Determine if an email should be STRICTLY flagged for action.
    
    Args:
        email: Normalized email object.
        ai_result: Optional AI classification result.
        min_conf: Minimum confidence threshold for AI.
        
    Returns:
        True if the email is a flag candidate.
    """
    # 1. AI-driven logic (Primary)
    if ai_result:
        classification = ai_result.get("classification")
        confidence = ai_result.get("confidence", 0.0)
        asks_me = ai_result.get("asks_me_specifically", False)
        
        # Must be actionable, high confidence, and addressed to me
        if (
            classification in {"action_request", "direct_question", "meeting_request"}
            and confidence >= min_conf
            and asks_me
        ):
            return True
            
    # 2. Offline/Fallback logic (Secondary)
    # Conservative heuristic: Must be Direct TO + contain action verbs + NOT automated
    else:
        role = get_recipient_role(email)
        if role == "to" and not is_auto_notification(email):
            subject = (email.get("subject") or "").lower()
            body = (email.get("body_text") or "").lower()
            
            # Check for action keywords in subject or body
            content = subject + " " + body[:1000] # Check start of body
            if any(kw in content for kw in ACTION_KEYWORDS):
                return True
                
    return False


def is_surface_candidate(email: dict[str, Any], ai_result: dict[str, Any] | None = None) -> tuple[bool, str | None]:
    """
    Determine if an email is a SURFACE candidate (lenient "worth a look").
    
    Returns:
        Tuple (is_candidate, reason_string)
    """
    # If it's already a flag candidate, it's definitely a surface candidate
    # (Caller should handle deduplication, but logically it implies surface)
    
    role = get_recipient_role(email)
    subject = (email.get("subject") or "").lower()
    body = (email.get("body_text") or "").lower()
    is_high_importance = email.get("importance") == "high"
    has_attachments = email.get("has_attachments", False)
    
    # Exclude obvious noise regardless of other signals
    # (Unless it is strictly To me, sometimes automated alerts are important)
    if is_auto_notification(email) and role != "to":
        return False, None

    # Rule 1: Approval / Signature workflow
    # "To" + Attachments + Approval keywords in subject
    if role == "to" and has_attachments:
        if any(kw in subject for kw in SURFACE_KEYWORDS):
            return True, "Approval/Signature request with attachment"

    # Rule 2: High Importance addressed directly
    if role == "to" and is_high_importance:
        return True, "High importance direct message"

    # Rule 3: Expiry / Access Timeouts
    # "To" + Expiry keywords in body/preview
    content = body[:2000] + (email.get("body_preview") or "").lower()
    if role == "to" and any(kw in content for kw in EXPIRY_KEYWORDS):
        return True, "Time-sensitive access/expiry warning"

    return False, None
