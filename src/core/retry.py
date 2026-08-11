"""Shared retry classification for provider calls."""

from typing import Any

from pydantic import ValidationError


NON_RETRYABLE_STATUS_CODES = {400, 401, 403, 404, 422}
NON_RETRYABLE_MARKERS = (
    "api key",
    "authentication",
    "unauthorized",
    "forbidden",
    "invalid model",
    "unsupported model",
    "invalid schema",
    "validation error",
    "configuration",
)


def is_retryable_provider_error(error: Exception) -> bool:
    """Return whether a provider exception is plausibly transient."""
    if isinstance(error, ValidationError):
        return False
    status_code: Any = getattr(error, "status_code", None) or getattr(error, "status", None)
    if status_code in NON_RETRYABLE_STATUS_CODES:
        return False
    message = str(error).lower()
    return not any(marker in message for marker in NON_RETRYABLE_MARKERS)
