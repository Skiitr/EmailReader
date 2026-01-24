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
    "subject",
    "from",
    "toRecipients",
    "ccRecipients",
    "receivedDateTime",
    "isRead",
    "conversationId",
    "webLink",
    "bodyPreview",
]


def validate_settings() -> None:
    """Validate required settings are present."""
    if not CLIENT_ID:
        raise ValueError(
            "M365_CLIENT_ID environment variable is required.\n"
            "Set it with: export M365_CLIENT_ID=your-app-client-id\n"
            "See README.md for Azure App Registration setup instructions."
        )
