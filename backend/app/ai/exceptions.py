"""
Exceptions for CountOn AI Layer with structured intelligence telemetry and error codes.
Preserves existing CountOnAIError hierarchy and adds canonical Bedrock error classifications.
"""


class CountOnAIError(Exception):
    """Base exception for all CountOn AI module errors."""
    pass


class BedrockError(Exception):
    message = "Bedrock request failed"

    def __init__(self) -> None:
        super().__init__(self.message)


class BedrockUnavailableError(BedrockError):
    message = "Bedrock is unavailable or not configured"


class BedrockThrottledError(BedrockError):
    message = "Bedrock request was throttled"


class BedrockTimeoutError(BedrockError):
    message = "Bedrock request timed out"


class BedrockResponseError(BedrockError):
    message = "Bedrock returned an unusable response"


class BedrockValidationError(BedrockResponseError):
    message = "Bedrock output failed structured validation"

    def __init__(self, error_types: tuple[str, ...] = ()) -> None:
        import re

        super().__init__()
        # Pydantic type codes only; never locations, context, input or messages.
        self.feedback = (
            ", ".join(
                sorted(
                    {
                        code
                    for code in error_types
                        if re.fullmatch(r"[a-z_]{1,64}", code)
                    }
                )
            )[:300]
            or "invalid_json"
        )


class BedrockDisabledError(BedrockError):
    message = "Bedrock intelligence is disabled"


class BedrockClientError(BedrockError, CountOnAIError):
    """Raised when interaction with AWS Bedrock API fails."""
    def __init__(self, message: str = "Bedrock request failed") -> None:
        self.message = message
        super().__init__()


class InvalidModelResponse(BedrockResponseError, CountOnAIError):
    """Raised when Bedrock returns malformed JSON or unexpected schema."""
    def __init__(self, message: str = "Bedrock returned an unusable response") -> None:
        self.message = message
        super().__init__()


class ExpectationCompilationError(CountOnAIError):
    """Raised when compilation of user statement fails fatally."""
    pass


class InvestigationError(CountOnAIError):
    """Raised when investigation of mismatch fails fatally."""
    pass


def intelligence_error_code(error: Exception) -> str:
    """Classify failures without exposing messages, provider responses or inputs."""
    if isinstance(error, BedrockDisabledError):
        return "BEDROCK_DISABLED"
    if isinstance(error, BedrockThrottledError):
        return "BEDROCK_THROTTLED"
    if isinstance(error, BedrockResponseError):
        return "COMPILER_INVALID_OUTPUT"
    if isinstance(error, BedrockError):
        return "BEDROCK_UNAVAILABLE"
    return "COMPILER_INVALID_OUTPUT"
