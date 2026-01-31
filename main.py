#!/usr/bin/env python3
"""
Microsoft 365 Email Reader - CLI Entry Point

Fetches emails from Microsoft 365 Outlook using the Microsoft Graph API.
Optionally classifies emails using AI to determine which need action.
Outputs normalized messages as JSON to stdout and optionally to a file.

Usage:
    python main.py --max 50 --folder inbox --out emails.json --pretty
    python main.py --max 10 --out-enriched enriched.json --report report.md
"""
import argparse
import json
import sys
from pathlib import Path

from settings import (
    DEFAULT_FOLDER,
    DEFAULT_MAX_MESSAGES,
    DEFAULT_UNREAD_ONLY,
    DEFAULT_MAX_AI,
    DEFAULT_MIN_CONFIDENCE,
    validate_settings,
    validate_openai_settings,
)
from graph_client import GraphClient
from normalize import normalize_messages


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Fetch and classify emails from Microsoft 365 Outlook.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py                              # Fetch 25 unread inbox messages
  python main.py --max 50 --pretty            # Fetch 50 messages, pretty-print
  python main.py --no-ai --out emails.json    # Fetch without AI classification
  python main.py --out-enriched enriched.json # Fetch with AI, save enriched output
  python main.py --report report.md           # Generate markdown report

Common folder names:
  inbox, sentitems, drafts, deleteditems, junkemail, archive

Environment variables:
  M365_CLIENT_ID     - Required: Azure App Registration client ID
  M365_TENANT_ID     - Optional: Azure tenant ID (defaults to 'common')
  OPENAI_API_KEY     - Required for AI: OpenAI API key
  OPENAI_MODEL       - Optional: Model to use (default: gpt-4o-mini)
""",
    )

    # Email fetching options
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

    # Output options
    parser.add_argument(
        "--out",
        type=str,
        default=None,
        help="Output file for normalized JSON (without AI fields)",
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

    # AI classification options
    parser.add_argument(
        "--ai",
        action="store_true",
        dest="ai_enabled",
        default=True,
        help="Enable AI classification (default: enabled)",
    )

    parser.add_argument(
        "--no-ai",
        action="store_false",
        dest="ai_enabled",
        help="Disable AI classification",
    )

    parser.add_argument(
        "--max-ai",
        type=int,
        default=DEFAULT_MAX_AI,
        help=f"Maximum emails to send to AI (default: {DEFAULT_MAX_AI})",
    )

    parser.add_argument(
        "--min-confidence",
        type=float,
        default=DEFAULT_MIN_CONFIDENCE,
        help=f"Minimum confidence for flagging (default: {DEFAULT_MIN_CONFIDENCE})",
    )

    parser.add_argument(
        "--out-enriched",
        type=str,
        default=None,
        help="Output file for enriched JSON (with AI fields)",
    )

    parser.add_argument(
        "--report",
        type=str,
        default=None,
        help="Output file for markdown report of flagged emails",
    )

    parser.add_argument(
        "--apply",
        action="store_true",
        default=False,
        help="Apply flags to mailbox (NOT YET IMPLEMENTED)",
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

    # Validate OpenAI settings if AI is enabled
    if args.ai_enabled:
        try:
            validate_openai_settings()
        except ValueError as e:
            print(f"AI configuration error: {e}", file=sys.stderr)
            print("Use --no-ai to skip AI classification.", file=sys.stderr)
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

    # Handle --apply placeholder
    if args.apply:
        print("APPLY requested but not implemented yet.", file=sys.stderr)
        print("Flags will be computed but not written to mailbox.", file=sys.stderr)

    # Create client and fetch messages
    print(f"Fetching up to {args.max} messages from {args.folder}...", file=sys.stderr)
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

    print(f"Fetched {len(raw_messages)} messages.", file=sys.stderr)

    # Normalize messages to canonical schema
    normalized_messages = normalize_messages(raw_messages, include_body=include_body)

    # AI Classification
    enriched_messages = None
    if args.ai_enabled and normalized_messages:
        print(f"Classifying emails with AI (max {args.max_ai})...", file=sys.stderr)

        try:
            from classify import classify_emails, generate_report, get_summary_stats

            enriched_messages = classify_emails(
                normalized_messages,
                max_ai=args.max_ai,
                min_confidence=args.min_confidence,
            )

            # Print summary
            stats = get_summary_stats(enriched_messages)
            print(
                f"AI processed {stats['processed_by_ai']} emails. "
                f"Flagged: {stats['flagged']} (>={args.min_confidence:.0%} confidence). "
                f"Skipped: {stats['skipped']}.",
                file=sys.stderr,
            )

            if stats["errors"] > 0:
                print(f"Warning: {stats['errors']} classification errors.", file=sys.stderr)

        except KeyboardInterrupt:
            print("\nAI classification cancelled.", file=sys.stderr)
            return 130
        except Exception as e:
            print(f"AI classification error: {e}", file=sys.stderr)
            print("Continuing without AI results.", file=sys.stderr)
            enriched_messages = None

    # Format output
    indent = 2 if args.pretty else None

    # Output normalized JSON (without AI)
    if args.out:
        json_output = json.dumps(normalized_messages, indent=indent, ensure_ascii=False)
        try:
            out_path = Path(args.out)
            out_path.write_text(json_output, encoding="utf-8")
            print(f"Normalized output written to: {out_path}", file=sys.stderr)
        except IOError as e:
            print(f"Error writing to file: {e}", file=sys.stderr)
            return 1

    # Output enriched JSON (with AI)
    if args.out_enriched and enriched_messages:
        json_output = json.dumps(enriched_messages, indent=indent, ensure_ascii=False)
        try:
            out_path = Path(args.out_enriched)
            out_path.write_text(json_output, encoding="utf-8")
            print(f"Enriched output written to: {out_path}", file=sys.stderr)
        except IOError as e:
            print(f"Error writing enriched file: {e}", file=sys.stderr)
            return 1

    # Generate markdown report
    if args.report and enriched_messages:
        try:
            from classify import generate_report

            report = generate_report(enriched_messages, top_n=10)
            report_path = Path(args.report)
            report_path.write_text(report, encoding="utf-8")
            print(f"Report written to: {report_path}", file=sys.stderr)
        except IOError as e:
            print(f"Error writing report: {e}", file=sys.stderr)
            return 1

    # Output to stdout (enriched if available, else normalized)
    if not args.out and not args.out_enriched:
        output_data = enriched_messages if enriched_messages else normalized_messages
        json_output = json.dumps(output_data, indent=indent, ensure_ascii=False)
        print(json_output)

    return 0


if __name__ == "__main__":
    sys.exit(main())
