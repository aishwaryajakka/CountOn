# Alexa CI collection compatibility — October 12, 2026

Branch `feature/alexa-mcp`, baseline `b87570ec38118fccdcc9199bd2b6be967b0107c2`.
The [hosted failure](https://github.com/aishwaryajakka/CountOn/actions/runs/38255661487)
completed with backend failure at `python -m pytest -q --tb=short`, frontend success
and secrets success. Public job metadata confirms this; full job logs return HTTP
403 without GitHub authentication. The supplied traceback was independently reproduced.
No commit, push, dispatch, deployment or production database operation was performed.

## Exact cause

The installed chain is:

```text
CountOn Alexa verification
→ ask-sdk-webservice-support 1.3.3
→ certvalidator 0.11.1
→ oscrypto 1.3.0
→ native OpenSSL libcrypto version detection
```

PyPI `oscrypto 1.3.0` uses `\b(\d\.\d\.\d[a-z]*)\b` in both CFFI and ctypes
libcrypto loaders. Its single-digit patch component cannot recognize `3.0.13`,
causing `LibraryNotFoundError: Error detecting the version of libcrypto` before
pytest collection can finish. Debian images with single-digit OpenSSL patch versions
can hide this problem; earlier Debian validation did not establish Ubuntu compatibility.

The reproduction used a fresh official **Ubuntu 24.04 x86_64** container with
**Python 3.12.3**, **OpenSSL 3.0.13**, the repository's original constrained packages
and complete CI environment. This matches the runner OS/Python minor/OpenSSL failure;
Ubuntu's Python patch version differs from setup-python's downloadable builds.
`python -m pytest --collect-only -q tests/test_alexa.py` exited **4**, showing the
same ASK → certvalidator → oscrypto traceback as hosted CI.

`cryptography 50.0.2` was already installed. Upgrading it cannot correct oscrypto's
separate system-libcrypto regex. On October 12, the public PyPI metadata still listed
oscrypto **1.3.0**, ASK webservice support **1.3.3**, and pyHanko certvalidator **0.32.1**
as latest releases. A published-package upgrade alone cannot resolve this import.
Sources: [upstream oscrypto fix](https://github.com/wbond/oscrypto/pull/76),
[ASK verifier imports](https://github.com/alexa/alexa-skills-kit-sdk-for-python/blob/master/ask-sdk-webservice-support/ask_sdk_webservice_support/verifier.py).

## Solution and verification boundary

Runtime requirements select the official upstream oscrypto source at immutable commit
`ebbc944485b278192b60080ea1f495e287efb4f8`, with archive SHA-256
`fa482f4b2f86eed75a451564d5a50edf7fceddaec32c389ab37038f26064905b`.
PR #76 changes both parsers to allow a multi-digit patch number. The selected upstream
tree also contains earlier platform/FFI compatibility changes since PyPI 1.3.0; their
file/commit list was reviewed and the actual artifact was tested on Ubuntu and macOS.
Installation requires HTTPS access to codeload.github.com as well as PyPI.
Dependency audit checks known advisories against package metadata; it does not replace
source review of the pinned upstream tree.
This uses upstream code rather than a runtime monkeypatch or a vendored SDK fork.

The artifact retains package version **1.3.0**, so `constraints.txt` keeps that version
and documents that `requirements.txt` supplies the fixed source. A fresh environment
is important: pip can leave an already-installed, same-version PyPI package in place.
For an existing environment, reinstall this one package explicitly:

```sh
cd backend
source .venv/bin/activate
python -m pip install --force-reinstall --no-deps 'oscrypto @ https://codeload.github.com/wbond/oscrypto/tar.gz/ebbc944485b278192b60080ea1f495e287efb4f8#sha256=fa482f4b2f86eed75a451564d5a50edf7fceddaec32c389ab37038f26064905b'
python db/scripts/alexa_import_smoke.py
```

New virtual environments and production images use the ordinary requirements install.
The archive hash is enforced by pip; do not replace it with a floating branch or plain
`pip install oscrypto==1.3.0`. Remove the source pin only when a compatible published
release passes these regressions and the signed-request tests.

CountOn's existing maintained pyHanko PKIX path remains unchanged. SDK SHA-256 body
signatures, certificate URL restrictions, trusted CA chain, digital-signature usage,
Alexa SAN, certificate expiry, timestamp window and session/application identity checks
remain enforced. No exception suppression, verification bypass or test skip was added.
The only application-file edit corrects a comment about the dependency import.

CI now runs `alexa_import_smoke.py` immediately after installation, before database
setup and pytest collection, and includes `constraints.txt` in the pip cache key.
The smoke starts fresh interpreters for default/CFFI and forced ctypes imports, loads
the real ASK/CountOn/pyHanko verification classes and trust roots, and verifies/rejects
valid/tampered RSA SHA-256 signatures using **cryptography**, CountOn's actual signature
implementation. It does not exercise oscrypto's unused legacy key-generation APIs.
Import or crypto failures remain fatal. It needs no AWS credentials, live Alexa
certificates, network certificate fetch or database connection.

Regression tests additionally inspect both installed parser patterns across seven
versions, including `3.0.10`, `3.0.13`, `3.0.20`, `3.0.100` and `1.1.1w`. Existing
signed-request tests still reject untrusted CA chains, wrong SANs, expired certificates,
tampered bodies/signatures, stale timestamps and replay/identity violations.

## Validation commands and results

An additional macOS full-suite run exposed existing clock-dependent test setup:
collection-time `iat`/`nbf` inputs could stop being future claims, and setting a repeat
poll due time from the host clock could race PostgreSQL's worker clock. Both modules
passed in isolation. The JWT test now reuses its existing frozen-clock fixture and
constructs otherwise-valid claims; the poll test sets its due time with PostgreSQL
`clock_timestamp()`. All original denial, evaluation and deduplication assertions remain.
Production authentication and worker implementations were not altered.

Final clean Ubuntu validation passed every backend workflow command:

| Check | Result |
| --- | --- |
| Alexa imports and native dependency loading | PASS, default and ctypes |
| Ruff | PASS |
| Mypy | PASS, 144 files; strict subset 37 files |
| Full backend pytest | PASS, 1,245 tests, 104 warnings, 55.45 seconds |
| Production smoke | PASS, all six groups, including signed Alexa and MCP ownership |
| Orchestration evaluation | PASS, 26/26 synthetic cases, zero Bedrock calls |
| Bandit | PASS |
| pip-audit | PASS, no known vulnerabilities found |
| pip check | PASS, no broken requirements |
| Gitleaks repository/directory scan | PASS, zero findings |
| git diff --check | PASS |

The final macOS full-suite run also passed all **1,245 tests** (104 warnings,
52.61 seconds). The orchestration evaluation explicitly reports live provider,
real Bedrock and human-reviewed acceptance as blocked; its optional separate
mocked-provider regression mode was not requested. These local results do not
claim those external acceptance gates passed.

Ubuntu validation used a new `/opt/fixed-venv`, not the original failing virtual
environment. Dependencies were installed exactly with:

```sh
python -m pip install --upgrade pip==26.2.1
python -m pip install -r requirements.txt -r requirements-dev.txt -r requirements-security.txt
```

The isolated PostgreSQL **16** container became ready, `counton_test` was created with
the workflow's `CREATE DATABASE` step, and test fixtures applied existing Alembic
migrations only to disposable local test databases. The container used the CI
`ENVIRONMENT=test`, `DATABASE_TARGET=local`, loopback local/test database URLs,
`BEDROCK_ENABLED=false` and `AWS_EC2_METADATA_DISABLED=true`. No production credentials
or ignored `.env.local` files entered the container. A repository-root marker matched
Ruff's actual checkout import classification.

Commands run from `backend` in that environment:

```sh
python db/scripts/alexa_import_smoke.py
ruff check app db/scripts tests alembic ../scripts
mypy app --ignore-missing-imports
mypy --strict --follow-imports=silent --ignore-missing-imports app/ai app/agent app/alexa app/mcp/compiler.py app/mcp/intelligence.py app/mcp/conversation_state.py app/mcp/schemas.py app/api/v1/agent.py app/api/v1/alexa.py app/schemas/compiler.py app/schemas/clarification.py app/schemas/investigation.py app/schemas/trust.py app/services/compiler_service.py app/services/investigation_service.py app/services/agent_audit.py db/scripts/bedrock_smoke.py
python -m pytest -q --tb=short
python db/scripts/production_smoke.py
python db/scripts/orchestration_eval.py
bandit -q -r app -ll
pip-audit --progress-spinner off
python -m pip check
```

Additional local checks: `.venv/bin/python db/scripts/alexa_import_smoke.py`,
full pytest via the existing private local-test-database wrapper, root
`backend/.venv/bin/python scripts/secret_scan.py` and `git diff --check`.
Frontend and secrets workflow sections were compared byte-for-byte to baseline and
are unchanged; frontend checks were not rerun for this backend-only change.

## Files changed and remaining gate

- `.github/workflows/ci.yml`: backend import smoke and constraints cache key only.
- `backend/requirements.txt`: exact upstream artifact and integrity hash.
- `backend/constraints.txt`: same-version provenance warning.
- `backend/app/alexa/verification.py`: comment clarification; no verification behavior change.
- `backend/db/scripts/alexa_import_smoke.py`: new credential-free pre-collection smoke.
- `backend/tests/test_alexa_dependencies.py`: new import/parser regressions.
- `backend/tests/test_auth.py`, `backend/tests/test_production_conversations.py`:
  deterministic test clocks; assertions and production behavior preserved.
- `docs/alexa-ci-compatibility.md`, `docs/ci-validation.md`, `docs/traditional-alexa.md`:
  current failure, repair, setup and verification documentation.

GitHub-hosted CI remains **unverified for this working tree**. After reviewing and
committing/pushing these changes yourself, wait for the new hosted run and confirm
backend, frontend and secrets are green. This local compatibility fix does not
establish live Alexa/Echo acceptance or broader production readiness.
