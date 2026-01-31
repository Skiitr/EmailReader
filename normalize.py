"""
Email message normalization module.

Converts raw Microsoft Graph API message objects into a stable,
canonical JSON schema for downstream processing.
"""
import html
import re
from html.parser import HTMLParser
from typing import Any


# Maximum length for body_text (truncate with ellipsis if exceeded)
MAX_BODY_LENGTH = 4000

# Patterns for detecting reply/forward markers (compiled for performance)
REPLY_PATTERNS = [
    # "On Mon, Jan 15, 2026 at 10:30 AM John Doe <john@example.com> wrote:"
    re.compile(r"^On .+ wrote:\s*$", re.MULTILINE | re.IGNORECASE),
    # "-----Original Message-----"
    re.compile(r"^-{3,}\s*Original Message\s*-{3,}", re.MULTILINE | re.IGNORECASE),
    # Classic Outlook reply header block
    re.compile(
        r"^From:\s*.+\n(?:Sent:\s*.+\n)?(?:To:\s*.+\n)?(?:Cc:\s*.+\n)?(?:Subject:\s*.+)?",
        re.MULTILINE | re.IGNORECASE,
    ),
    # Gmail-style forwarded message
    re.compile(r"^-{3,}\s*Forwarded message\s*-{3,}", re.MULTILINE | re.IGNORECASE),
]

# Patterns for detecting signatures
SIGNATURE_PATTERNS = [
    # "-- " standard signature delimiter
    re.compile(r"^-- \s*$", re.MULTILINE),
    # "Sent from my iPhone/Android/etc"
    re.compile(r"^Sent from my \w+", re.MULTILINE | re.IGNORECASE),
    # "Get Outlook for iOS/Android"
    re.compile(r"^Get Outlook for \w+", re.MULTILINE | re.IGNORECASE),
]


class HTMLTextExtractor(HTMLParser):
    """
    HTML parser that extracts plain text content.
    
    Strips all HTML tags and converts entities to text.
    Handles common email HTML patterns.
    """

    def __init__(self) -> None:
        super().__init__()
        self.text_parts: list[str] = []
        self._skip_data = False
        self._skip_tags = {"script", "style", "head", "meta", "title"}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag_lower = tag.lower()
        if tag_lower in self._skip_tags:
            self._skip_data = True
        # Add newline for block-level elements
        elif tag_lower in {"br", "p", "div", "tr", "li", "h1", "h2", "h3", "h4", "h5", "h6"}:
            self.text_parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        tag_lower = tag.lower()
        if tag_lower in self._skip_tags:
            self._skip_data = False
        # Add newline after block elements
        elif tag_lower in {"p", "div", "tr", "li", "h1", "h2", "h3", "h4", "h5", "h6"}:
            self.text_parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self._skip_data:
            self.text_parts.append(data)

    def handle_entityref(self, name: str) -> None:
        if not self._skip_data:
            char = html.unescape(f"&{name};")
            self.text_parts.append(char)

    def handle_charref(self, name: str) -> None:
        if not self._skip_data:
            char = html.unescape(f"&#{name};")
            self.text_parts.append(char)

    def get_text(self) -> str:
        """Return the extracted plain text."""
        return "".join(self.text_parts)


def strip_html_tags(html_content: str) -> str:
    """
    Convert HTML content to plain text.

    Uses Python's stdlib html.parser to extract text content
    while preserving basic structure (newlines for block elements).

    Args:
        html_content: HTML string to convert.

    Returns:
        Plain text with HTML tags and entities converted.
    """
    if not html_content:
        return ""

    try:
        parser = HTMLTextExtractor()
        parser.feed(html_content)
        return parser.get_text()
    except Exception:
        # Fallback: simple regex-based tag removal
        text = re.sub(r"<[^>]+>", " ", html_content)
        return html.unescape(text)


