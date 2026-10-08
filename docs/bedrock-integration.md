# CountOn Bedrock intelligence integration

## Architecture and decision

The existing authenticated Streamable HTTP server cleanly supports typed tools.
Three high-level intelligence tools were added to MCP; the three original tools
retain their names, descriptions and contracts. No parallel intelligence REST
surface, direct browser Bedrock call, dashboard redesign or evaluator rewrite was
introduced. This keeps discovery and the judge trace consistent while making
**Bedrock interprets → MCP acts** visible as separate calls.

```text
User → /alexa → deterministic conversational router
                 │
                 ├─ list/detail → Next.js /api/mcp → Streamable HTTP → list/get
                 │
                 ├─ capture → /api/mcp → MCP compile_expectation
                 │                         → Bedrock compiler
                 │                         → signed clarification if needed
                 │                         → existing ExpectationCreate
                 │           → separate MCP capture_expectation → owned services
                 │
                 └─ why failed → list/match → MCP explain_expectation_mismatch
                                               → owned expectation
                                               → latest deterministic evaluation
                                               → bounded historical evidence
                                               → Bedrock investigator/fallback

MCP → CountOn services → PostgreSQL / Supabase
Dashboard → FastAPI → same PostgreSQL / Supabase
Evidence → deterministic evaluator → MATCH / UNKNOWN / MISMATCH
```

The audit covered the AI client/compiler/clarification/investigator, auth and
ownership services, evaluation/evidence APIs, MCP contracts/transport, Next.js
client/route, `/alexa`, normal API dashboard source and Agent Skill. Existing
layers are reused; orchestration and transport contracts are the added layer.

## MCP surface

Configured remote endpoint (verify deployed discovery before use):
`https://counton-mcp.7ak6j8v4ypay0.us-east-2.cs.amazonlightsail.com/mcp`.
Locally: `http://127.0.0.1:8003/mcp` by default. Every user-specific call uses the
existing Supabase bearer verifier and exactly `{"request": {...}}`.

| Tool | Request fields | Result / effect |
| --- | --- | --- |
| `list_expectations` | Existing pagination/status/type | Existing owned compact records; no Bedrock |
| `get_expectation` | Owned `expectation_id` | Existing compact record; no Bedrock |
| `capture_expectation` | Existing `ExpectationCreate` | Expectation mutation; same services/database; compiled ticket prevents replay |
| `compile_expectation` | `text` 1–2000, IANA `timezone` (default UTC), optional locale, `conversational`, stable `compilation_id` | Interpretation plus lifecycle ledger; never saves an expectation |
| `continue_expectation_compilation` | Actual signed `state`, `answer` 1–2000 | Clarifies/corrects/cancels; writes lifecycle state, never an expectation |
| `explain_expectation_mismatch` | Owned `expectation_id` | Real latest evaluation, grounded explanation or deterministic fallback |

Compilation returns `status` compiled/clarification/cancelled/expired/unsupported/error,
`message`, nullable `expectation`/`state`/`capture_state`/`code`, `bedrock_used`, `prompt_version`,
`clarification_turn`. Only `compiled` proceeds to a separate capture call.

Explanation returns actual `result`, nullable `evaluation_id`/`explanation`/`code`,
`message`, `expectation_id`, selected real `evidence_ids`, `bedrock_used`,
`fallback_used`. Provenance IDs are retained internally, not spoken. MATCH, UNKNOWN and NO_EVALUATION do not invoke the
investigator. Explanation never calls the evaluator or writes any result. It
returns historical expected/observed/threshold/reason snapshots, not values inferred
from a mutable current expectation.

Evidence reads happen only after ownership checks, with bounded pinned-record,
same-time peer and latest contributor queries, then the existing investigator's
as-of normalization. Sources/raw data/credentials are not sent to Bedrock. Possible
contribution is not causation, net effect or proof of matching billing periods.

## Conversation and failure behavior

List/detail stay deterministic; capture regexes choose intent only and produce no
static payload. Active clarification answers/corrections/cancellation go to the
continuation tool. List/detail can interrupt clarification without saving anything.
Trusted Next.js orchestration captures only the final validated structure. An ambiguous detail match asks
for specificity; a missing match never creates an expectation. Search currently
covers the first 50 records and discloses that limit.

