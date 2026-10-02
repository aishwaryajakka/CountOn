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
