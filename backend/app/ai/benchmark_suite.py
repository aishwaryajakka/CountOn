"""Benchmarking and performance suite for Bedrock AI calls.

Tracks latency distributions, token usage, and cost estimates using standard
AWS Bedrock Claude 3 Sonnet / Haiku pricing tables.
"""

from dataclasses import dataclass
from typing import Any
import statistics
import time

# Pricing per 1,000 tokens (USD) as of standard Bedrock Claude 3 pricing:
# Claude 3 Sonnet: $0.003 input / $0.015 output
# Claude 3 Haiku: $0.00025 input / $0.00125 output
PRICING_TABLE = {
    "anthropic.claude-3-sonnet": {"input_per_1k": 0.003, "output_per_1k": 0.015},
    "anthropic.claude-3-haiku": {"input_per_1k": 0.00025, "output_per_1k": 0.00125},
    "default": {"input_per_1k": 0.003, "output_per_1k": 0.015},
}


def calculate_cost(model_id: str | None, input_tokens: int, output_tokens: int) -> float:
    """Calculate the estimated USD cost of a Bedrock call given token usage."""
    rates = PRICING_TABLE.get(model_id or "default", PRICING_TABLE["default"])
    input_cost = (input_tokens / 1000.0) * rates["input_per_1k"]
    output_cost = (output_tokens / 1000.0) * rates["output_per_1k"]
    return round(input_cost + output_cost, 6)


@dataclass
class BenchmarkSample:
    query: str
    latency_ms: float
    input_tokens: int
    output_tokens: int
    cost_usd: float
    success: bool
    error: str | None = None


@dataclass
class BenchmarkReport:
    total_requests: int
    successful_requests: int
    failed_requests: int
    avg_latency_ms: float
    p50_latency_ms: float
    p95_latency_ms: float
    min_latency_ms: float
    max_latency_ms: float
    total_input_tokens: int
    total_output_tokens: int
    total_cost_usd: float
    avg_cost_per_request_usd: float
    samples: list[dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_requests": self.total_requests,
            "successful_requests": self.successful_requests,
            "failed_requests": self.failed_requests,
            "latency": {
                "avg_ms": self.avg_latency_ms,
                "p50_ms": self.p50_latency_ms,
                "p95_ms": self.p95_latency_ms,
                "min_ms": self.min_latency_ms,
                "max_ms": self.max_latency_ms,
            },
            "tokens": {
                "total_input": self.total_input_tokens,
                "total_output": self.total_output_tokens,
                "total": self.total_input_tokens + self.total_output_tokens,
            },
            "cost": {
                "total_usd": self.total_cost_usd,
                "avg_per_request_usd": self.avg_cost_per_request_usd,
            },
            "samples": self.samples,
        }


def run_compiler_benchmark(
    queries: list[str],
    mock_mode: bool = False,
    model_id: str = "anthropic.claude-3-sonnet",
) -> BenchmarkReport:
    """Executes a suite of representative queries and computes latency and cost metrics."""
    from app.services import compiler_service

    samples: list[BenchmarkSample] = []

    for query in queries:
        start_time = time.perf_counter()
        success = True
        error_msg = None
        input_tokens = 0
        output_tokens = 0

        try:
            res = compiler_service.compile_statement(text=query, mock_mode=mock_mode)
            # Estimate tokens if real metrics are unavailable: ~4 chars per token rule of thumb
            input_tokens = max(15, len(query) // 4 + 80)  # prompt context + prompt
            output_tokens = max(20, len(str(res.model_dump())) // 4)
        except Exception as exc:
            success = False
            error_msg = str(exc)
            input_tokens = 0
            output_tokens = 0

        duration_ms = round((time.perf_counter() - start_time) * 1000.0, 2)
        cost = calculate_cost(model_id, input_tokens, output_tokens) if success else 0.0

        samples.append(
            BenchmarkSample(
                query=query,
                latency_ms=duration_ms,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cost_usd=cost,
                success=success,
                error=error_msg,
            )
        )

    latencies = [s.latency_ms for s in samples if s.success] or [0.0]
    total_cost = sum(s.cost_usd for s in samples)
    tot_input = sum(s.input_tokens for s in samples)
    tot_output = sum(s.output_tokens for s in samples)

    latencies_sorted = sorted(latencies)
    p50_idx = int(0.50 * (len(latencies_sorted) - 1))
    p95_idx = int(0.95 * (len(latencies_sorted) - 1))

    return BenchmarkReport(
        total_requests=len(samples),
        successful_requests=sum(1 for s in samples if s.success),
        failed_requests=sum(1 for s in samples if not s.success),
        avg_latency_ms=round(statistics.mean(latencies), 2),
        p50_latency_ms=round(latencies_sorted[p50_idx], 2),
        p95_latency_ms=round(latencies_sorted[p95_idx], 2),
        min_latency_ms=round(min(latencies), 2),
        max_latency_ms=round(max(latencies), 2),
        total_input_tokens=tot_input,
        total_output_tokens=tot_output,
        total_cost_usd=round(total_cost, 6),
        avg_cost_per_request_usd=round(total_cost / max(1, len(samples)), 6),
        samples=[s.__dict__ for s in samples],
    )