Signed state contains no JWT, AWS data, credentials or stored principal ID. HMAC
binds it to the authenticated user. It is integrity protected, **not encrypted**;
it contains that user's private utterance/facts. Never log/echo the opaque state.
Production requires a shared signing secret on every MCP replica; development
uses a process-local random key, invalidated on restart. TTL, turn limits and
prompt-version checks reuse the clarification state machine. Rotate the key to
invalidate existing handles. Signed state is not authentication.
The `compilation_sessions` ledger holds canonical state, owner and latest token
digest. Continuations consume their handle; terminal/replaced/expired sessions
cannot be resumed. A stable `compilation_id` protects initial-request replay.
Only a compiled ticket plus its exact expectation payload can use replay-safe
capture: `capture_state` is supplied as `compilation_state`, and creation plus
stored expectation ID commits atomically. Replay returns the same owned row;
a deleted captured row is not recreated. Direct capture without a ticket remains
non-idempotent and is not automatically retried. No second state format is used.

Browser state stays in React memory: refresh/sign-out/user change starts a new
conversation, while previously captured rows persist in the normal dashboard.
The UI says “AI: Amazon Bedrock,” never “Bedrock connected.” Success traces require
actual tool results. MCP connectivity requires initialize and core discovery.

Errors remain distinct and calm: AUTH_REQUIRED/AUTH_EXPIRED, MCP_UNAVAILABLE/
MCP_PROTOCOL_ERROR, BEDROCK_DISABLED/UNAVAILABLE/THROTTLED,
COMPILER_INVALID_OUTPUT, CLARIFICATION_REQUIRED/EXPIRED/UNAVAILABLE,
UNSUPPORTED_EXPECTATION, NO_EXPECTATION, NO_EVALUATION, NO_EVIDENCE,
NOT_MISMATCH, INVESTIGATION_UNAVAILABLE and TOOL_VALIDATION_ERROR.
Bedrock failures cannot create guessed capture objects. List/detail remain usable;
investigation falls back to the deterministic evaluation summary.

Next.js generates a request UUID, forwards it to MCP and logs only safe operational
fields: initialize/discovery, tool, status, duration, compiler result, clarification
turn and Bedrock/investigator usage. MCP accepts only valid UUID correlation IDs.
Existing Bedrock telemetry supplies model, prompt version, token counts, latency
and bounded retry/repair metadata. No Authorization/JWT, prompts, raw sensitive
evidence, opaque state or provider exception content is logged.

## Production environment

Set these on the **MCP Lightsail container**, alongside its existing private
Supabase/auth/database settings. Backend `.env.local` is for local development.
Do not put AWS credentials in Vercel or frontend public variables.

| Variable | Value / default |
| --- | --- |
| `BEDROCK_ENABLED` | `true` to opt in; currently defaults false |
| `AWS_REGION` | Region supporting your chosen model/profile; normally `us-east-2` for this deployment |
| `BEDROCK_MODEL_ID` | Defaults to `openai.gpt-oss-120b-1:0`; override for another enabled model/profile |
| `COUNTON_CLARIFICATION_SIGNING_KEY` | Private random secret of at least 32 bytes; identical across replicas |
| `BEDROCK_MAX_TOKENS` | `1000` default; raise if the selected model truncates valid structured output |
| `BEDROCK_TEMPERATURE` | `0.1` default; compiler/investigator explicitly use zero |
| `BEDROCK_REQUEST_TIMEOUT_SECONDS` | `30` default |
| `BEDROCK_MAX_RETRIES` | `2` default |
| `BEDROCK_NATIVE_STRUCTURED_OUTPUT` | `false` default; opt in only with a supported model |
| `CLARIFICATION_MAX_TURNS` | `6` default, supported 1–12 |
| `CLARIFICATION_TTL_SECONDS` | `900` default |
| `INVESTIGATOR_MAX_EVIDENCE` | `6` default, max 12 |
| `INVESTIGATOR_MAX_PROMPT_BYTES` | `12000` default |

Generate the signing key **into a private environment/secret configuration**, not
terminal/chat output. Existing settings use `SecretStr` and ignored env files.
All Bedrock settings live on the service executing the MCP intelligence tools.
The separate FastAPI deployment continues its existing database/auth configuration.

Vercel production variables:

```text
NEXT_PUBLIC_API_BASE_URL=https://counton-api.7ak6j8v4ypay0.us-east-2.cs.amazonlightsail.com
NEXT_PUBLIC_SUPABASE_URL=<existing Supabase project URL>
NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY=<existing public publishable key>
COUNTON_MCP_URL=https://counton-mcp.7ak6j8v4ypay0.us-east-2.cs.amazonlightsail.com/mcp
```

`COUNTON_MCP_URL` is server-only. No AWS credentials, signing key, service-role key
or shared test token belongs on Vercel. The Next.js route uses Node with
`maxDuration=180`; its MCP request budget is also 180 seconds. Confirm the Vercel
project's function limits support this value; [Vercel duration configuration](https://vercel.com/docs/functions/configuring-functions/duration).
No vercel.json change is needed. No new browser CORS path was added.

