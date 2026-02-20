"""
Deterministic heuristic scoring engine for email triage.

This module is intentionally split into:
1) signal extraction
2) scoring policy application
3) sender-memory loading/updating
"""
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

from settings import (
    HEURISTIC_FLAG_THRESHOLD,
    HEURISTIC_PROFILE_PATH,
    HEURISTIC_SURFACE_THRESHOLD,
    HEURISTIC_WEIGHTS,
    M365_USER_EMAIL,
    M365_VIP_SENDERS,
)


ACTION_STRONG_PATTERNS = [
    re.compile(r"\bplease\s+(review|approve|confirm|respond|send|share)\b", re.IGNORECASE),
    re.compile(r"\b(can|could|would)\s+you\b", re.IGNORECASE),
    re.compile(r"\bneed\s+you\s+to\b", re.IGNORECASE),
    re.compile(r"\byour\s+(approval|feedback|input|decision)\b", re.IGNORECASE),
    re.compile(r"\blast request\b", re.IGNORECASE),
]

ACTION_WEAK_PATTERNS = [
    re.compile(r"\breview\b", re.IGNORECASE),
    re.compile(r"\bapprove\b", re.IGNORECASE),
    re.compile(r"\bconfirm\b", re.IGNORECASE),
    re.compile(r"\bschedule\b", re.IGNORECASE),
]

IMPERATIVE_PATTERNS = [
    re.compile(r"\bplease\b", re.IGNORECASE),
    re.compile(r"\bkindly\b", re.IGNORECASE),
    re.compile(r"\baction required\b", re.IGNORECASE),
    re.compile(r"\blet'?s\b", re.IGNORECASE),
    re.compile(r"\bdo it\b", re.IGNORECASE),
]

DEADLINE_PATTERNS = [
    re.compile(r"\bby\s+(eod|cob|end of day|tomorrow|today|monday|tuesday|wednesday|thursday|friday)\b", re.IGNORECASE),
    re.compile(r"\bdeadline\b", re.IGNORECASE),
    re.compile(r"\bdue\s+(by|on)?\b", re.IGNORECASE),
    re.compile(r"\bexpires?\b", re.IGNORECASE),
    re.compile(r"\b\d{4}-\d{2}-\d{2}\b"),
]

URGENCY_PATTERNS = [
    re.compile(r"\burgent\b", re.IGNORECASE),
    re.compile(r"\basap\b", re.IGNORECASE),
    re.compile(r"\bhigh priority\b", re.IGNORECASE),
    re.compile(r"\btime[- ]sensitive\b", re.IGNORECASE),
]

APPROVAL_PATTERNS = [
    re.compile(r"\b(ready for approval|sign off|signature request|please sign)\b", re.IGNORECASE),
]

CONTRACT_FINANCE_PATTERNS = [
    re.compile(r"\b(invoice|agreement|contract|quote|purchase order|po)\b", re.IGNORECASE),
]

FYI_PATTERNS = [
    re.compile(r"\bfyi\b", re.IGNORECASE),
    re.compile(r"\bfor your information\b", re.IGNORECASE),
    re.compile(r"\bfor awareness\b", re.IGNORECASE),
]

NEWSLETTER_PATTERNS = [
    re.compile(r"\b(newsletter|digest|weekly update|view in browser)\b", re.IGNORECASE),
]

NO_ACTION_PATTERNS = [
    re.compile(r"\bno action needed\b", re.IGNORECASE),
    re.compile(r"\bno response required\b", re.IGNORECASE),
    re.compile(r"\bfyi only\b", re.IGNORECASE),
]

DIRECT_SALUTATION_PATTERN = re.compile(
    r"^\s*(dan|dan/ben|dan and ben)\s*[,;:]",
    re.IGNORECASE,
)

THREAD_ADDITION_PATTERN = re.compile(
    r"\badding\s+.+\s+to\s+the\s+(conversation|thread)\b",
    re.IGNORECASE,
)

AUTOMATION_PATTERNS = [
    re.compile(r"noreply|no-reply|do-not-reply|donotreply", re.IGNORECASE),
    re.compile(r"notification|automated|auto-generated|alert", re.IGNORECASE),
]


def _sender_email(email: dict[str, Any]) -> str:
    return ((email.get("from") or {}).get("email") or "").strip().lower()


