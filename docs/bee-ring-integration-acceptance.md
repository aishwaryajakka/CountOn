# Bee CLI, Bee simulator, and Ring simulator acceptance

Validated locally on 2026-10-13. This document distinguishes implementation and
fixture coverage from access to a real Bee account or physical Ring device.

## Acceptance matrix

| Capability | Status | Evidence / limit |
| --- | --- | --- |
| Ring simulator | **IMPLEMENTED, LOCALLY TESTED, SIMULATED** | Authenticated server endpoint, explicit expectation source approval, persisted evidence/evaluation, stable event replay. No Ring hardware or Ring account is involved. |
| Bee simulator | **IMPLEMENTED, LOCALLY TESTED, SIMULATED** | Authenticated server endpoint, explicit expectation source approval, persisted context/evaluation, stable event replay. A recorded promise is context and produces `UNKNOWN` without outcome evidence. |
| Official Bee CLI detection | **IMPLEMENTED, FIXTURE TESTED** | Detects the `bee` binary and runs the official `bee version --json` and `bee me --json` commands. The binary was not installed on this machine. |
| Bee CLI authentication | **IMPLEMENTED, NOT REAL-ACCOUNT VERIFIED** | Authentication stays in the official CLI. CountOn directs the user to `bee login`; it never requests or reads the Bee token. |
| Local pairing | **IMPLEMENTED, LOCALLY TESTED** | Signed-in CountOn user creates a 10-minute single-use code. The bridge exchanges it for a 90-day, narrowly scoped, revocable CountOn connector token. Only SHA-256 digests are stored by the backend. |
| Bee preview/staging | **IMPLEMENTED, FIXTURE TESTED** | `bee changed --json` is reduced to bounded fact/todo/conversation/journal summaries. Full transcripts, audio, locations, photos, credentials, and unrelated profile data are not uploaded. |
| Explicit Bee import consent | **IMPLEMENTED, LOCALLY TESTED** | Browser selects staged records and one owned expectation, confirms source binding, then imports. No evidence is persisted before this action. |
| Bee incremental sync | **MANUAL INCREMENTAL SYNC IMPLEMENTED** | The bridge passes the documented cursor to `bee changed --cursor ... --json` and advances it only after successful staging. No unattended scheduler is enabled. |
| Real Bee CLI data access | **BLOCKED / NOT VERIFIED** | `bee` is not installed and no Bee account was requested. Run the manual acceptance below with an authorized account. |
| Live Ring ingestion | **NOT IMPLEMENTED** | Product decision keeps Ring simulated for the hackathon. The UI and evidence provenance do not claim otherwise. |

## Official Bee CLI contract