## AWS permissions and credential delivery

Boto3's standard credential chain is reused. Local development can use authenticated
SSO/profile credentials (`aws sso login --profile YOUR_PROFILE`, then set
`AWS_PROFILE` privately). [Converse requires `bedrock:InvokeModel`](https://docs.aws.amazon.com/bedrock/latest/userguide/conversation-inference.html).
Grant it only for the selected permitted model/profile resources. Example policy
template for a directly invoked regional foundation model:

```json
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Action": "bedrock:InvokeModel",
    "Resource": "arn:aws:bedrock:us-east-2::foundation-model/SELECTED_MODEL_ID"
  }]
}
```

For an inference profile, add its ARN and the authorized destination foundation
model ARNs for its participating regions; use that profile ID/ARN as modelId.
[Inference-profile invocation](https://docs.aws.amazon.com/bedrock/latest/userguide/inference-profiles-use.html).
Enable any required model access/provider agreement and check region/quotas.
No model-list, Supabase-admin or Bedrock streaming permission is required.
An exact resource policy cannot be finalized until the model/profile is selected.

Do not assume the current Lightsail container has an EC2 instance role.
[Lightsail IAM guidance](https://docs.aws.amazon.com/lightsail/latest/userguide/security_iam.html)
does not establish application credentials for this deployment. If no supported
workload credential provider is configured, supply **rotated short-lived STS
credentials** privately to the MCP runtime using `AWS_ACCESS_KEY_ID`,
`AWS_SECRET_ACCESS_KEY`, `AWS_SESSION_TOKEN`, and refresh before expiry. Have a
trusted backend credential-delivery process obtain them from the least-privilege
role; the application does not mint credentials itself. Avoid committing deployment
JSON with those values or printing container environment/logs. A continuously
operated deployment needs automated refresh/a supported workload provider; static
copied STS credentials are only a temporary demo setup.

## Exact local commands

First configure ignored `backend/.env.local` / `frontend/.env.local` with the
settings above and secure credentials. Configure existing frontend auth/API
origins for loopback and MCP `COUNTON_MCP_URL=http://127.0.0.1:8003/mcp` locally.

Terminal 1 (from repository root):
```sh
docker compose up -d
cd backend
source .venv/bin/activate
python -m pip install -r requirements.txt
DATABASE_TARGET=local alembic upgrade head
DATABASE_TARGET=local uvicorn app.main:app --reload
```
Terminal 2:
```sh
cd backend
source .venv/bin/activate
DATABASE_TARGET=local python -m app.mcp
```
Terminal 3:
```sh
cd frontend
npm install
npm run dev
```
Checks from the root (privately set isolated loopback `TEST_DATABASE_URL` ending
in `_test`; never point the suite at production):
```sh
cd backend
source .venv/bin/activate
pytest -q
ruff check app/ai app/mcp/intelligence.py app/mcp/conversation_state.py \
  app/mcp/schemas.py app/mcp/http.py tests/test_mcp_intelligence.py \
  tests/test_mcp_network.py db/scripts/intelligence_smoke.py
mypy --strict --follow-imports=silent --ignore-missing-imports app/ai \
  app/schemas/compiler.py app/schemas/clarification.py app/schemas/investigation.py \
  app/services/compiler_service.py app/services/investigation_service.py \
  app/mcp/compiler.py app/mcp/intelligence.py app/mcp/conversation_state.py app/mcp/schemas.py
python db/scripts/bedrock_smoke.py --live
python db/scripts/intelligence_smoke.py --mcp-url http://127.0.0.1:8003/mcp
python db/scripts/intelligence_smoke.py --mcp-url http://127.0.0.1:8003/mcp \
  --api-url http://127.0.0.1:8000 --capture
cd ../frontend
npm run lint
npm run typecheck
npm run test
npm run build
```
Smoke scripts require a real token in private `COUNTON_TEST_ACCESS_TOKEN` or
`COUNTON_ACCESS_TOKEN`; they never print it. `--compile` opts into inference without
saving; `--capture` compiles, captures one uniquely tagged row, cross-checks API
persistence and cleans only exact matching tagged rows, including recovery of a
lost capture response. Cleanup failure exits nonzero for dedicated-account review.

## Exact production checks

Redeploy the MCP backend image with the required backend environment/IAM settings,
and redeploy the frontend. Apply `alembic upgrade head` first: the existing
`6e302a79bd01` migration adds `compilation_sessions` for durable continuation/capture
replay protection. Then, from `backend` with a securely supplied real test token:

```sh
python db/scripts/bedrock_smoke.py --live
python db/scripts/intelligence_smoke.py \
  --mcp-url https://counton-mcp.7ak6j8v4ypay0.us-east-2.cs.amazonlightsail.com/mcp
python db/scripts/intelligence_smoke.py \
  --mcp-url https://counton-mcp.7ak6j8v4ypay0.us-east-2.cs.amazonlightsail.com/mcp \
  --api-url https://counton-api.7ak6j8v4ypay0.us-east-2.cs.amazonlightsail.com --capture
```
The first command validates the configured environment where it runs; run it on
trusted backend infrastructure to verify production AWS credentials. The remaining
commands probe the deployed MCP service. Browser E2E from `frontend`:

```sh
COUNTON_ALEXA_BASE_URL=https://counton-frontend.vercel.app \
COUNTON_E2E_API_BASE_URL=https://counton-api.7ak6j8v4ypay0.us-east-2.cs.amazonlightsail.com \
node tests/alexa-live.mjs
```
Privately supply `COUNTON_E2E_EMAIL` and `COUNTON_E2E_PASSWORD` first. The browser
script sends a tagged **utterance through the compiler**, checks capture/handoff,
refresh/shared persistence and exact returned-row cleanup. It does not patch a
static capture object. Use a dedicated test account and follow cleanup failures.

Manual production acceptance at `https://counton-frontend.vercel.app/alexa`:

1. Sign in. Ask “What am I counting on?”; verify actual records and list trace.
2. Ask “Tell me about my electricity bill”; verify list/get with a real UUID.
3. Ask the grocery `$120 this week` capture; see Bedrock compile then separate MCP
   capture. Follow “View in CountOn,” refresh and verify the same row/target.
4. Start “I'm counting on my bill being lower”; answer subject/reference/amount.
   Verify no row is saved until complete. Test “Never mind” and an explicit
   correction during clarification; refresh clears only the conversation.
5. Ask why a real electricity expectation failed; compare returned recorded
   expected/observed with its actual evaluation. Retain explanation caveats.
6. Repeat for MATCH, UNKNOWN and no evaluation; no investigator is invoked.
7. Disable Bedrock in a controlled test deployment: list/detail still work,
   capture refuses to guess and mismatch retains its deterministic summary.
8. Use another account to confirm explanation/state cannot cross ownership.

## Judge demos

**60 seconds:** 0–10s introduce quiet monitoring and sign in; 10–20s list actual
expectations with the MCP trace; 20–40s capture the grocery limit, point out separate
Bedrock compile and MCP capture; 40–50s open/refresh the normal CountOn record;
50–60s explain one pre-existing real mismatch and its evidence/causality caveat.
Use prepared real demo data and a ready authenticated deployment.

**2 minutes:** 0–20s list/detail; 20–45s grocery capture and dashboard refresh;
45–80s ambiguous bill → clarification, explicit correction before completion,
then cancellation of a separate draft without saving; 80–110s compare a real
MISMATCH explanation with MATCH/UNKNOWN responses; 110–120s show subtle traces
and explain that AI never changes deterministic evaluation. Successful monitoring
stays quiet; no provider ingestion or notification delivery is claimed.

## Validation and blockers

Implementation tests exercise real MCP/service/database paths with mocked inference.
They do not establish live model quality or production rollout. Run the commands
above against the current checkout; the latest test results belong in validation
reports rather than fixed historical counts here.

The configured Lightsail/Vercel addresses are deployment targets. This cleanup
does not inspect or redeploy them. Confirm all six discovered tools, the current
migration, backend signing key, enabled Bedrock/model configuration and valid AWS
runtime credentials, then run live compilation/clarification/capture/explanation
acceptance before claiming production intelligence readiness.

Intentionally deferred: arbitrary intent classification, evidence/evaluate/update/
resolve MCP tools, Ring/Bee/provider ingestion, workers, notification delivery,
cache infrastructure and real Alexa/Echo account linking. Conversation state is
already durable; automatic ledger retention/cleanup remains operational work.

## Natural Why? acceptance

The simulator routes “Why did my electricity expectation fail?”, “Why was my bill
higher?” and contextual “Why didn't this match?” through the existing explanation
tool. Ambiguous owned matches ask for a more specific claim; a contextual pronoun
requires a real previously viewed/captured expectation. No match is reported
without inventing a record. Speech uses only the server's concise message.
The latest recorded result gates investigation, even if an older result was a
MISMATCH. Bedrock never selects an outcome, fabricates evidence or writes state.
Real Alexa/Echo integration is not claimed.
