"""Remote HTTPS MCP probe. Writes require an owner-scoped API cleanup path."""
import argparse
import asyncio
import logging
import ipaddress
import re
import os
import sys
from pathlib import Path
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from db.scripts._token import access_token
from db.scripts.mcp_smoke import SmokeFailure, discover, call, success, smoke


def https_url(value):
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError:
        raise argparse.ArgumentTypeError('Invalid HTTPS endpoint') from None
    if (parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password
            or parsed.query or parsed.fragment or '*' in parsed.netloc or port == 0
            or '?' in value or '#' in value or any(char.isspace() for char in value)):
        raise argparse.ArgumentTypeError('Remote endpoints must be credential-free HTTPS URLs')
    try:
        ipaddress.ip_address(parsed.hostname)
    except ValueError:
        if not re.fullmatch(r'[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?', parsed.hostname):
            raise argparse.ArgumentTypeError('Invalid HTTPS hostname')
    return value.rstrip('/')


async def run(mcp_url, api_url, token, discovery_only=False):
    if api_url and not discovery_only:
        # Same network flow and exact-run-tag cleanup as local smoke. The API
        # must point to the same CountOn database and accept the same token.
        await smoke(mcp_url, api_url, token)
    else:
        await discover(mcp_url, token)
        if not discovery_only:
            success(await call(mcp_url, token, 'list_expectations', {}), 'remote authenticated list')
            print('NOT RUN capture/get/FastAPI/cleanup: configure --api-url to safely clean test data')
    print('REMOTE MCP PROBE PASSED')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mcp-url', type=https_url, default=os.getenv('MCP_PUBLIC_URL'))
    parser.add_argument('--api-url', type=https_url, default=os.getenv('COUNTON_API_URL'))
    parser.add_argument('--discovery-only', action='store_true')
    args = parser.parse_args()
    if not args.mcp_url or urlsplit(args.mcp_url).path != '/mcp':
        parser.error('Set MCP_PUBLIC_URL or --mcp-url to the canonical HTTPS /mcp endpoint')
    if args.api_url and urlsplit(args.api_url).path not in ('', '/'):
        parser.error('API URL must be an HTTPS origin without a path')
    logging.disable(logging.CRITICAL)
    try:
        token = os.getenv('COUNTON_TEST_ACCESS_TOKEN') or access_token()
        asyncio.run(run(args.mcp_url, args.api_url, token, args.discovery_only))
        return 0
    except SmokeFailure as error:
        print(f'FAIL {error}')
    except BaseException:
        print('FAIL remote probe interrupted or unavailable; no credential or exception details printed')
    return 1


if __name__ == '__main__':
    raise SystemExit(main())