def _sender_domain(sender_email: str) -> str:
    if "@" not in sender_email:
        return ""
    return sender_email.split("@", 1)[1]


def _user_domain(user_email: str) -> str:
    if "@" not in user_email:
        return ""
    return user_email.split("@", 1)[1]


def _recipient_role(email: dict[str, Any], user_email: str) -> str:
    if not user_email:
        return "unknown"
    to_list = [a.lower() for a in email.get("to", [])]
    cc_list = [a.lower() for a in email.get("cc", [])]
    if user_email in to_list:
        return "to"
    if user_email in cc_list:
        return "cc"
    return "unknown"


def _safe_text(email: dict[str, Any]) -> str:
    subject = email.get("subject") or ""
    body = email.get("body_text") or ""
    preview = email.get("body_preview") or ""
    return f"{subject}\n{body}\n{preview}"


def _is_recent(received_at: Optional[str], hours: int = 48) -> bool:
    if not received_at:
        return False
    try:
        ts = datetime.fromisoformat(received_at.replace("Z", "+00:00"))
    except ValueError:
        return False
    now = datetime.now(timezone.utc)
    return now - ts <= timedelta(hours=hours)


def extract_features(
    email: dict[str, Any],
    user_email: Optional[str] = None,
    vip_senders: Optional[set[str]] = None,
) -> dict[str, Any]:
    user_email = (user_email or M365_USER_EMAIL).lower()
    vip_senders = vip_senders if vip_senders is not None else M365_VIP_SENDERS

    sender = _sender_email(email)
    sender_domain = _sender_domain(sender)
    internal_domain = _user_domain(user_email)
    text = _safe_text(email)
    role = _recipient_role(email, user_email)
    subject = (email.get("subject") or "").lower()
    total_recipients = len(email.get("to", []) or []) + len(email.get("cc", []) or [])
    to_count = len(email.get("to", []) or [])
    body_text = (email.get("body_text") or email.get("body_preview") or "").strip()

    features: dict[str, Any] = {
        "recipient_role": role,
        "to_count": to_count,
        "is_unread": not bool(email.get("is_read", False)),
        "is_high_importance": (email.get("importance") == "high"),
        "has_attachments": bool(email.get("has_attachments", False)),
        "is_external_sender": bool(sender_domain and internal_domain and sender_domain != internal_domain),
        "is_internal_sender": bool(sender_domain and internal_domain and sender_domain == internal_domain),
        "is_vip_sender": sender in vip_senders,
        "is_noreply_sender": bool(re.search(r"(noreply|no-reply|donotreply|do-not-reply)", sender)),
        "automation_pattern_hit": any(p.search(sender) or p.search(subject) for p in AUTOMATION_PATTERNS),
        "action_phrase_strong_hits": sum(1 for p in ACTION_STRONG_PATTERNS if p.search(text)),
        "action_phrase_weak_hits": sum(1 for p in ACTION_WEAK_PATTERNS if p.search(text)),
        "direct_salutation": bool(DIRECT_SALUTATION_PATTERN.search(body_text[:80])),
        "direct_salutation_to_me": False,
        "small_group_question": ("?" in text and 0 < total_recipients <= 3),
        "thread_addition": bool(THREAD_ADDITION_PATTERN.search(text)),
        "thread_addition_cc_me": False,
        "multi_to_no_salutation": False,
        "last_request_phrase": bool(re.search(r"\blast request\b", text, re.IGNORECASE)),
        "question_present": ("?" in text),
        "imperative_present": any(p.search(text) for p in IMPERATIVE_PATTERNS),
        "deadline_present": any(p.search(text) for p in DEADLINE_PATTERNS),
        "urgency_present": any(p.search(text) for p in URGENCY_PATTERNS),
        "approval_workflow_present": any(p.search(text) for p in APPROVAL_PATTERNS),
        "contract_finance_present": any(p.search(text) for p in CONTRACT_FINANCE_PATTERNS),
        "fyi_present": any(p.search(text) for p in FYI_PATTERNS),
        "newsletter_present": any(p.search(text) for p in NEWSLETTER_PATTERNS),
        "no_action_present": any(p.search(text) for p in NO_ACTION_PATTERNS),
        "is_recent": _is_recent(email.get("received_at")),
        "sender_email": sender,
    }
    features["direct_salutation_to_me"] = bool(
        features["direct_salutation"] and role == "to"
    )
    features["thread_addition_cc_me"] = bool(
        features["thread_addition"] and role == "cc"
    )
    features["multi_to_no_salutation"] = bool(
        role == "to" and to_count >= 3 and not features["direct_salutation"]
    )
    return features


