"""Non-secret CountOn Person 1 ASK/MCP/simulator preflight.

Static audit only by default; optional HTTP probes never send tokens or signed ASK requests.
This is not Alexa live acceptance or a replacement for authenticated MCP testing.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
MODEL = ROOT / 'backend/app/alexa/interaction-model.en-US.json'
TOOLS = ROOT / 'backend/app/mcp/server.py'
ASK = ROOT / 'backend/app/api/v1/alexa.py'
EXPECTED = {
    'capture_expectation', 'get_expectation', 'list_expectations',
    'compile_expectation', 'continue_expectation_compilation',
    'explain_expectation_mismatch',
}


def audit() -> int:
    failures = []
    try:
        model = json.loads(MODEL.read_text())['interactionModel']['languageModel']
        names = {entry['name'] for entry in model['intents']}
        required = {'CaptureExpectationIntent', 'ListExpectationsIntent', 'GetExpectationIntent', 'WhyExpectationIntent'}
        if model['invocationName'] != 'count on':
            failures.append('Invocation name is not count on')
        if not required.issubset(names):
            failures.append(f'Missing ASK intents: {sorted(required - names)}')
    except (OSError, ValueError, KeyError, TypeError) as exc:
        failures.append(f'Interaction model invalid: {exc}')
    try:
        server = TOOLS.read_text()
        for name in EXPECTED:
            if name not in server:
                failures.append(f'MCP registration may be missing: {name}')
    except OSError as exc:
        failures.append(f'MCP source unreadable: {exc}')
    try:
        route = ASK.read_text()
        if 'get_alexa_verifier' not in route or 'authenticated_context' not in route:
            failures.append('ASK signed-verification/auth entry points not found')
        if 'alexa_skill_id' not in route:
            failures.append('ASK skill ID fail-closed guard not found')
    except OSError as exc:
        failures.append(f'ASK endpoint unreadable: {exc}')
    for provider in ('ring', 'bee'):
        sim = ROOT / f'backend/app/integrations/{provider}/simulator.py'
        if not sim.exists() or 'simulated' not in sim.read_text():
            failures.append(f'{provider} simulator provenance missing')
    print('CountOn Person 1 static preflight')
    print(f'ASK interaction model: {"PASS" if not any("ASK" in v or "Interaction" in v or "Invocation" in v for v in failures) else "REVIEW"}')
    print(f'Expected MCP tool names: {len(EXPECTED)}')
    print('Ring and Bee: SIMULATION ONLY (no live device claim)')
    for error in failures:
        print(f'FAIL: {error}')
    print('PASS: static preflight' if not failures else 'FAIL: static preflight')
    print('NOT VERIFIED: Alexa Developer Console, OAuth consent, Echo, signed ASK POST, authenticated MCP, SQL persistence')
    return 1 if failures else 0


def probe(url: str) -> int:
    parsed = urlsplit(url)
    if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        print('ERROR: Provide an HTTPS origin only, without credentials/query/fragment.')
        return 2
    origin = f'https://{parsed.netloc}'
    for path in ('/health', '/ready'):
        target = origin + path
        try:
            with urlopen(Request(target, headers={'User-Agent': 'CountOn-person1-preflight/1'}), timeout=5) as response:
                print(f'{path}: HTTP {response.status}')
        except HTTPError as exc:
            print(f'{path}: HTTP {exc.code} (not ready if /ready)')
        except (URLError, TimeoutError, OSError) as exc:
            print(f'{path}: unreachable ({type(exc).__name__})')
    print('Probes check reachability only; they do not establish live Alexa/MCP acceptance.')
    return 0


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--api-origin', help='Optional deployed HTTPS API origin, without a path or secrets')
    args = parser.parse_args()
    result = audit()
    if args.api_origin:
        result |= probe(args.api_origin)
    sys.exit(result)
