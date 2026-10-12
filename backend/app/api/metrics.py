"""Private aggregate metrics; no identities, utterances, tokens or raw payloads."""

import hmac
import math
import re

from fastapi import APIRouter, Request
from fastapi.responses import PlainTextResponse

from app.api.errors import error_response
from app.core import observability
from app.core.config import get_settings

router = APIRouter()


@router.get("/metrics", include_in_schema=False)
def metrics(request: Request):
    key = get_settings().operations_metrics_token
    if key is None:
        return error_response(503, "NOT_CONFIGURED", "Metrics access is not configured")
    supplied = request.headers.get("Authorization", "")
    if not hmac.compare_digest(
        supplied.encode(), ("Bearer " + key.get_secret_value()).encode()
    ):
        return error_response(401, "UNAUTHORIZED", "Metrics authentication required")
    sink = observability.metrics
    if not isinstance(sink, observability.MemoryMetrics):
        return error_response(
            503, "NOT_CONFIGURED", "Metrics are exported by the configured sink"
        )
    lines = []
    for (name, label), value in sorted(sink.snapshot().items()):
        if not re.fullmatch(r"[a-z_]+", name) or not math.isfinite(value):
            continue
        escaped = label.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
        lines.append(f'counton_{name}{{operation="{escaped}"}} {value}')
    return PlainTextResponse(
        "\n".join(lines) + "\n",
        media_type="text/plain; version=0.0.4",
        headers={"Cache-Control": "no-store"},
    )
