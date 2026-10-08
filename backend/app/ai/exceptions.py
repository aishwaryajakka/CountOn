"""Stable, deliberately payload-free failures for optional intelligence."""


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
