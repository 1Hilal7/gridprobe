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


class MuseResponseParsingError(RuntimeError):
    """The SDK could not parse a structured completion."""


class GridProbeAgentError(RuntimeError):
    """Investigation boundary error with a stable, non-sensitive code."""

    code = "AGENT_ERROR"


class UnknownToolError(GridProbeAgentError):
    code = "UNKNOWN_TOOL"


class MalformedToolArgumentsError(GridProbeAgentError):
    code = "MALFORMED_TOOL_ARGUMENTS"


class ToolExecutionError(GridProbeAgentError):
    code = "TOOL_EXECUTION_FAILED"


class MaxAgentStepsError(GridProbeAgentError):
    """Recoverable termination recorded in the result before finalization."""

    code = "MAX_AGENT_STEPS"


class DiagnosisSchemaError(GridProbeAgentError):
    code = "DIAGNOSIS_SCHEMA_FAILED"


class AgentProviderError(GridProbeAgentError):
    code = "PROVIDER_FAILED"
