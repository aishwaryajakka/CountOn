"""Framework-independent application errors."""

from uuid import UUID


class ExpectationNotFoundError(Exception):
    def __init__(self, expectation_id: UUID):
        super().__init__(f"Expectation {expectation_id} not found")


class InvalidExpectationError(Exception):
    pass


class EvaluationNotFoundError(Exception):
    def __init__(self, expectation_id: UUID):
        super().__init__(f"No evaluation exists for expectation {expectation_id}")


class AuthenticationError(Exception):
    def __init__(self):
        super().__init__("Authentication required or token invalid")


class IdempotencyConflictError(Exception):
    pass


class ResourceNotFoundError(Exception):
    def __init__(self,code,message):
        self.code,self.message=code,message
        super().__init__(message)


class InvalidIntegrationError(Exception):
    pass
