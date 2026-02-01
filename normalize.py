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
        r"^From:\s*.+\n(?:Sent:\s*.+\n)?(?:To:\s*.+\n)?(?:Cc:\s*.+\n)?Subject:\s*.+\n",
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

# Patterns for detecting boilerplate/legal text to remove
BOILERPLATE_PATTERNS = [
    # LCR-Security Warning banner at top
    re.compile(r"^LCR-Security Warning:.*?(?:\n\s*\n|$)", re.IGNORECASE | re.DOTALL),
    # Confidentiality notice blocks at bottom
    re.compile(r"^CONFIDENTIALITY NOTICE:.*$", re.IGNORECASE | re.DOTALL),
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
    if not text:
        return ""
    
    original_text = text

    # 0) Remove known boilerplate (banners/legal logic) safely
    # Only remove if it looks like a banner (at start) or footer (at end)
    for pattern in BOILERPLATE_PATTERNS:
        match = pattern.search(text)
        if match:
            # If it's a security banner (LCR-Security), it usually appears at the very start
            if "LCR-Security" in match.group() and match.start() < 50:
                text = text[match.end():].strip()
                continue
            
            # If it's a confidentiality notice, usually at the end
            if "CONFIDENTIALITY NOTICE:" in match.group().upper():
                # Only remove if it's long enough to be a real notice
                if match.end() - match.start() > 100:
                    text = text[:match.start()].strip()
                    continue

    # 1) Always truncate quoted replies/forwards (high confidence)
    earliest_reply_cut = len(text)
    for pattern in REPLY_PATTERNS:
        match = pattern.search(text)
        if match and match.start() < earliest_reply_cut:
            earliest_reply_cut = match.start()
    text = text[:earliest_reply_cut]

    # 2) Only truncate signatures if there's meaningful content before them
    # Heuristics:
    # - signature marker must be after MIN_SIG_POS characters
    # - and content before marker must be "meaningful"
    MIN_SIG_POS = 200          # don't cut signatures too early
    MIN_MEANINGFUL_CHARS = 80  # require actual content above signature

    sig_cut = None
    for pattern in SIGNATURE_PATTERNS:
        match = pattern.search(text)
        if match:
            pos = match.start()
            before = text[:pos]
            meaningful_chars = len(re.sub(r"\s+", " ", before).strip())

            if pos >= MIN_SIG_POS and meaningful_chars >= MIN_MEANINGFUL_CHARS:
                # choose the earliest valid signature cut
                if sig_cut is None or pos < sig_cut:
                    sig_cut = pos

    if sig_cut is not None:
        text = text[:sig_cut]

    # 3) Cleanup whitespace
    text = re.sub(r"\n{3,}", "\n\n", text)
    lines = [line.strip() for line in text.split("\n")]
    text = "\n".join(lines).strip()

    # 4) Extra Aggressive Token Saver Cleaning
    # (Applied after initial cleanup to catch things exposed by previous steps)
    
    lines = text.split("\n")
    cleaned_lines = []
    
    # Track content length to safely cut footers only if we have enough content
    current_length = 0
    
    for line in lines:
        stripped = line.strip()
        
        # A) Remove inline image cid references
        if "cid:image" in line or re.match(r"^\[cid:.*\]$", stripped, re.IGNORECASE):
            continue
            
        # B) Remove common garbage lines
        # Long separator lines
        if re.match(r"^[_=-]{5,}$", stripped):
            continue
            
        # Standalone header lines usually left over from reply blocks
        if re.match(r"^(From|Sent|To|Cc|Subject):.*$", stripped, re.IGNORECASE):
            continue
            
        # C) Remove Confidentiality/Legal Footers (if we already have content)
        # Check against common footer start patterns
        if current_length > 120:
             # Typical legal footer starts
             if (
                 re.match(r"^CONFIDENTIALITY NOTICE", stripped, re.IGNORECASE) or 
                 "sole use of the intended recipient" in line or
                 "privileged and confidential" in line.lower()
             ):
                 # Stop processing lines (remove everything after)
                 break
        
        cleaned_lines.append(line)
        current_length += len(stripped)

    # Reassemble and collapse blank lines again
    text = "\n".join(cleaned_lines).strip()
    text = re.sub(r"\n{3,}", "\n\n", text)
    
    # Safety: If aggressive cleaning left almost nothing, fallback to original input
    if len(re.sub(r"\s+", "", text)) < 20 and len(re.sub(r"\s+", "", original_text)) > 20:
        return original_text.strip()

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

            # Fallback to body_preview if body_text is effectively empty or too short
            # (e.g., approval emails often have minimal reply text, mostly boilerplate)
            if not body_text or len(re.sub(r"\s+", "", body_text)) < 80:
                body_preview = msg.get("bodyPreview") or ""
                if body_preview:
                    # Apply same cleaning logic to preview
                    cleaned_preview = clean_email_body(body_preview)
                    if cleaned_preview:
                        # Only use preview if it actually adds content or is longer
                        if not body_text or len(cleaned_preview) > len(body_text):
                            body_text = cleaned_preview

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
