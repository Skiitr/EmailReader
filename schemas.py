"""
JSON Schema definitions for OpenAI Structured Outputs.

Defines the schema used for email classification responses.
"""
from typing import Any


# Classification types for email triage
CLASSIFICATION_TYPES = [
    "action_request",
    "direct_question",
    "meeting_request",
    "waiting_on_others",
    "fyi",
    "spam_or_noise",
    "unknown",
]

# JSON Schema for email classification response
EMAIL_CLASSIFICATION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "classification": {
            "type": "string",
            "enum": CLASSIFICATION_TYPES,
            "description": "The primary classification of the email",
        },
        "should_flag": {
            "type": "boolean",
            "description": "Whether the model thinks this email should be flagged for attention",
        },
        "confidence": {
            "type": "number",
            "minimum": 0.0,
            "maximum": 1.0,
            "description": "Confidence score from 0.0 to 1.0",
        },
        "reason": {
            "type": "string",
            "description": "One sentence rationale for the classification",
        },
        "summary": {
            "type": "string",
            "description": "One short sentence summary, imperative style if action requested",
        },
        "requested_action": {
            "type": ["string", "null"],
            "description": "The specific action requested, if any",
        },
        "deadline_iso": {
            "type": ["string", "null"],
            "description": "ISO 8601 date or datetime if clearly stated, else null",
        },
        "asks_me_specifically": {
            "type": "boolean",
            "description": "True if the email is addressed to me or explicitly asks me for something",
        },
        "signals": {
            "type": "object",
            "properties": {
                "to_vs_cc": {
                    "type": "string",
                    "enum": ["to", "cc", "unknown"],
                    "description": "Whether recipient is in To or CC field",
                },
                "contains_question": {
                    "type": "boolean",
                    "description": "Whether the email contains a question mark or question phrasing",
                },
                "contains_imperative": {
                    "type": "boolean",
                    "description": "Whether the email contains imperative/command language",
                },
                "mentions_deadline": {
                    "type": "boolean",
                    "description": "Whether a deadline or due date is mentioned",
                },
            },
            "required": ["to_vs_cc", "contains_question", "contains_imperative", "mentions_deadline"],
            "additionalProperties": False,
        },
    },
    "required": [
        "classification",
        "should_flag",
        "confidence",
        "reason",
        "summary",
        "requested_action",
        "deadline_iso",
        "asks_me_specifically",
        "signals",
    ],
    "additionalProperties": False,
}


def get_response_format() -> dict[str, Any]:
    """
    Get the response format configuration for OpenAI Structured Outputs.
    Used for the 'text' parameter in client.responses.create().

    Returns:
        Dict with type and json_schema configuration for the API call.
    """
    return {
        "type": "json_schema",
        "json_schema": {
            "name": "email_classification",
            "strict": True,
            "schema": EMAIL_CLASSIFICATION_SCHEMA,
        },
    }
