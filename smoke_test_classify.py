#!/usr/bin/env python3
"""
Smoke tests for the AI classification module.

Tests the classification logic with mocked email data.
Requires OPENAI_API_KEY to be set.

Usage:
    python smoke_test_classify.py
"""
import json
import os
import sys


# Sample test emails
SAMPLE_ACTION_REQUEST = {
    "message_id": "test-001",
    "conversation_id": "conv-001",
    "internet_message_id": "<action@test.com>",
    "subject": "Please review the Q4 budget proposal",
    "from": {"name": "Sarah Chen", "email": "sarah.chen@company.com"},
    "to": ["me@company.com"],
    "cc": [],
    "received_at": "2026-01-31T10:00:00Z",
    "sent_at": "2026-01-31T09:59:00Z",
    "is_read": False,
    "web_link": "https://outlook.office365.com/owa/?ItemID=test-001",
    "has_attachments": True,
    "importance": "high",
    "body_preview": "Hi, I've attached the Q4 budget proposal. Could you please review it and provide feedback by Friday?",
    "body_text": """Hi,

I've attached the Q4 budget proposal for your review.

Could you please review it and provide your feedback by Friday (February 5th)? 
We need to finalize it before the board meeting next week.

Thanks,
Sarah""",
}

SAMPLE_FYI_NEWSLETTER = {
    "message_id": "test-002",
    "conversation_id": "conv-002",
    "internet_message_id": "<newsletter@test.com>",
    "subject": "Weekly Engineering Digest - January Week 5",
    "from": {"name": "Engineering Updates", "email": "noreply@company.com"},
    "to": ["engineering-all@company.com"],
    "cc": [],
    "received_at": "2026-01-31T08:00:00Z",
    "sent_at": "2026-01-31T07:59:00Z",
    "is_read": True,
    "web_link": "https://outlook.office365.com/owa/?ItemID=test-002",
    "has_attachments": False,
    "importance": "normal",
    "body_preview": "This week in engineering: New CI/CD pipeline deployed, Team offsite scheduled for March...",
    "body_text": """This week in engineering:

- New CI/CD pipeline deployed to production
- Team offsite scheduled for March 15-17
- Reminder: Code freeze begins February 10th

View in browser: https://internal.company.com/digest""",
}

SAMPLE_DIRECT_QUESTION = {
    "message_id": "test-003",
    "conversation_id": "conv-003",
    "internet_message_id": "<question@test.com>",
    "subject": "Quick question about the API integration",
    "from": {"name": "Alex Rivera", "email": "alex.r@partner.com"},
    "to": ["me@company.com"],
    "cc": ["team@company.com"],
    "received_at": "2026-01-31T14:30:00Z",
    "sent_at": "2026-01-31T14:29:00Z",
    "is_read": False,
    "web_link": "https://outlook.office365.com/owa/?ItemID=test-003",
    "has_attachments": False,
    "importance": "normal",
    "body_preview": "Hey, quick question - what's the rate limit on the new v2 API endpoints?",
    "body_text": """Hey,

Quick question - what's the rate limit on the new v2 API endpoints? 

We're planning our integration and need to know if we need to implement 
request throttling on our side.

Thanks!
Alex""",
}


def check_openai_key() -> bool:
    """Check if OpenAI API key is set."""
    if not os.environ.get("OPENAI_API_KEY"):
        print("=" * 60)
        print("OPENAI_API_KEY not set!")
        print("=" * 60)
        print()
        print("To run this smoke test, set your OpenAI API key:")
        print()
        print("  export OPENAI_API_KEY=sk-your-api-key-here")
        print()
        print("Get your API key from: https://platform.openai.com/api-keys")
        print()
        return False
    return True


