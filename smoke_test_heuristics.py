#!/usr/bin/env python3
"""
Smoke tests for deterministic heuristic triage.
"""
from rules import triage_email


def run() -> None:
    actionable = {
        "message_id": "s1",
        "subject": "Please approve the attached agreement by EOD",
        "from": {"name": "Legal", "email": "legal@company.com"},
        "to": ["your.name@company.com"],
        "cc": [],
        "received_at": "2026-02-15T12:00:00Z",
        "is_read": False,
        "has_attachments": True,
        "importance": "high",
        "body_preview": "Need your approval by EOD",
        "body_text": "Please approve the attached agreement by EOD today.",
    }
    noise = {
        "message_id": "s2",
        "subject": "Weekly digest newsletter",
        "from": {"name": "Updates", "email": "noreply@company.com"},
        "to": ["engineering-all@company.com"],
        "cc": [],
        "received_at": "2026-02-15T10:00:00Z",
        "is_read": True,
        "has_attachments": False,
        "importance": "normal",
        "body_preview": "FYI only",
        "body_text": "FYI only. Weekly newsletter. No action needed.",
    }

    r1 = triage_email(actionable, ai_result=None)
    r2 = triage_email(noise, ai_result=None)

    assert r1["decision"] in {"flag", "surface"}
    assert r1["priority_score"] >= 40
    assert r2["decision"] == "ignore"
    assert r2["priority_score"] < 40
    print("Heuristic smoke tests passed.")


if __name__ == "__main__":
    run()
