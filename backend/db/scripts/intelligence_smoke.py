"""Opt-in real MCP/Bedrock probe; writes require exact tagged cleanup via REST."""

import argparse
import asyncio
import logging
import os
import sys
from pathlib import Path
from uuid import UUID, uuid4

import httpx
import httpx2
from mcp import Client
from mcp.client.streamable_http import streamable_http_client

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from db.scripts.mcp_remote_smoke import https_url
from db.scripts.mcp_smoke import SmokeFailure, loopback_url

TOOLS = {
    "list_expectations",
    "get_expectation",
    "capture_expectation",
    "compile_expectation",
    "continue_expectation_compilation",
    "explain_expectation_mismatch",
}


def endpoint(value: str) -> str:
    return loopback_url(value) if value.startswith("http:") else https_url(value)


async def probe(
    mcp_url: str, api_url: str | None, token: str, *, compile_: bool, capture: bool
) -> None:
    tag = f"[counton-intelligence-smoke:{uuid4()}]"
    expected_claim = None
    attempted = False
    identity = None
    async with httpx.AsyncClient(
        headers={"Authorization": f"Bearer {token}"}, timeout=20, follow_redirects=False
    ) as api:
        try:
            async with (
                httpx2.AsyncClient(
                    headers={"Authorization": f"Bearer {token}"}, timeout=180
                ) as transport,
                Client(
                    streamable_http_client(mcp_url, http_client=transport), cache=None
                ) as mcp,
            ):
                discovered = await mcp.list_tools()
                if not TOOLS <= {tool.name for tool in discovered.tools}:
                    raise SmokeFailure(
                        "Deploy the six-tool intelligence MCP surface first"
                    )
                print("PASS initialize and six-tool discovery")

                async def call(name, request):
                    result = await mcp.call_tool(name, {"request": request})
                    if result.is_error or not isinstance(
                        result.structured_content, dict
                    ):
                        raise SmokeFailure(
                            "MCP tool failed; private details suppressed"
                        )
                    return result.structured_content

                await call("list_expectations", {"limit": 1})
                print("PASS authenticated list")
                if not compile_:
                    return
                result = await call(
                    "compile_expectation",
                    {
                        "text": f"My grocery bill should stay under $120 this week. {tag}",
                        "timezone": "America/Chicago",
                        "locale": "en-US",
                    },
                )
                if result.get("status") != "compiled" or not isinstance(
                    result.get("expectation"), dict
                ):
                    raise SmokeFailure(
                        "Compilation did not produce a valid expectation; nothing captured"
                    )
                structured = result["expectation"]
                expected_claim = structured.get("claim")
                if not isinstance(expected_claim, str) or tag not in expected_claim:
                    raise SmokeFailure(
                        "Compiler did not retain the run tag; capture refused"
                    )
                print("PASS Bedrock compile over MCP; no mutation yet")
                if capture:
                    attempted = True
                    saved = await call("capture_expectation", structured)
                    identity = str(UUID(saved["id"]))
                    detail = await call("get_expectation", {"expectation_id": identity})
                    if detail.get("claim") != expected_claim:
                        raise SmokeFailure("Captured claim mismatch")
                    response = await api.get(
                        f"{api_url}/api/v1/expectations/{identity}"
                    )
                    if (
                        response.status_code != 200
                        or response.json().get("claim") != expected_claim
                    ):
                        raise SmokeFailure("Shared FastAPI persistence failed")
                    print("PASS compile → capture → get → shared API persistence")
        finally:
            if attempted:
                # Recover a lost capture response by its unique run tag and exact claim.
                identities = {identity} if identity else set()
                offset = 0
                while True:
                    response = await api.get(
                        f"{api_url}/api/v1/expectations",
                        params={"limit": 100, "offset": offset},
                    )
                    if response.status_code != 200:
                        raise SmokeFailure(
                            "Cleanup discovery failed; inspect dedicated test account"
                        )
                    rows = response.json()
                    identities.update(
                        row["id"]
                        for row in rows
                        if row.get("claim") == expected_claim
                        and tag in row.get("claim", "")
                    )
                    if len(rows) < 100:
                        break
                    offset += 100
                for found in identities:
                    response = await api.get(f"{api_url}/api/v1/expectations/{found}")
                    if (
                        response.status_code != 200
                        or response.json().get("claim") != expected_claim
                        or tag not in response.json().get("claim", "")
                    ):
                        raise SmokeFailure(
                            "Cleanup refused: exact owned run tag did not match"
                        )
                    response = await api.delete(
                        f"{api_url}/api/v1/expectations/{found}"
                    )
                    if response.status_code != 204:
                        raise SmokeFailure(
                            "Tagged cleanup failed; inspect dedicated test account"
                        )
                    if (
                        await api.get(f"{api_url}/api/v1/expectations/{found}")
                    ).status_code != 404:
                        raise SmokeFailure("Tagged cleanup persistence failed")
                print("PASS exact tagged-row cleanup")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mcp-url", type=endpoint, required=True)
    parser.add_argument("--api-url", type=endpoint)
    parser.add_argument(
        "--compile",
        action="store_true",
        help="Authorize one paid inference; no capture",
    )
    parser.add_argument(
        "--capture",
        action="store_true",
        help="Compile, save one tagged expectation, verify and clean up",
    )
    args = parser.parse_args()
    if not args.mcp_url.endswith("/mcp") or args.capture and not args.api_url:
        parser.error("Use /mcp; --capture requires --api-url for safe cleanup")
    token = os.getenv("COUNTON_TEST_ACCESS_TOKEN") or os.getenv("COUNTON_ACCESS_TOKEN")
    if not token:
        print(
            "BLOCKED: securely supply COUNTON_TEST_ACCESS_TOKEN; no interactive credential prompt"
        )
        return 1
    logging.disable(logging.CRITICAL)
    try:
        asyncio.run(
            probe(
                args.mcp_url,
                args.api_url,
                token,
                compile_=args.compile or args.capture,
                capture=args.capture,
            )
        )
    except Exception:  # noqa: BLE001 — never print credential-bearing provider exceptions
        print("FAIL intelligence smoke; credentials and private records suppressed")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
