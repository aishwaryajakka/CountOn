"""One safe event per logical call; no prompts, responses or arbitrary metadata."""

import logging
import re
from collections.abc import Mapping
from dataclasses import dataclass
from time import monotonic
from typing import Any

logger = logging.getLogger("app.ai.bedrock")


def safe_label(value: object) -> str | None:
    # Only operational labels, not arbitrary caller strings. No JWT-like dots.
    if isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9_-]{1,64}", value):
        return value
    return None


@dataclass
class CallTelemetry:
    operation_name: str
    model_id: str | None
    prompt_version: str | None
    started: float
    retry_count: int = 0
    repair_count: int = 0
    validation_result: str = "not_requested"
    aws_request_id: str | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    model_latency_ms: int = 0

    def observe(self, response: Mapping[str, Any]) -> None:
        self.aws_request_id = safe_label(
            response.get("ResponseMetadata", {}).get("RequestId")
        )
        for field, key in (
            ("input_tokens", "inputTokens"),
            ("output_tokens", "outputTokens"),
            ("total_tokens", "totalTokens"),
        ):
            value = response.get("usage", {}).get(key)
            if type(value) is int and value >= 0:
                setattr(self, field, getattr(self, field) + value)
        latency = response.get("metrics", {}).get("latencyMs")
        if type(latency) is int and latency >= 0:
            self.model_latency_ms += latency

    def finish(self, success: bool) -> None:
        fields = vars(self).copy()
        fields.pop("started")
        fields["duration_ms"] = round((monotonic() - self.started) * 1000, 2)
        fields["result_status"] = "success" if success else "failure"
        logger.log(
            logging.INFO if success else logging.WARNING,
            "Bedrock call completed",
            extra=fields,
        )