def _bounded_sender_prior(
    sender_email: str,
    profiles: Optional[dict[str, Any]],
    weights: dict[str, int],
) -> tuple[int, str]:
    if not sender_email or not profiles:
        return 0, "sender_history"
    senders = profiles.get("senders", {})
    rec = senders.get(sender_email)
    if not rec:
        return 0, "sender_history"

    seen = int(rec.get("seen", 0))
    if seen < 3:
        return 0, "sender_history"

    responded = int(rec.get("flag_count", 0)) + int(rec.get("surface_count", 0))
    rate = responded / seen if seen else 0.0
    raw = int(round((rate - 0.5) * 24))
    max_boost = int(weights.get("sender_history_max_boost", 12))
    max_penalty = int(weights.get("sender_history_max_penalty", -12))
    bounded = max(max_penalty, min(max_boost, raw))
    return bounded, "sender_history"


def score_features(
    features: dict[str, Any],
    weights: Optional[dict[str, int]] = None,
    sender_profiles: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    weights = weights if weights is not None else HEURISTIC_WEIGHTS
    breakdown: list[dict[str, Any]] = []
    score = 0

    def add(signal: str, points: int, when: bool = True) -> None:
        nonlocal score
        if not when or points == 0:
            return
        score += points
        breakdown.append({"signal": signal, "points": points})

    role = features.get("recipient_role")
    add("to_me", weights.get("to_me", 0), role == "to")
    add("cc_me", weights.get("cc_me", 0), role == "cc")
    add("unknown_recipient_role", weights.get("unknown_recipient_role", 0), role == "unknown")

    add("unread", weights.get("unread", 0), features.get("is_unread"))
    add("importance_high", weights.get("importance_high", 0), features.get("is_high_importance"))
    add("has_attachments", weights.get("has_attachments", 0), features.get("has_attachments"))
    add("external_sender", weights.get("external_sender", 0), features.get("is_external_sender"))
    add("internal_sender", weights.get("internal_sender", 0), features.get("is_internal_sender"))
    add("vip_sender", weights.get("vip_sender", 0), features.get("is_vip_sender"))
    add("noreply_sender", weights.get("noreply_sender", 0), features.get("is_noreply_sender"))
    add("automation_pattern", weights.get("automation_pattern", 0), features.get("automation_pattern_hit"))

    if features.get("action_phrase_strong_hits", 0) > 0:
        add("action_phrase_strong", weights.get("action_phrase_strong", 0))
    elif features.get("action_phrase_weak_hits", 0) > 0:
        add("action_phrase_weak", weights.get("action_phrase_weak", 0))

    add("direct_salutation", weights.get("direct_salutation", 0), features.get("direct_salutation"))
    add(
        "direct_salutation_to_me",
        weights.get("direct_salutation_to_me", 0),
        features.get("direct_salutation_to_me"),
    )
    add("small_group_question", weights.get("small_group_question", 0), features.get("small_group_question"))
    add("thread_addition", weights.get("thread_addition", 0), features.get("thread_addition"))
    add(
        "thread_addition_cc_me",
        weights.get("thread_addition_cc_me", 0),
        features.get("thread_addition_cc_me"),
    )
    add(
        "multi_to_no_salutation",
        weights.get("multi_to_no_salutation", 0),
        features.get("multi_to_no_salutation"),
    )
    add("last_request_phrase", weights.get("last_request_phrase", 0), features.get("last_request_phrase"))
    add("question_present", weights.get("question_present", 0), features.get("question_present"))
    add("imperative_present", weights.get("imperative_present", 0), features.get("imperative_present"))
    add("deadline_present", weights.get("deadline_present", 0), features.get("deadline_present"))
    add("urgency_present", weights.get("urgency_present", 0), features.get("urgency_present"))
    add("approval_workflow", weights.get("approval_workflow", 0), features.get("approval_workflow_present"))
    add("contract_finance_signal", weights.get("contract_finance_signal", 0), features.get("contract_finance_present"))

    add("fyi_phrase", weights.get("fyi_phrase", 0), features.get("fyi_present"))
    add("newsletter_phrase", weights.get("newsletter_phrase", 0), features.get("newsletter_present"))
    add("no_action_phrase", weights.get("no_action_phrase", 0), features.get("no_action_present"))

    prior_points, prior_name = _bounded_sender_prior(
        features.get("sender_email", ""),
        sender_profiles,
        weights,
    )
    add(prior_name, prior_points, True)

    score = max(0, min(100, score))
    return {"score": score, "breakdown": breakdown}


def classify_score(
    score: int,
    flag_threshold: int = HEURISTIC_FLAG_THRESHOLD,
    surface_threshold: int = HEURISTIC_SURFACE_THRESHOLD,
) -> str:
    if score >= flag_threshold:
        return "flag"
    if score >= surface_threshold:
        return "surface"
    return "ignore"


def summarize_reasons(breakdown: list[dict[str, Any]], top_n: int = 3) -> str:
    positive = [b for b in breakdown if b["points"] > 0]
    positive.sort(key=lambda x: x["points"], reverse=True)
    if not positive:
        return "Low-signal message"
    picks = positive[:top_n]
    return ", ".join(f"{p['signal']} (+{p['points']})" for p in picks)


def evaluate_email(
    email: dict[str, Any],
    sender_profiles: Optional[dict[str, Any]] = None,
    user_email: Optional[str] = None,
) -> dict[str, Any]:
    features = extract_features(email, user_email=user_email)
    scoring = score_features(features, sender_profiles=sender_profiles)
    score = int(scoring["score"])
    decision = classify_score(score)
    reason = summarize_reasons(scoring["breakdown"])
    return {
        "decision": decision,
        "priority_score": score,
        "reason": reason,
        "score_breakdown": scoring["breakdown"],
        "features": features,
        "source": "heuristic",
    }


def infer_user_email(messages: list[dict[str, Any]]) -> Optional[str]:
    list_like = re.compile(r"(^|[._-])(all|team|group|list|noreply)($|[._-])", re.IGNORECASE)
    counts: dict[str, int] = {}
    for msg in messages:
        for field in ("to", "cc"):
            for addr in msg.get(field, []) or []:
                a = (addr or "").strip().lower()
                if not a or "@" not in a:
                    continue
                local = a.split("@", 1)[0]
                if list_like.search(local):
                    continue
                counts[a] = counts.get(a, 0) + 1
    if not counts:
        return None
    return max(counts.items(), key=lambda kv: kv[1])[0]


def load_sender_profiles(path: Optional[Path] = None) -> dict[str, Any]:
    path = path or HEURISTIC_PROFILE_PATH
    if not path.exists():
        return {"senders": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"senders": {}}
    if not isinstance(data, dict) or "senders" not in data:
        return {"senders": {}}
    return data


def save_sender_profiles(profiles: dict[str, Any], path: Optional[Path] = None) -> None:
    path = path or HEURISTIC_PROFILE_PATH
    try:
        path.write_text(json.dumps(profiles, indent=2, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass


def update_sender_profiles(
    profiles: dict[str, Any],
    evaluated_messages: list[dict[str, Any]],
) -> dict[str, Any]:
    senders = profiles.setdefault("senders", {})
    now_iso = datetime.now(timezone.utc).isoformat()

    for msg in evaluated_messages:
        sender = _sender_email(msg)
        if not sender:
            continue
        triage = msg.get("triage") or {}
        decision = triage.get("decision", "ignore")
        rec = senders.setdefault(
            sender,
            {"seen": 0, "flag_count": 0, "surface_count": 0, "ignore_count": 0, "last_seen": None},
        )
        rec["seen"] = int(rec.get("seen", 0)) + 1
        if decision == "flag":
            rec["flag_count"] = int(rec.get("flag_count", 0)) + 1
        elif decision == "surface":
            rec["surface_count"] = int(rec.get("surface_count", 0)) + 1
        else:
            rec["ignore_count"] = int(rec.get("ignore_count", 0)) + 1
        rec["last_seen"] = now_iso

    return profiles
