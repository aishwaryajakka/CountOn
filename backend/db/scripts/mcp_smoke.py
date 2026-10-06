"""Loopback-only MCP/REST smoke client; creates and cleans one unique test tag."""
import argparse
import asyncio
import logging
import sys
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import httpx
import httpx2
from mcp import Client
from mcp.client.streamable_http import streamable_http_client

from db.scripts._token import access_token


class SmokeFailure(Exception):
    pass


def loopback_url(value):
    parsed = urlsplit(value)
    if (parsed.scheme != 'http' or parsed.hostname not in ('localhost', '127.0.0.1', '::1')
            or parsed.username or parsed.password or parsed.query or parsed.fragment):
        raise argparse.ArgumentTypeError('Only credential-free loopback HTTP URLs are allowed')
    return value.rstrip('/')


def token_for_smoke(demo_login):
    if not demo_login:
        return access_token()
    # Optional credential convenience, not an authentication bypass. It obtains
    # a real access token and every server still verifies its signature/claims.
    from app.core.config import get_settings
    settings = get_settings()
    if settings.environment not in ('test', 'development'):
        raise SmokeFailure('Demo login is allowed only in development/test')
    if not (settings.supabase_url and settings.supabase_publishable_key and settings.counton_demo_password):
        raise SmokeFailure('Configure existing demo Auth credentials in backend/.env.local')
    try:
        response = httpx.post(settings.supabase_url.rstrip('/') + '/auth/v1/token?grant_type=password',
            headers={'apikey': settings.supabase_publishable_key}, json={
                'email': settings.counton_demo_email,
                'password': settings.counton_demo_password.get_secret_value(),
            }, timeout=15, follow_redirects=False)
        if response.status_code != 200 or not response.json().get('access_token'):
            raise SmokeFailure('Demo Auth login failed')
        return response.json()['access_token']
    except (httpx.HTTPError, ValueError):
        raise SmokeFailure('Demo Auth login failed') from None


async def call(url, token, name, request):
    headers = {'Authorization': f'Bearer {token}'} if token else {}
    async with httpx2.AsyncClient(headers=headers, timeout=20) as http:
        async with Client(streamable_http_client(url, http_client=http), cache=None) as client:
            return await client.call_tool(name, {'request': request})


CORE_TOOLS = {'capture_expectation', 'get_expectation', 'list_expectations'}


async def discover(url, token):
    async with httpx2.AsyncClient(headers={'Authorization': f'Bearer {token}'}, timeout=20) as http:
        async with Client(streamable_http_client(url, http_client=http), cache=None) as client:
            result = await client.list_tools()
            names = {tool.name for tool in result.tools}
            if names != CORE_TOOLS or len(result.tools) != len(CORE_TOOLS):
                import re
                safe = lambda name: name if re.fullmatch(r'[A-Za-z0-9_]{1,80}', name) else '<invalid name>'
                missing = sorted(CORE_TOOLS - names)
                unexpected = sorted(safe(name) for name in names - CORE_TOOLS)
                raise SmokeFailure(f'Tool discovery mismatch: missing={missing}, unexpected={unexpected}')
            import json
            for tool in result.tools:
                json.dumps(tool.input_schema, allow_nan=False)
                json.dumps(tool.output_schema, allow_nan=False)
    print('PASS MCP initialization and exact core tool discovery')


async def unauthorized_http(url, token, stage):
    headers = {'Authorization': f'Bearer {token}'} if token else {}
    async with httpx.AsyncClient(timeout=20, follow_redirects=False) as http:
        response = await http.post(url, headers=headers, json={
            'jsonrpc': '2.0', 'id': 1, 'method': 'initialize', 'params': {}})
    if (response.status_code != 401 or 'www-authenticate' in response.headers
            or response.json().get('error', {}).get('code') != 'UNAUTHORIZED'):
        raise SmokeFailure(f'{stage} did not return a clean HTTP 401')
    print(f'PASS {stage}')


def success(result, stage):
    if result.is_error or result.structured_content is None:
        raise SmokeFailure(f'{stage} failed')
    print(f'PASS {stage}')
    return result.structured_content


def expected_error(result, code, stage):
    text = ' '.join(item.text for item in result.content if hasattr(item, 'text'))
    if not result.is_error or code not in text or 'smoke-secret-sentinel' in text:
        raise SmokeFailure(f'{stage} did not return a clean expected error')
    print(f'PASS {stage}')


