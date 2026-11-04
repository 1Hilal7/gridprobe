"""Static messages only: provider bodies and credentials must never escape."""


class SamError(Exception):
    code = "SAM_FAILED"


class SamConfigurationError(SamError):
    code = "SAM_NOT_CONFIGURED"


class SamImageError(SamError):
    code = "IMAGE_UNAVAILABLE"


class SamPathError(SamError):
    code = "IMAGE_PATH_REJECTED"


class SamProviderError(SamError):
    code = "SAM_PROVIDER_FAILED"


class SamParsingError(SamError):
    code = "SAM_RESPONSE_INVALID"
