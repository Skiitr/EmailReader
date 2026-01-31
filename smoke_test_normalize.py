#!/usr/bin/env python3
"""
Smoke tests for the normalize module.

Runs basic validation with hardcoded sample messages to verify
the normalization logic works correctly. No external test framework required.

Usage:
    python smoke_test_normalize.py
"""
import json
from normalize import (
    clean_email_body,
    normalize_message,
    normalize_messages,
    strip_html_tags,
)


# Sample test messages simulating Graph API responses
SAMPLE_HTML_MESSAGE = {
    "id": "AAMkAGI2THVSAAA=",
    "conversationId": "AAQkAGI2THVSAAA=",
    "internetMessageId": "<abc123@mail.example.com>",
    "subject": "Weekly Team Update",
    "from": {
        "emailAddress": {
            "name": "John Doe",
            "address": "john.doe@example.com",
        }
    },
    "toRecipients": [
        {"emailAddress": {"name": "Jane Smith", "address": "jane.smith@example.com"}},
        {"emailAddress": {"name": "Bob Wilson", "address": "bob.wilson@example.com"}},
    ],
    "ccRecipients": [
        {"emailAddress": {"name": "Team List", "address": "team@example.com"}},
    ],
    "receivedDateTime": "2026-01-31T14:30:00Z",
    "sentDateTime": "2026-01-31T14:29:55Z",
    "isRead": False,
    "webLink": "https://outlook.office365.com/owa/?ItemID=AAMkAGI2THVSAAA%3D",
    "hasAttachments": True,
    "importance": "normal",
    "bodyPreview": "Hi team, Here's our weekly update for this week...",
    "body": {
        "contentType": "html",
        "content": """
<html>
<head><style>body { font-family: Arial; }</style></head>
<body>
<p>Hi team,</p>
<p>Here's our weekly update for this week:</p>
<ul>
<li>Project Alpha is on track</li>
<li>New feature deployment scheduled for Friday</li>
</ul>
<p>Best regards,<br>John</p>
<div>
<p>-- </p>
<p>John Doe<br>Senior Engineer<br>Example Corp</p>
</div>
</body>
</html>
""",
    },
}

SAMPLE_TEXT_MESSAGE = {
    "id": "AAMkAGI2PLAINTEXT=",
    "conversationId": "AAQkAGI2PLAINTEXT=",
    "internetMessageId": "<def456@mail.example.com>",
    "subject": "Re: Quick Question",
    "from": {
        "emailAddress": {
            "name": "Alice Johnson",
            "address": "alice@example.com",
        }
    },
    "toRecipients": [
        {"emailAddress": {"name": "John Doe", "address": "john.doe@example.com"}},
    ],
    "ccRecipients": [],
    "receivedDateTime": "2026-01-31T10:15:00Z",
    "sentDateTime": "2026-01-31T10:14:50Z",
    "isRead": True,
    "webLink": "https://outlook.office365.com/owa/?ItemID=AAMkAGI2PLAINTEXT%3D",
    "hasAttachments": False,
    "importance": "high",
    "bodyPreview": "Yes, I can help with that! Let me know when you're free.",
    "body": {
        "contentType": "text",
        "content": """Yes, I can help with that! Let me know when you're free.

Best,
Alice

On Wed, Jan 30, 2026 at 3:45 PM John Doe <john.doe@example.com> wrote:

> Hi Alice,
> 
> Do you have time to review the proposal?
> 
> Thanks,
> John
""",
    },
}

SAMPLE_MINIMAL_MESSAGE = {
    "id": "AAMkAGI2MINIMAL=",
    "isRead": False,
    # Missing most optional fields
}


def test_strip_html_tags() -> None:
    """Test HTML to plain text conversion."""
    print("=" * 60)
    print("TEST: strip_html_tags")
    print("=" * 60)

    test_html = "<p>Hello <b>world</b>!</p><br><div>New line here.</div>"
    result = strip_html_tags(test_html)
    print(f"Input:  {test_html!r}")
    print(f"Output: {result!r}")
    print()

    # Test entity handling
    entity_html = "<p>Price: &lt;$100&gt; &amp; free shipping!</p>"
    result2 = strip_html_tags(entity_html)
    print(f"Entity test input:  {entity_html!r}")
    print(f"Entity test output: {result2!r}")
    print()


def test_clean_email_body() -> None:
    """Test email body cleaning."""
    print("=" * 60)
    print("TEST: clean_email_body")
    print("=" * 60)

    # Test with reply content
    body_with_reply = """Thanks for the update!

I'll review it today.

On Mon, Jan 30, 2026 at 10:00 AM John <john@example.com> wrote:
> Here's the document.
> Let me know if you have questions.
"""
    result = clean_email_body(body_with_reply)
    print("Input with reply marker:")
    print(body_with_reply)
    print("\nCleaned output:")
    print(result)
    print()

    # Test with signature
    body_with_sig = """Meeting confirmed for 3pm.

-- 
John Doe
Senior Engineer
555-1234
"""
    result2 = clean_email_body(body_with_sig)
    print("Input with signature:")
    print(body_with_sig)
    print("\nCleaned output:")
    print(result2)
    print()


def test_normalize_message() -> None:
    """Test single message normalization."""
    print("=" * 60)
    print("TEST: normalize_message (HTML body)")
    print("=" * 60)

    result = normalize_message(SAMPLE_HTML_MESSAGE)
    print(json.dumps(result, indent=2))
    print()

    print("=" * 60)
    print("TEST: normalize_message (text body with reply)")
    print("=" * 60)

    result2 = normalize_message(SAMPLE_TEXT_MESSAGE)
    print(json.dumps(result2, indent=2))
    print()

    print("=" * 60)
    print("TEST: normalize_message (minimal/missing fields)")
    print("=" * 60)

    result3 = normalize_message(SAMPLE_MINIMAL_MESSAGE)
    print(json.dumps(result3, indent=2))
    print()

    print("=" * 60)
    print("TEST: normalize_message (include_body=False)")
    print("=" * 60)

    result4 = normalize_message(SAMPLE_HTML_MESSAGE, include_body=False)
    print(f"body_text is None: {result4['body_text'] is None}")
    print()


def test_normalize_messages() -> None:
    """Test batch message normalization."""
    print("=" * 60)
    print("TEST: normalize_messages (batch)")
    print("=" * 60)

    messages = [SAMPLE_HTML_MESSAGE, SAMPLE_TEXT_MESSAGE, SAMPLE_MINIMAL_MESSAGE]
    results = normalize_messages(messages)

    print(f"Input count: {len(messages)}")
    print(f"Output count: {len(results)}")
    print(f"All have message_id: {all('message_id' in r for r in results)}")
    print(f"All have canonical keys: {all(len(r) == 16 for r in results)}")
    print()


def run_smoke_tests() -> None:
    """Run all smoke tests."""
    print()
    print("*" * 60)
    print("  NORMALIZE MODULE SMOKE TESTS")
    print("*" * 60)
    print()

    test_strip_html_tags()
    test_clean_email_body()
    test_normalize_message()
    test_normalize_messages()

    print("*" * 60)
    print("  ALL SMOKE TESTS COMPLETED")
    print("*" * 60)
    print()


if __name__ == "__main__":
    run_smoke_tests()
