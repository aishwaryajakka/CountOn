"""
Custom exceptions for CountOn AI Layer.
"""

class CountOnAIError(Exception):
    """Base exception for all CountOn AI module errors."""
    pass


class BedrockClientError(CountOnAIError):
    """Raised when interaction with AWS Bedrock API fails."""
    pass


class InvalidModelResponse(CountOnAIError):
    """Raised when Bedrock returns malformed JSON or unexpected schema."""
    pass


class ExpectationCompilationError(CountOnAIError):
    """Raised when compilation of user statement fails fatally."""
    pass


class InvestigationError(CountOnAIError):
    """Raised when investigation of mismatch fails fatally."""
    pass
