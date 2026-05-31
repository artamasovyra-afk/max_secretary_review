from __future__ import annotations


class MaxApiError(Exception):
    """Base exception for MAX Bot API integration errors."""


class MaxApiConfigurationError(ValueError, MaxApiError):
    """Raised when MAX Bot API client settings are incomplete."""


class MaxApiRequestError(MaxApiError):
    """Raised when an outgoing MAX Bot API request fails before a response."""


class MaxApiTimeoutError(MaxApiRequestError):
    """Raised when MAX Bot API request times out."""


class MaxApiHTTPError(MaxApiError):
    def __init__(self, message: str, *, status_code: int, response_text: str | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.response_text = response_text


class MaxApiTemporaryError(MaxApiHTTPError):
    """Raised for temporary MAX Bot API HTTP errors after retries are exhausted."""


class MaxApiResponseError(MaxApiError):
    """Raised when MAX Bot API returns malformed or unexpected data."""
