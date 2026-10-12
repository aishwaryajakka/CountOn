"""Small JSON log formatter with explicit fields and no exception payloads."""

import json
import logging
from datetime import datetime, timezone

from app.core.config import get_settings
from app.core.observability import request_id


class StructuredFormatter(logging.Formatter):
    def format(self, record):
        # Uvicorn's normal message embeds the complete URL/query. Provider OAuth
        # callbacks contain short-lived codes, so never interpolate that record.
        access = record.name == "uvicorn.access"
        sdk = record.name.startswith(("mcp", "ask_sdk"))
        value = {
            "timestamp": datetime.fromtimestamp(
                record.created, timezone.utc
            ).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": "HTTP access"
            if access
            else "SDK event"
            if sdk
            else record.getMessage(),
            "request_id": request_id.get(),
        }
        if access and isinstance(record.args, tuple) and len(record.args) == 5:
            method, status = record.args[1], record.args[4]
            if method in ("GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"):
                value["method"] = method
            if type(status) is int and 100 <= status <= 599:
                value["status_code"] = status
        for key in (
            "method",
            "route",
            "status_code",
            "user_id",
            "expectation_id",
            "integration_id",
            "duration_ms",
            "tool_name",
            "result_status",
            "operation_name",
            "model_id",
            "retry_count",
            "validation_result",
            "aws_request_id",
            "input_tokens",
            "output_tokens",
            "total_tokens",
            "model_latency_ms",
            "prompt_version",
            "repair_count",
            "turn_count",
            "clarification_event",
            "run_id",
            "action",
            "audit_status",
            "readiness_code",
            "missing_table_count",
            "missing_column_count",
            "expected_revisions",
            "observed_revisions",
        ):
            if hasattr(record, key):
                value[key] = getattr(record, key)
        return json.dumps(value, default=str)


def configure_logging():
    logging.basicConfig(level=get_settings().log_level)
    for handler in logging.getLogger().handlers:
        handler.setFormatter(StructuredFormatter())
    for handler in logging.getLogger("uvicorn.access").handlers:
        handler.setFormatter(StructuredFormatter())
    for name in (
        "sqlalchemy.engine",
        "sqlalchemy.pool",
        "psycopg",
        "httpx",
        "httpcore",
        "httpx2",
        "httpcore2",
        "boto3",
        "botocore",
        "urllib3",
        "mcp",
        "mcp_types",
        "ask_sdk_core",
        "ask_sdk_webservice_support",
        "ask_sdk_runtime",
    ):
        logging.getLogger(name).setLevel(logging.WARNING)
