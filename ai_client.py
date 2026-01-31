"""
OpenAI API client wrapper for email classification.

Handles API calls with retry logic, timeouts, and structured outputs.
"""
import json
import sys
import time
from typing import Any

from openai import OpenAI, APIError, APIConnectionError, RateLimitError, APITimeoutError

from settings import (
    OPENAI_API_KEY,
    OPENAI_MODEL,
    OPENAI_TIMEOUT_SECONDS,
    OPENAI_STORE,
)
from schemas import get_response_format


# Retry configuration
MAX_RETRIES = 3
INITIAL_BACKOFF_SECONDS = 1.0
MAX_BACKOFF_SECONDS = 30.0

# Token limits
MAX_OUTPUT_TOKENS = 400


class AIClient:
    """Client for OpenAI API with retry logic and structured outputs."""

    def __init__(self) -> None:
        """Initialize the OpenAI client."""
        if not OPENAI_API_KEY:
            raise ValueError(
                "OPENAI_API_KEY not set. Set it with: export OPENAI_API_KEY=sk-..."
            )
        
        self.client = OpenAI(
            api_key=OPENAI_API_KEY,
            timeout=OPENAI_TIMEOUT_SECONDS,
        )
        self.model = OPENAI_MODEL

    def classify_email(
        self,
        system_prompt: str,
        user_prompt: str,
    ) -> dict[str, Any]:
        """
        Classify an email using OpenAI with structured outputs.

        Args:
            system_prompt: System instructions for the model.
            user_prompt: The email content to classify.

        Returns:
            Parsed JSON response matching the classification schema.

        Raises:
            Exception: If all retries fail.
        """
        last_error: Exception | None = None
        backoff = INITIAL_BACKOFF_SECONDS

        for attempt in range(MAX_RETRIES):
            try:
                response = self.client.responses.create(
                    model=self.model,
                    input=[
                        {"role": "system", "content": [{"type": "text", "text": system_prompt}]},
                        {"role": "user", "content": [{"type": "text", "text": user_prompt}]},
                    ],
                    text={"format": get_response_format()},
                    temperature=0,
                    max_output_tokens=MAX_OUTPUT_TOKENS,
                    store=OPENAI_STORE,
                )

                # Extract and parse the response content
                if response.output_text:
                    result = json.loads(response.output_text)
                    if "classification" not in result:
                        raise ValueError(f"Invalid AI response: missing 'classification' key. Response: {str(result)[:100]}")
                    return result
                else:
                    raise ValueError("Empty response from OpenAI")

            except RateLimitError as e:
                last_error = e
                print(
                    f"Rate limited (attempt {attempt + 1}/{MAX_RETRIES}), "
                    f"waiting {backoff:.1f}s...",
                    file=sys.stderr,
                )
                time.sleep(backoff)
                backoff = min(backoff * 2, MAX_BACKOFF_SECONDS)

            except APITimeoutError as e:
                last_error = e
                print(
                    f"Timeout (attempt {attempt + 1}/{MAX_RETRIES}), retrying...",
                    file=sys.stderr,
                )
                time.sleep(backoff)
                backoff = min(backoff * 2, MAX_BACKOFF_SECONDS)

            except APIConnectionError as e:
                last_error = e
                print(
                    f"Connection error (attempt {attempt + 1}/{MAX_RETRIES}), retrying...",
                    file=sys.stderr,
                )
                time.sleep(backoff)
                backoff = min(backoff * 2, MAX_BACKOFF_SECONDS)

            except APIError as e:
                # Check if it's a 5xx error (server-side)
                if hasattr(e, "status_code") and e.status_code >= 500:
                    last_error = e
                    print(
                        f"Server error {e.status_code} (attempt {attempt + 1}/{MAX_RETRIES}), "
                        f"retrying...",
                        file=sys.stderr,
                    )
                    time.sleep(backoff)
                    backoff = min(backoff * 2, MAX_BACKOFF_SECONDS)
                else:
                    # Client error (4xx except rate limit), don't retry
                    raise

        # All retries exhausted
        raise Exception(f"All {MAX_RETRIES} attempts failed. Last error: {last_error}")


# Singleton instance (lazy initialization)
_client: AIClient | None = None


def get_ai_client() -> AIClient:
    """Get or create the AI client singleton."""
    global _client
    if _client is None:
        _client = AIClient()
    return _client
