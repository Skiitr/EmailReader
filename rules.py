"""
Deterministic rules and policy wrappers for email triage.

This module combines:
1) AI-derived strict flag signals (when available)
2) deterministic heuristic scoring (primary for --no-ai)
"""
from typing import Any
from typing import Optional

from heuristics import evaluate_email


def _ai_should_flag(ai_result: Optional[dict[str, Any]], min_conf: float) -> bool:
    if not ai_result:
        return False
    classification = ai_result.get("classification")
    confidence = ai_result.get("confidence", 0.0)
    asks_me = ai_result.get("asks_me_specifically", False)
    return (
        classification in {"action_request", "direct_question", "meeting_request"}
        and confidence >= min_conf
        and asks_me
    )


def triage_email(
    email: dict[str, Any],
    ai_result: Optional[dict[str, Any]] = None,
    min_conf: float = 0.75,
    sender_profiles: Optional[dict[str, Any]] = None,
    user_email: Optional[str] = None,
) -> dict[str, Any]:
    """
    Produce triage decision with score and explanation.

    Returns:
        Dict with decision, priority_score, reason, score_breakdown, features, source.
    """
    heuristic = evaluate_email(
        email,
        sender_profiles=sender_profiles,
        user_email=user_email,
    )
    features = heuristic.get("features", {})
    score = int(heuristic.get("priority_score", 0))

    if _ai_should_flag(ai_result, min_conf):
        heuristic["decision"] = "flag"
        heuristic["priority_score"] = max(heuristic.get("priority_score", 0), 95)
        heuristic["reason"] = (
            f"AI: {ai_result.get('classification')} "
            f"({ai_result.get('confidence', 0):.0%}) + {heuristic.get('reason', '')}"
        ).strip()
        heuristic["source"] = "ai+heuristic"
    elif ai_result:
        heuristic["source"] = "heuristic_with_ai_context"

    # Policy adjustments for deterministic no-AI behavior.
    # 1) CC-only messages are usually surface unless explicitly adding me to a thread.
    if features.get("recipient_role") == "cc" and not features.get("thread_addition_cc_me"):
        if heuristic["decision"] == "flag":
            heuristic["decision"] = "surface"

    # 2) Broad TO lists without direct salutation should generally be surfaced, not flagged.
    if (
        features.get("recipient_role") == "to"
        and int(features.get("to_count", 0)) >= 3
        and not features.get("direct_salutation")
        and not features.get("last_request_phrase")
        and int(features.get("action_phrase_strong_hits", 0)) == 0
        and heuristic["decision"] == "flag"
    ):
        heuristic["decision"] = "surface"

    # 2b) Small-group question without direct salutation is usually surface triage.
    if (
        features.get("recipient_role") == "to"
        and features.get("small_group_question")
        and not features.get("direct_salutation")
        and not features.get("deadline_present")
        and not features.get("last_request_phrase")
        and int(features.get("action_phrase_strong_hits", 0)) == 0
        and heuristic["decision"] == "flag"
    ):
        heuristic["decision"] = "surface"

    # 3) Direct salutation to me with ask-like language is strong action signal.
    if (
        features.get("recipient_role") == "to"
        and features.get("direct_salutation")
        and (
            features.get("imperative_present")
            or features.get("question_present")
            or int(features.get("action_phrase_strong_hits", 0)) > 0
            or int(features.get("action_phrase_weak_hits", 0)) > 0
        )
        and score >= 55
    ):
        heuristic["decision"] = "flag"

    # 3b) Personal salutation to me in a small recipient set is actionable.
    if (
        features.get("direct_salutation_to_me")
        and int(features.get("to_count", 0)) <= 3
        and score >= 40
    ):
        heuristic["decision"] = "flag"

    # 4) Explicitly adding me on CC to a thread should be promoted.
    if features.get("thread_addition_cc_me") and score >= 40:
        heuristic["decision"] = "flag"

    return heuristic


def is_flag_candidate(
    email: dict[str, Any],
    ai_result: Optional[dict[str, Any]] = None,
    min_conf: float = 0.75,
) -> bool:
    return triage_email(email, ai_result=ai_result, min_conf=min_conf)["decision"] == "flag"


def is_surface_candidate(
    email: dict[str, Any],
    ai_result: Optional[dict[str, Any]] = None,
) -> tuple[bool, Optional[str]]:
    triage = triage_email(email, ai_result=ai_result)
    is_candidate = triage["decision"] in {"flag", "surface"}
    return is_candidate, triage.get("reason")