def clean_email_body(text: str) -> str:
    """
    Clean email body text by removing quoted replies and signatures.

    Applies best-effort heuristics to keep only the newest/primary
    content from an email, removing:
    - Quoted reply content (On ... wrote:, etc.)
    - Forwarded message headers
    - Signature blocks
    - Excessive whitespace

    Args:
        text: Plain text email body.

    Returns:
        Cleaned text with replies and signatures removed.
    """
    if not text:
        return ""

    # Find the earliest position where a reply/signature marker appears
    # and truncate everything after it
    earliest_cut = len(text)

    # Check for reply markers
    for pattern in REPLY_PATTERNS:
        match = pattern.search(text)
        if match and match.start() < earliest_cut:
            earliest_cut = match.start()

    # Check for signature markers
    for pattern in SIGNATURE_PATTERNS:
        match = pattern.search(text)
        if match and match.start() < earliest_cut:
            earliest_cut = match.start()

    # Truncate at the earliest marker found
    text = text[:earliest_cut]

    # Collapse multiple blank lines into at most two
    text = re.sub(r"\n{3,}", "\n\n", text)

    # Remove leading/trailing whitespace from each line and the whole text
    lines = [line.strip() for line in text.split("\n")]
    text = "\n".join(lines).strip()

    return text


def normalize_message(msg: dict[str, Any], include_body: bool = True) -> dict[str, Any]:
    """
    Normalize a Microsoft Graph message to canonical schema.

    Converts the raw Graph API message format to a stable internal
    representation with consistent field names and types.

    Args:
        msg: Raw message dict from Microsoft Graph API.
        include_body: If True, process and include body_text. If False, set to null.

    Returns:
        Normalized message dictionary with canonical schema.
    """
    # Extract sender info
    from_data = msg.get("from", {})
    if from_data:
        email_address = from_data.get("emailAddress", {})
        sender = {
            "name": email_address.get("name") or None,
            "email": email_address.get("address") or None,
        }
    else:
        sender = {"name": None, "email": None}

    # Extract recipient email addresses
    def extract_emails(recipients: list[dict[str, Any]] | None) -> list[str]:
        if not recipients:
            return []
        emails = []
        for r in recipients:
            addr = r.get("emailAddress", {}).get("address")
            if addr:
                emails.append(addr)
        return emails

    to_emails = extract_emails(msg.get("toRecipients"))
    cc_emails = extract_emails(msg.get("ccRecipients"))

    # Process body content
    body_text: str | None = None
    if include_body:
        body_data = msg.get("body", {})
        content_type = body_data.get("contentType", "").lower()
        content = body_data.get("content", "")

        if content:
            # Convert HTML to plain text if needed
            if content_type == "html":
                body_text = strip_html_tags(content)
            else:
                body_text = content

            # Clean the body text
            body_text = clean_email_body(body_text)

            # Truncate if too long
            if body_text and len(body_text) > MAX_BODY_LENGTH:
                body_text = body_text[: MAX_BODY_LENGTH - 3] + "..."

            # Ensure we return None instead of empty string
            if not body_text:
                body_text = None

    # Build canonical message
    return {
        "message_id": msg.get("id") or "",
        "conversation_id": msg.get("conversationId") or None,
        "internet_message_id": msg.get("internetMessageId") or None,
        "subject": msg.get("subject") or None,
        "from": sender,
        "to": to_emails,
        "cc": cc_emails,
        "received_at": msg.get("receivedDateTime") or None,
        "sent_at": msg.get("sentDateTime") or None,
        "is_read": bool(msg.get("isRead", False)),
        "web_link": msg.get("webLink") or None,
        "has_attachments": bool(msg.get("hasAttachments", False)),
        "importance": msg.get("importance") or None,
        "body_preview": msg.get("bodyPreview") or None,
        "body_text": body_text,
    }


def normalize_messages(
    msgs: list[dict[str, Any]], include_body: bool = True
) -> list[dict[str, Any]]:
    """
    Normalize a list of Microsoft Graph messages.

    Args:
        msgs: List of raw message dicts from Microsoft Graph API.
        include_body: If True, process and include body_text. If False, set to null.

    Returns:
        List of normalized message dictionaries.
    """
    return [normalize_message(msg, include_body=include_body) for msg in msgs]


# Allow running as module for quick testing
if __name__ == "__main__":
    # Run smoke test when executed directly
    from smoke_test_normalize import run_smoke_tests

    run_smoke_tests()
