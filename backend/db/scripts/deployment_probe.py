"""Read-only remote acceptance probe. No capture, compile, evidence or cleanup writes."""

import argparse
import asyncio
import logging
import os
import sys
from pathlib import Path
from urllib.parse import urlsplit
from uuid import UUID

import httpx
import httpx2
from mcp import Client
from mcp.client.streamable_http import streamable_http_client

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from db.scripts.intelligence_smoke import TOOLS
from db.scripts.mcp_remote_smoke import https_url
from db.scripts.mcp_smoke import token_for_smoke


async def run(api_url, mcp_url, frontend_origin, token=None, *, http=None, mcp_factory=None):
    failures = []
    blocked = []

    def check(label, passed):
        print(f"{'PASS' if passed else 'FAIL'} REMOTE {label}")
        if not passed:
            failures.append(label)

    async with httpx.AsyncClient(timeout=15, follow_redirects=False, transport=http) as client:
        async def status(label, method, url, expected, **kwargs):
            try:
                result = await client.request(method, url, **kwargs)
                check(f"{label} (HTTP {result.status_code})", result.status_code == expected)
                return result
            except Exception:  # noqa: BLE001 -- transport errors may contain headers/URLs
                check(f"{label} (transport unavailable)", False)
                return None

        for label, origin in (("API", api_url), ("MCP", mcp_url.removesuffix("/mcp"))):
            for path in ("/health", "/ready"):
                await status(label + path, "GET", origin + path, 200)
        await status("API missing auth", "GET", api_url + "/api/v1/expectations", 401)
        for label, headers in (("missing auth", {}), ("invalid auth", {"Authorization": "Bearer counton-invalid-probe-token"})):
            await status("MCP " + label, "POST", mcp_url, 401, headers=headers, json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
        for origin, expected in ((frontend_origin, 200), ("https://counton-untrusted-origin.invalid", 400)):
            response = await status("CORS approved origin" if expected == 200 else "CORS rejected origin", "OPTIONS", api_url + "/api/v1/expectations", expected, headers={"Origin": origin, "Access-Control-Request-Method": "GET", "Access-Control-Request-Headers": "authorization"})
            if response is not None:
                check("CORS exact allowlist" if expected == 200 else "CORS no untrusted grant", response.headers.get("access-control-allow-origin") == origin if expected == 200 else "access-control-allow-origin" not in response.headers)
        response = await status("API contract", "GET", api_url + "/openapi.json", 200)
        if response is not None and response.status_code == 200:
            try:
                paths = response.json()["paths"]
                for path in ("/api/v1/agent/converse", "/api/v1/alexa", "/api/v1/expectations/{expectation_id}/monitoring"):
                    check("route " + path, path in paths)
            except Exception:  # noqa: BLE001 -- never print remote content
                check("API contract usable", False)
        if not token:
            print("BLOCKED REMOTE authenticated API/MCP: no dedicated access token; no login attempted")
            blocked.append("authentication")
        else:
            authenticated = await status("authenticated API list", "GET", api_url + "/api/v1/expectations", 200, headers={"Authorization": f"Bearer {token}", "Origin": frontend_origin}, params={"limit": 1})
            if authenticated is not None:
                check("authenticated API CORS", authenticated.headers.get("access-control-allow-origin") == frontend_origin)
            try:
                async with asyncio.timeout(45):
                    async with httpx2.AsyncClient(headers={"Authorization": f"Bearer {token}"}, timeout=15, follow_redirects=False) as transport:
                        factory = mcp_factory or (lambda: Client(streamable_http_client(mcp_url, http_client=transport), cache=None))
                        async with factory() as mcp:
                            check("MCP initialize", True)
                            result = await mcp.list_tools()
                            names = {tool.name for tool in result.tools}
                            check("MCP six tools/list", TOOLS <= names)
                            if TOOLS - names:
                                print("Missing required MCP tools: " + ", ".join(sorted(TOOLS - names)))
                            check("MCP nested request schemas", TOOLS <= names and all(set(tool.input_schema.get("properties", {})) == {"request"} for tool in result.tools if tool.name in TOOLS))
                            listed = await mcp.call_tool("list_expectations", {"request": {"limit": 1}})
                            content = listed.structured_content
                            usable = not listed.is_error and isinstance(content, dict) and isinstance(content.get("expectations"), list)
                            check("MCP list_expectations", usable)
                            if usable and content["expectations"]:
                                identity = str(UUID(content["expectations"][0]["id"]))
                                detail = await mcp.call_tool("get_expectation", {"request": {"expectation_id": identity}})
                                valid = not detail.is_error and isinstance(detail.structured_content, dict) and detail.structured_content.get("id") == identity
                                check("MCP get_expectation", valid)
                                api = await status("owned API detail", "GET", api_url + "/api/v1/expectations/" + identity, 200, headers={"Authorization": f"Bearer {token}"})
                                check("shared existing row persistence", valid and api is not None and api.status_code == 200 and api.json().get("id") == identity and api.json().get("claim") == detail.structured_content.get("claim"))
                            elif usable:
                                print("BLOCKED REMOTE get/shared-row check: empty owned list; no data created")
                                blocked.append("empty list")
            except Exception:  # noqa: BLE001 -- no SDK payload, identity, token or model output
                check("MCP authenticated protocol (private details suppressed)", False)
    print("REMOTE capture/worker/provider/browser/device/backup/edge-load acceptance: NOT RUN")
    return 1 if failures else 2 if blocked else 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--remote", action="store_true", required=True, help="Explicitly select remote verification; never inferred from local tests")
    parser.add_argument("--api-url", type=https_url, required=True)
    parser.add_argument("--mcp-url", type=https_url, required=True)
    parser.add_argument("--frontend-origin", type=https_url, required=True)
    parser.add_argument("--demo-login", action="store_true", help="Explicitly use existing development/test demo credentials to obtain a real Supabase token")
    args = parser.parse_args()
    if urlsplit(args.mcp_url).path != "/mcp" or any(urlsplit(u).path not in ("", "/") for u in (args.api_url, args.frontend_origin)):
        parser.error("Use API/frontend HTTPS origins and the canonical HTTPS /mcp endpoint")
    logging.disable(logging.CRITICAL)
    token = os.getenv("COUNTON_TEST_ACCESS_TOKEN")
    try:
        if args.demo_login:
            token = token_for_smoke(True)
        return asyncio.run(run(args.api_url, args.mcp_url, args.frontend_origin, token))
    except Exception:  # noqa: BLE001 -- config/auth messages can contain credentials
        print("FAIL REMOTE probe configuration/login; private details suppressed")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
