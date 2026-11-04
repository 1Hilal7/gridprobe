"""Sanitized errors for Muse's descriptive image-observation layer."""


class VisualObservationError(Exception):
    code = "VISUAL_OBSERVATION_FAILED"


class VisualObservationConfigurationError(VisualObservationError):
    code = "VISION_NOT_CONFIGURED"


class VisualObservationProviderError(VisualObservationError):
    code = "VISION_PROVIDER_FAILED"


class VisualObservationSchemaError(VisualObservationError):
    code = "VISION_RESPONSE_INVALID"
