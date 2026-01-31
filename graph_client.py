"""
Microsoft Graph API client with MSAL authentication.

Handles OAuth 2.0 delegated authentication with token caching
and provides methods for fetching emails from Microsoft 365.
"""
import json
import sys
from typing import Any

import msal
import requests

from settings import (
    AUTHORITY,
    CLIENT_ID,
    GRAPH_BASE_URL,
    GRAPH_SCOPES,
    MESSAGE_SELECT_FIELDS,
    PAGE_SIZE,
    TOKEN_CACHE_PATH,
)


class GraphClient:
    """Client for Microsoft Graph API with MSAL authentication."""

    def __init__(self) -> None:
        """Initialize the Graph client with MSAL and token cache."""
        self.cache = msal.SerializableTokenCache()
        self._load_cache()

        self.app = msal.PublicClientApplication(
            client_id=CLIENT_ID,
            authority=AUTHORITY,
            token_cache=self.cache,
        )

    def _load_cache(self) -> None:
        """Load token cache from disk if it exists."""
        if TOKEN_CACHE_PATH.exists():
            try:
                self.cache.deserialize(TOKEN_CACHE_PATH.read_text())
            except (json.JSONDecodeError, Exception) as e:
                print(f"Warning: Could not load token cache: {e}", file=sys.stderr)

    def _save_cache(self) -> None:
        """Save token cache to disk if it has changed."""
        if self.cache.has_state_changed:
            TOKEN_CACHE_PATH.write_text(self.cache.serialize())

    def get_access_token(self) -> str:
        """
        Get a valid access token, using cached token or interactive login.

        Returns:
            str: A valid access token for Microsoft Graph API.

        Raises:
            SystemExit: If authentication fails.
        """
        result = None

        # First, try to get token silently from cache
        accounts = self.app.get_accounts()
        if accounts:
            # Use the first account found
            result = self.app.acquire_token_silent(
                scopes=GRAPH_SCOPES,
                account=accounts[0],
            )

        # If silent acquisition failed, do interactive login
        if not result:
            print("No cached token found. Opening browser for authentication...")
            print("Please sign in with your Microsoft 365 account.")
            print()

            try:
                result = self.app.acquire_token_interactive(
                    scopes=GRAPH_SCOPES,
                    prompt="select_account",
                )
            except Exception as e:
                print(f"Error during interactive authentication: {e}", file=sys.stderr)
                sys.exit(1)

        # Check for errors in the result
        if "error" in result:
            error = result.get("error", "unknown_error")
            error_desc = result.get("error_description", "No description provided")

            print(f"\nAuthentication failed: {error}", file=sys.stderr)
            print(f"Description: {error_desc}", file=sys.stderr)

            # Provide helpful messages for common errors
            if "AADSTS50011" in error_desc:
                print(
                    "\nHint: The redirect URI is not configured correctly.",
                    file=sys.stderr,
                )
                print(
                    "Make sure 'http://localhost' is added as a Mobile and desktop application redirect URI.",
                    file=sys.stderr,
                )
            elif "AADSTS65001" in error_desc or "consent" in error_desc.lower():
                print(
                    "\nHint: Admin consent may be required for this application.",
                    file=sys.stderr,
                )
                print(
                    "Ask your Azure AD admin to grant consent, or use an account with admin privileges.",
                    file=sys.stderr,
                )
            elif "AADSTS700016" in error_desc:
                print(
                    "\nHint: The application was not found. Check your M365_CLIENT_ID.",
                    file=sys.stderr,
                )
            elif "AADSTS7000218" in error_desc:
                print(
                    "\nHint: Public client flows are not enabled for this app.",
                    file=sys.stderr,
                )
                print(
                    "In Azure Portal > App Registration > Authentication, enable 'Allow public client flows'.",
                    file=sys.stderr,
                )

            sys.exit(1)

        # Save the cache after successful authentication
        self._save_cache()

        return result["access_token"]

    def get_messages(
        self,
        folder: str = "inbox",
        max_messages: int = 25,
        unread_only: bool = True,
    ) -> list[dict[str, Any]]:
        """
        Fetch email messages from the specified folder.

        Args:
            folder: Mail folder to fetch from (e.g., 'inbox', 'sentitems', 'drafts').
            max_messages: Maximum number of messages to retrieve.
            unread_only: If True, only fetch unread messages.

        Returns:
            List of raw message dictionaries from Graph API.

        Raises:
            SystemExit: If the API request fails.
        """
        access_token = self.get_access_token()

        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
            # Request plain text body when available (Graph may still return HTML)
            "Prefer": 'outlook.body-content-type="text"',
        }

        # Build the request URL
        select_fields = ",".join(MESSAGE_SELECT_FIELDS)
        page_size = min(PAGE_SIZE, max_messages)

        url = (
            f"{GRAPH_BASE_URL}/me/mailFolders/{folder}/messages"
            f"?$top={page_size}"
            f"&$orderby=receivedDateTime desc"
            f"&$select={select_fields}"
        )

        # Add filter for unread messages if requested
        if unread_only:
            url += "&$filter=isRead eq false"

        messages: list[dict[str, Any]] = []

        while url and len(messages) < max_messages:
            try:
                response = requests.get(url, headers=headers, timeout=30)
            except requests.RequestException as e:
                print(f"Network error: {e}", file=sys.stderr)
                sys.exit(1)

            if response.status_code == 401:
                print("Error: Unauthorized. Your token may have expired.", file=sys.stderr)
                print("Try deleting token_cache.json and running again.", file=sys.stderr)
                sys.exit(1)

            if response.status_code == 403:
                print("Error: Forbidden. Missing required permissions.", file=sys.stderr)
                print("Ensure Mail.Read permission is granted for your app.", file=sys.stderr)
                print(
                    "You may need to re-consent: delete token_cache.json and run again.",
                    file=sys.stderr,
                )
                sys.exit(1)

            if response.status_code == 404:
                print(f"Error: Folder '{folder}' not found.", file=sys.stderr)
                print(
                    "Common folders: inbox, sentitems, drafts, deleteditems, junkemail",
                    file=sys.stderr,
                )
                sys.exit(1)

            if not response.ok:
                print(
                    f"Error: API request failed with status {response.status_code}",
                    file=sys.stderr,
                )
                try:
                    error_data = response.json()
                    error_msg = error_data.get("error", {}).get("message", response.text)
                    print(f"Details: {error_msg}", file=sys.stderr)
                except Exception:
                    print(f"Response: {response.text}", file=sys.stderr)
                sys.exit(1)

            data = response.json()

            # Collect raw messages (normalization handled by normalize module)
            for msg in data.get("value", []):
                if len(messages) >= max_messages:
                    break
                messages.append(msg)

            # Get next page URL if available
            url = data.get("@odata.nextLink")

        return messages