async def smoke(mcp_url, api_url, token):
    claim = f'[counton-mcp-smoke:{uuid4()}] My next electricity bill should be lower'
    attempted_capture = False
    async with httpx.AsyncClient(base_url=api_url, headers={'Authorization': f'Bearer {token}'},
                                  timeout=20, follow_redirects=False) as api:
        for base in (mcp_url.rsplit('/mcp', 1)[0], api_url):
            for path in ('/health', '/ready'):
                response = await api.get(base + path)
                if response.status_code != 200:
                    raise SmokeFailure('Service health/readiness failed')
        print('PASS service health/readiness')
        try:
            await unauthorized_http(mcp_url, None, 'missing auth')
            await unauthorized_http(mcp_url, 'smoke-invalid-token', 'invalid token')
            await discover(mcp_url, token)
            success(await call(mcp_url, token, 'list_expectations', {'limit': 100}), 'initial list over HTTP')
            expected_error(await call(mcp_url, token, 'get_expectation',
                {'expectation_id': '00000000-0000-0000-0000-000000000000'}), 'NOT_FOUND', 'nonexistent expectation')
            expected_error(await call(mcp_url, token, 'capture_expectation',
                {'claim': claim, 'type': 'smoke-secret-sentinel'}), 'INVALID_ARGUMENTS', 'malformed input')
            attempted_capture = True
            created = success(await call(mcp_url, token, 'capture_expectation', {
                'claim': claim, 'type': 'numeric_comparison', 'metric': 'total_cost',
                'comparison': 'less_than', 'baseline': 142.1, 'materiality_threshold': 0.05,
            }), 'capture over HTTP')
            listed = success(await call(mcp_url, token, 'list_expectations', {'limit': 100}), 'list over HTTP')
            if created['id'] not in {row['id'] for row in listed['expectations']}:
                raise SmokeFailure('Created row missing from MCP list')
            fetched = success(await call(mcp_url, token, 'get_expectation',
                {'expectation_id': created['id']}), 'get over HTTP')
            if fetched['id'] != created['id'] or fetched['claim'] != claim:
                raise SmokeFailure('MCP row identity mismatch')
            response = await api.get(f"/api/v1/expectations/{created['id']}")
            if response.status_code != 200 or response.json()['claim'] != claim:
                raise SmokeFailure('FastAPI cross-check failed')
            print('PASS FastAPI cross-check')
        finally:
            if attempted_capture:
                # Discover by this invocation's exact unique claim, including
                # when create committed but its response was interrupted.
                offset = 0
                ids = []
                while True:
                    response = await api.get('/api/v1/expectations', params={'limit': 100, 'offset': offset})
                    if response.status_code != 200:
                        raise SmokeFailure('Cleanup lookup failed; inspect the smoke-tagged row')
                    rows = response.json()
                    ids.extend(row['id'] for row in rows if row['claim'] == claim)
                    if len(rows) < 100:
                        break
                    offset += 100
                for identity in ids:
                    response = await api.get(f'/api/v1/expectations/{identity}')
                    if response.status_code != 200 or response.json()['claim'] != claim:
                        raise SmokeFailure('Cleanup refused: row tag did not match')
                    response = await api.delete(f'/api/v1/expectations/{identity}')
                    if response.status_code != 204:
                        raise SmokeFailure('Cleanup delete failed')
                    if (await api.get(f'/api/v1/expectations/{identity}')).status_code != 404:
                        raise SmokeFailure('Cleanup persistence check failed')
                print('PASS tagged-row cleanup')
    print('MCP NETWORK SMOKE PASSED')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mcp-url', type=loopback_url, default='http://127.0.0.1:8003/mcp')
    parser.add_argument('--api-url', type=loopback_url, default='http://127.0.0.1:8000')
    parser.add_argument('--discovery-only', action='store_true', help='Initialize and check tools without creating data')
    parser.add_argument('--demo-login', action='store_true', help='Development/test only: obtain a real token using existing demo credentials')
    args = parser.parse_args()
    if not args.mcp_url.endswith('/mcp'):
        parser.error('MCP URL must end in /mcp')
    # Client library logs must never print authentication/provider responses.
    logging.disable(logging.CRITICAL)
    try:
        token = token_for_smoke(args.demo_login)
        if args.discovery_only:
            asyncio.run(discover(args.mcp_url, token))
        else:
            asyncio.run(smoke(args.mcp_url, args.api_url, token))
        return 0
    except SmokeFailure as error:
        print(f'FAIL {error}')
    except BaseException:
        print('FAIL smoke interrupted or service unavailable; no credentials or exception details printed')
    return 1


if __name__ == '__main__':
    raise SystemExit(main())