The implementation follows the current [official Bee CLI reference](https://docs.bee.computer/docs/cli):

- npm package: `@beeai/cli`
- binary: `bee`
- installation check: `bee version --json`
- authentication: `bee login`, `bee status`, `bee logout`
- user/authentication readiness probe: `bee me --json`
- manual incremental retrieval: `bee changed --json` and
  `bee changed --cursor <cursor> --json`
- the next cursor is `meta.next_cursor`, as documented in
  [Agentic Sync](https://docs.bee.computer/docs/agentic-sync)

The official CLI also offers sync, streaming, proxy, and MCP modes. CountOn does
not expose `bee proxy`: Bee documents it as an unauthenticated localhost
development proxy that must not be made public. CountOn's bridge directly invokes
an allowlist of CLI commands and uploads only minimized previews. CountOn does not
claim that Bee provides a cloud OAuth account-linking flow.

## Architecture and security boundary

```text
Bee account
  -> official local `bee` CLI and its local authentication
  -> CountOn bridge (fixed commands; bounded JSON; no shell)
  -> short-lived pairing / hashed revocable CountOn connector token
  -> staged minimal summaries in PostgreSQL
  -> signed-in CountOn user previews and selects records
  -> explicit owned expectation/source binding
  -> normalized `LIVE_BEE_CLI` evidence
  -> deterministic evaluator
  -> evaluation history / deduplicated mismatch notification

Ring/Bee browser simulator
  -> Supabase bearer token
  -> dedicated authenticated simulator endpoint
  -> confirmed simulator source on owned expectation
  -> server normalization with `SIMULATED_*` identity
  -> deterministic evaluator
```

The connector token can only stage Bee candidates. It cannot list expectations,
bind a source, import evidence, evaluate records, or read user data. Those actions
require the user's Supabase session. Pairing codes are single-use, expire after 10
minutes, and are not stored in plaintext. Disconnect revokes the CountOn bridge;
the user separately runs `bee logout` to clear the Bee CLI session.

All Bee tables are owner-keyed, have composite owner foreign keys, are denied to
`PUBLIC`, `anon`, and `authenticated`, and remain server-only under Supabase RLS.
The migration is `b4819ac72e30_bee_cli_connector.py`. It has not been applied to
production by this work.

## Evidence contract

| Origin | `source` | Provenance | Outcome rule |
| --- | --- | --- | --- |
| Physical Ring | unavailable | unavailable | Not implemented. |
| Ring simulator | `ring_simulator` | raw payload always has `simulated: true` | Positive package detection may support a result. Non-detection lacks a boolean outcome and stays `UNKNOWN`. |
| Bee simulator | `bee_simulator` | raw payload always has `simulated: true` | Conversation confirmation describes the commitment, not fulfillment; it remains context. |
| Bee CLI | `bee` | `raw_data.provenance=LIVE_BEE_CLI` plus safe connection/record/category references | Conversation, journal, and fact summaries are context. An explicitly completed Bee todo may support a positive boolean outcome; an incomplete todo is not failure evidence. |

Every imported event retains an external record/version key, observation time,
ingestion time, confidence, expectation association, and source binding. Unique
constraints plus existing evidence/evaluation idempotency suppress replayed
evidence and duplicate mismatch notifications. Full conversations and audio are
not stored by default.

## User and local bridge flow

1. Sign in to CountOn and open **Connected Accounts**. Bee simulator availability
   is displayed separately from Bee CLI state.
2. On the computer that owns the Bee session:

   ```sh
   npm install -g @beeai/cli
   bee version
   bee login
   cd backend
   source .venv/bin/activate
   python -m app.integrations.bee.cli_bridge status
   ```

3. Create a single-use pairing code in Connected Accounts and run the displayed
   command using the actual CountOn API origin:

   ```sh
   python -m app.integrations.bee.cli_bridge pair \
     --api https://YOUR_COUNTOn_API_HOST \
     --code-stdin
   ```

   Paste the displayed one-time code into the hidden prompt. It is not placed in
   the process list or shell history.

4. Stage the next bounded change page:

   ```sh
   python -m app.integrations.bee.cli_bridge sync
   ```

5. Return to Connected Accounts, preview the staged summaries, select the exact
   records and owned expectation, and choose **Approve selected evidence import**.
6. Inspect the expectation evidence/evaluation history and notification inbox.
7. Disconnect in CountOn to revoke the bridge. Run `bee logout` separately if the
   Bee CLI session should also be cleared.

The local connector configuration is stored at `~/.counton/bee-connector.json`
with mode `0600`. It contains a CountOn connector token, never the Bee credential.
Do not copy it into the repository, browser environment, or chat.

## API surface

User-authenticated with the existing Supabase bearer token:

- `POST /api/v1/integrations/bee-cli/pairings`
- `GET /api/v1/integrations/bee-cli/status`
- `GET /api/v1/integrations/bee-cli/candidates`
- `POST /api/v1/integrations/bee-cli/imports`
- `POST /api/v1/integrations/bee-cli/disconnect`
- `POST /api/v1/simulators/ring/expectations/{id}/events`
- `POST /api/v1/simulators/bee/expectations/{id}/events`

Pairing and credential-scoped bridge operations:

- `POST /api/v1/integrations/bee-cli/pair` — valid single-use pairing secret
- `POST /api/v1/integrations/bee-cli/bridge/candidates` — CountOn connector bearer

The browser never receives the connector token and the bridge never receives a
Supabase access token.

## Validation

Executed locally:

```text
Focused backend connector/migration/simulator suite: 28 passed
Final relevant Bee/Ring/ownership/connected-account backend suite: 54 passed
Complete backend suite attempt: 1,295 passed, 8 failed (existing lease/expiry timing tests outside this connector); all 8 passed when rerun together in isolation
Ruff: passed
Mypy (`app`): passed, 155 source files
Frontend lint: passed
Frontend typecheck: passed
Frontend tests: 236 passed, 1 skipped
Frontend production build: passed
```

The complete backend run was not reported as passing: its time-sensitive monitoring
lease and durable-conversation expiry group failed late in the whole suite, then
all eight failures passed together in isolation without code changes. Tests cover
CLI absence, unsupported fixture schema, pairing
single use, invalid connector credentials, staged-record deduplication, cursor
checkpointing, explicit consent, wrong-user denial, source binding, minimized
evidence, revocation, Ring replay, Bee replay semantics, persistence, evaluation,
and migration/model agreement.

## Real-account acceptance still required

With an authorized Bee account, record and verify:

1. official CLI installation/version and successful `bee login`;
2. `bee me --json` succeeds without logging its output;
3. a one-time CountOn pairing succeeds and replay fails;
4. `bee changed --json` returns the documented shape;
5. only selected summaries appear in CountOn staging;
6. no transcript, audio, token, or unrelated record is persisted;
7. user-approved import creates `LIVE_BEE_CLI` evidence for the correct owner and
   expectation;
8. a promise stays `UNKNOWN`, while an explicitly completed applicable todo is
   evaluated by deterministic code;
9. cursor-based second sync does not duplicate evidence;
10. disconnect rejects the old connector token and `bee logout` clears the local
    Bee session.

Live Bee CLI, Bee account behavior, and physical Ring hardware remain external
acceptance gates. Fixture tests and simulators must not be presented as those
real-account results.
