#!/usr/bin/env python3
"""
Microsoft 365 Email Reader - CLI Entry Point

Fetches emails from Microsoft 365 Outlook using the Microsoft Graph API.
Outputs normalized messages as JSON to stdout and optionally to a file.

Usage:
    python main.py --max 50 --folder inbox --unread-only false --out emails.json --pretty
"""
import argparse
import json
import sys
from pathlib import Path

from settings import (
    DEFAULT_FOLDER,
    DEFAULT_MAX_MESSAGES,
    DEFAULT_UNREAD_ONLY,
    validate_settings,
)
from graph_client import GraphClient
from normalize import normalize_messages


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Fetch emails from Microsoft 365 Outlook using Microsoft Graph API.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py                          # Fetch 25 unread inbox messages
  python main.py --max 50                 # Fetch up to 50 unread inbox messages
  python main.py --unread-only false      # Fetch all messages (read and unread)
  python main.py --folder sentitems       # Fetch from Sent Items folder
  python main.py --out emails.json        # Save output to file
  python main.py --pretty                 # Pretty-print JSON output
  python main.py --include-body false     # Exclude body_text (use preview only)

Common folder names:
  inbox, sentitems, drafts, deleteditems, junkemail, archive

Environment variables:
  M365_CLIENT_ID   - Required: Azure App Registration client ID
  M365_TENANT_ID   - Optional: Azure tenant ID (defaults to 'common')
""",
    )

    parser.add_argument(
        "--max",
        type=int,
        default=DEFAULT_MAX_MESSAGES,
        help=f"Maximum number of messages to fetch (default: {DEFAULT_MAX_MESSAGES})",
    )

    parser.add_argument(
        "--folder",
        type=str,
        default=DEFAULT_FOLDER,
        help=f"Mail folder to fetch from (default: {DEFAULT_FOLDER})",
    )

    parser.add_argument(
        "--unread-only",
        type=str,
        default=str(DEFAULT_UNREAD_ONLY).lower(),
        choices=["true", "false"],
        help=f"Only fetch unread messages (default: {str(DEFAULT_UNREAD_ONLY).lower()})",
    )

    parser.add_argument(
        "--out",
        type=str,
        default=None,
        help="Optional output file path for JSON (also outputs to stdout)",
    )

    parser.add_argument(
        "--pretty",
        action="store_true",
        default=False,
        help="Pretty-print JSON output with indentation",
    )

    parser.add_argument(
        "--no-body",
        action="store_true",
        default=False,
        help="Exclude body_text from output (use preview only)",
    )

    return parser.parse_args()


def main() -> int:
    """Main entry point."""
    args = parse_args()

    # Validate settings before proceeding
    try:
        validate_settings()
    except ValueError as e:
        print(f"Configuration error: {e}", file=sys.stderr)
        return 1

    # Convert string flags to booleans
    unread_only = args.unread_only.lower() == "true"
    include_body = not args.no_body

    # Validate max value
    if args.max < 1:
        print("Error: --max must be at least 1", file=sys.stderr)
        return 1

    if args.max > 1000:
        print("Warning: Fetching more than 1000 messages may take a while.", file=sys.stderr)

    # Create client and fetch messages
    try:
        client = GraphClient()
        raw_messages = client.get_messages(
            folder=args.folder,
            max_messages=args.max,
            unread_only=unread_only,
        )
    except KeyboardInterrupt:
        print("\nOperation cancelled.", file=sys.stderr)
        return 130
    except Exception as e:
        print(f"Unexpected error: {e}", file=sys.stderr)
        return 1

    # Normalize messages to canonical schema
    normalized_messages = normalize_messages(raw_messages, include_body=include_body)

    # Format output as JSON array
    indent = 2 if args.pretty else None
    json_output = json.dumps(normalized_messages, indent=indent, ensure_ascii=False)

    # Write to stdout
    print(json_output)

    # Write to file if specified
    if args.out:
        try:
            out_path = Path(args.out)
            out_path.write_text(json_output, encoding="utf-8")
            print(f"\nOutput written to: {out_path}", file=sys.stderr)
        except IOError as e:
            print(f"Error writing to file: {e}", file=sys.stderr)
            return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
