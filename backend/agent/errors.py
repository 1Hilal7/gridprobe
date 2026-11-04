"""Actionable provider errors that do not include credentials or API bodies."""


class MuseConfigurationError(ValueError):
    """Provider configuration is malformed."""


class MissingMetaAPIKeyError(MuseConfigurationError):
    """META_API_KEY is absent or blank."""


class MuseAPIError(RuntimeError):
    """A Meta API request failed at the API or transport layer."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code