def test_pre_filter() -> None:
    """Test the pre-filter logic without calling OpenAI."""
    print("=" * 60)
    print("TEST: Pre-filter logic (no API calls)")
    print("=" * 60)

    from classify import should_skip_email

    # Test empty body
    empty_msg = {
        "body_text": "",
        "body_preview": "",
        "subject": "Test",
        "from": {"email": "test@test.com"},
        "to": [],
    }
    should_skip, reason = should_skip_email(empty_msg)
    print(f"Empty body: skip={should_skip}, reason={reason}")
    assert should_skip and reason == "empty_body"

    # Test noise pattern
    noise_msg = {
        "body_text": "Your notification",
        "body_preview": "Your notification",
        "subject": "Automated notification",
        "from": {"email": "noreply@system.com"},
        "to": [],
    }
    should_skip, reason = should_skip_email(noise_msg)
    print(f"Noise pattern: skip={should_skip}, reason={reason}")
    assert should_skip and reason == "noise_pattern"

    # Test normal email
    should_skip, reason = should_skip_email(SAMPLE_ACTION_REQUEST)
    print(f"Normal email: skip={should_skip}, reason={reason}")
    assert not should_skip

    print()
    print("✓ Pre-filter tests passed")
    print()


def test_classify_email(email: dict, name: str) -> dict:
    """Test classifying a single email."""
    print("=" * 60)
    print(f"TEST: {name}")
    print("=" * 60)

    from classify import classify_email

    print(f"Subject: {email['subject']}")
    print(f"From: {email['from']['name']} <{email['from']['email']}>")
    print()
    print("Calling OpenAI...")

    result = classify_email(email, min_confidence=0.75)

    print()
    print("Result:")
    print(json.dumps(result, indent=2))
    print()

    return result


def test_compute_final_flag() -> None:
    """Test the deterministic flag computation."""
    print("=" * 60)
    print("TEST: compute_final_flag logic")
    print("=" * 60)

    from classify import compute_final_flag

    # Should flag: action_request + high confidence + asks me
    result1 = {
        "classification": "action_request",
        "confidence": 0.9,
        "asks_me_specifically": True,
    }
    flag1 = compute_final_flag(result1, 0.75)
    print(f"Action request, 0.9 conf, asks me: {flag1}")
    assert flag1

    # Should not flag: low confidence
    result2 = {
        "classification": "action_request",
        "confidence": 0.5,
        "asks_me_specifically": True,
    }
    flag2 = compute_final_flag(result2, 0.75)
    print(f"Action request, 0.5 conf, asks me: {flag2}")
    assert not flag2

    # Should not flag: FYI
    result3 = {
        "classification": "fyi",
        "confidence": 0.95,
        "asks_me_specifically": False,
    }
    flag3 = compute_final_flag(result3, 0.75)
    print(f"FYI, 0.95 conf, not asking me: {flag3}")
    assert not flag3

    # Should not flag: doesn't ask me specifically
    result4 = {
        "classification": "action_request",
        "confidence": 0.9,
        "asks_me_specifically": False,
    }
    flag4 = compute_final_flag(result4, 0.75)
    print(f"Action request, 0.9 conf, not asking me: {flag4}")
    assert not flag4

    print()
    print("✓ compute_final_flag tests passed")
    print()


def run_smoke_tests() -> None:
    """Run all smoke tests."""
    print()
    print("*" * 60)
    print("  AI CLASSIFICATION SMOKE TESTS")
    print("*" * 60)
    print()

    # Tests that don't require API key
    test_pre_filter()
    test_compute_final_flag()

    # Check if we can run API tests
    if not check_openai_key():
        print("Skipping API tests (no API key).")
        print()
        return

    # API tests
    results = []

    try:
        result1 = test_classify_email(SAMPLE_ACTION_REQUEST, "Action Request Email")
        results.append(("Action Request", result1))

        result2 = test_classify_email(SAMPLE_FYI_NEWSLETTER, "FYI Newsletter Email")
        results.append(("FYI Newsletter", result2))

        result3 = test_classify_email(SAMPLE_DIRECT_QUESTION, "Direct Question Email")
        results.append(("Direct Question", result3))

    except Exception as e:
        print(f"Error during API test: {e}")
        return

    # Summary
    print("=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print()

    for name, result in results:
        classification = result.get("classification", "unknown")
        confidence = result.get("confidence", 0)
        final_flag = result.get("final_should_flag", False)
        print(f"{name}:")
        print(f"  Classification: {classification}")
        print(f"  Confidence: {confidence:.0%}")
        print(f"  Final flag: {final_flag}")
        print()

    print("*" * 60)
    print("  ALL SMOKE TESTS COMPLETED")
    print("*" * 60)
    print()


if __name__ == "__main__":
    run_smoke_tests()
