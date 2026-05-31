from __future__ import annotations


class Bitrix24ApiError(Exception):
    """Base exception for Bitrix24 REST API integration errors."""


class Bitrix24ConfigurationError(ValueError, Bitrix24ApiError):
    """Raised when Bitrix24 REST API client settings are incomplete."""


class Bitrix24RequestError(Bitrix24ApiError):
    """Raised when an outgoing Bitrix24 REST API request fails before a response."""


class Bitrix24TimeoutError(Bitrix24RequestError):
    """Raised when Bitrix24 REST API request times out."""


class Bitrix24HTTPError(Bitrix24ApiError):
    def __init__(self, message: str, *, status_code: int, response_text: str | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.response_text = response_text


class Bitrix24TemporaryError(Bitrix24HTTPError):
    """Raised for temporary Bitrix24 REST API HTTP errors after retries are exhausted."""


class Bitrix24ResponseError(Bitrix24ApiError):
    """Raised when Bitrix24 REST API returns an application error or malformed data."""


class Bitrix24MappingError(Bitrix24ApiError):
    """Raised when a local entity cannot be mapped to Bitrix24 payload fields."""
