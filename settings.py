"""
Settings and configuration for Microsoft 365 Email Reader.

Loads configuration from environment variables with sensible defaults.
"""
import os
from pathlib import Path

# Azure App Registration
CLIENT_ID = os.environ.get("M365_CLIENT_ID")
TENANT_ID = os.environ.get("M365_TENANT_ID", "common")

# Microsoft Graph API
GRAPH_BASE_URL = "https://graph.microsoft.com/v1.0"
GRAPH_SCOPES = ["https://graph.microsoft.com/Mail.Read"]

# MSAL Authority
AUTHORITY = f"https://login.microsoftonline.com/{TENANT_ID}"

# Token cache file path (in current working directory)
TOKEN_CACHE_PATH = Path("./token_cache.json")

# Default CLI values
DEFAULT_MAX_MESSAGES = 25
DEFAULT_FOLDER = "inbox"
DEFAULT_UNREAD_ONLY = True

# Graph API page size (max allowed by Microsoft is 1000, but 50 is reasonable)
PAGE_SIZE = 50

# Fields to select from Graph API (reduces payload size)
MESSAGE_SELECT_FIELDS = [
    "id",
    "conversationId",
    "internetMessageId",
    "subject",
    "from",
    "toRecipients",
    "ccRecipients",
    "receivedDateTime",
    "sentDateTime",
    "isRead",
    "webLink",
    "hasAttachments",
    "importance",
    "bodyPreview",
    "body",
]


def validate_settings() -> None:
    """Validate required settings are present."""
    if not CLIENT_ID:
        raise ValueError(
            "M365_CLIENT_ID environment variable is required.\n"
            "Set it with: export M365_CLIENT_ID=your-app-client-id\n"
            "See README.md for Azure App Registration setup instructions."
        )


# =============================================================================
# OpenAI Configuration
# =============================================================================

# API Key (required for AI features)
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")

# Model to use for classification (gpt-4o-mini is cost-effective for classification)
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")

# Request timeout in seconds
OPENAI_TIMEOUT_SECONDS = int(os.environ.get("OPENAI_TIMEOUT_SECONDS", "30"))

# Maximum characters of body text to send to AI
OPENAI_MAX_BODY_CHARS = int(os.environ.get("OPENAI_MAX_BODY_CHARS", "2500"))

# Whether to store conversations in OpenAI (false for privacy)
OPENAI_STORE = os.environ.get("OPENAI_STORE", "false").lower() == "true"

# Default AI CLI settings
DEFAULT_MAX_AI = 50
DEFAULT_MIN_CONFIDENCE = 0.75


def validate_openai_settings() -> None:
    """Validate OpenAI settings are present."""
    if not OPENAI_API_KEY:
        raise ValueError(
            "OPENAI_API_KEY environment variable is required for AI features.\n"
            "Set it with: export OPENAI_API_KEY=sk-your-api-key\n"
            "Get your API key from https://platform.openai.com/api-keys"
        )


# =============================================================================
# Heuristic Scoring Configuration (no-AI mode and fallback)
# =============================================================================

M365_USER_EMAIL = os.environ.get("M365_USER_EMAIL", "").strip().lower()
M365_VIP_SENDERS = {
    s.strip().lower()
    for s in os.environ.get("M365_VIP_SENDERS", "").split(",")
    if s.strip()
}

# Local memory file for sender scoring priors
HEURISTIC_PROFILE_PATH = Path(
    os.environ.get("HEURISTIC_PROFILE_PATH", "./sender_profiles.json")
)

# Decision thresholds
HEURISTIC_FLAG_THRESHOLD = int(os.environ.get("HEURISTIC_FLAG_THRESHOLD", "70"))
HEURISTIC_SURFACE_THRESHOLD = int(os.environ.get("HEURISTIC_SURFACE_THRESHOLD", "40"))

# Weight policy (kept separate from extraction logic for easy tuning)
HEURISTIC_WEIGHTS = {
    "to_me": 24,
    "cc_me": 6,
    "unknown_recipient_role": 0,
    "unread": 8,
    "importance_high": 14,
    "has_attachments": 5,
    "external_sender": 2,
    "internal_sender": 7,
    "vip_sender": 15,
    "noreply_sender": -30,
    "automation_pattern": -20,
    "action_phrase_strong": 20,
    "action_phrase_weak": 8,
    "direct_salutation": 14,
    "direct_salutation_to_me": 10,
    "small_group_question": 8,
    "thread_addition": 24,
    "thread_addition_cc_me": 16,
    "multi_to_no_salutation": -18,
    "last_request_phrase": 12,
    "question_present": 8,
    "imperative_present": 10,
    "deadline_present": 18,
    "urgency_present": 12,
    "approval_workflow": 16,
    "contract_finance_signal": 14,
    "fyi_phrase": -14,
    "newsletter_phrase": -22,
    "no_action_phrase": -24,
    "sender_history_max_boost": 6,
    "sender_history_max_penalty": -8,
}
