# CountOn Person 1 — Alexa ASK, MCP, simulators, orchestration and demo

## Verified scope

- **REAL voice:** Alexa Skills Kit (ASK) Custom Skill on an Alexa device, subject to console/account-linking and device acceptance.
- **NOT VERIFIED:** Native Alexa+ MCP onboarding. No Alexa+ developer-console access; do not label ASK as Alexa+ MCP.
- **SIMULATED:** Ring and Bee. Simulator events are tagged and must use the same authenticated evidence API, database and deterministic evaluator.
- **Existing implementation:** Six MCP tools, Streamable HTTP, ASK signed HTTPS adapter, Supabase-linked auth, source planning, Bedrock orchestration, PostgreSQL conversation storage, and Ring/Bee simulator utilities. Reuse them; do not create new agent frameworks or extra MCP tools simply for a demo.

## First: repository preflight and local regression

Run from repository root:

```bash
python scripts/person1_preflight.py
cd backend
# Configure DATABASE_TARGET=local and LOCAL_DATABASE_URL for isolated PostgreSQL tests.
python -m pytest -q tests/test_alexa.py tests/test_alexa_dependencies.py tests/test_mcp.py tests/test_mcp_network.py tests/test_mcp_remote.py tests/test_mcp_intelligence.py tests/test_orchestration_eval.py
```

Some test modules require the project's configured isolated PostgreSQL test database. A test run without that environment does not establish acceptance.

Before any deployment, review `docs/traditional-alexa.md`, `docs/production-readiness.md`, `backend/alexa.env.sample`, and `backend/production.env.sample`.

## P0: Live ASK checklist (manual account access required)

- [ ] Sign in to the **standard Alexa Developer Console**: https://developer.amazon.com/alexa/console/ask (not the Alexa+ console).
- [ ] Create/open CountOn **Custom Skill**, locale `en-US`, invocation `count on`.
- [ ] Import `backend/app/alexa/interaction-model.en-US.json`, save and build the interaction model.
- [ ] Deploy current FastAPI backend publicly on HTTPS; confirm `GET /health` and `GET /ready` are both HTTP 200: `python scripts/person1_preflight.py --api-origin https://YOUR-API-HOST`.
- [ ] Configure ASK **HTTPS endpoint**: `https://YOUR-API-HOST/api/v1/alexa`, **not** `/mcp` and not the Next.js `/alexa` simulator.
- [ ] Copy the exact ASK Skill ID into server-only `ALEXA_SKILL_ID` and redeploy. Never put secrets in Git.
- [ ] Enable Supabase OAuth server and register a confidential ASK OAuth client, PKCE S256 and exact Alexa redirect URIs; verify `docs/traditional-alexa.md` account-linking requirements.
- [ ] Set server-only `ALEXA_OAUTH_CLIENT_ID`, `OAUTH_ALLOWED_CLIENT_IDS`, persistent PostgreSQL conversation storage, and private signing/encryption keys. The OAuth access token must pass existing JWT ownership verification without weakening checks.
- [ ] Enable **Development** testing; successfully link a dedicated test CountOn account using the Alexa app.
- [ ] Test Launch, Capture, clarification, confirmation, List, Get, Why, Help, and Cancel in the developer simulator.
- [ ] Test on a real Echo registered to the same eligible Amazon developer/test account. Confirm spoken wording, ASR, latency and record persistence. Live acceptance remains pending until this happens.
- [ ] Validate that unsigned/invalid ASK requests fail, expired linking does not access data, and retries do not duplicate a capture.

**STOP/BLOCKED:** Without a standard Alexa Developer Console account, skill creation/build/test cannot be completed here. Alexa+ developer access is a *separate* blocker and is not needed for this ASK path.

## P0: MCP, orchestration and shared database

- [ ] Run the real MCP service configured with auth and persistence (`python -m app.mcp` from `backend` using documented environment settings).
- [ ] Discover exactly six tools by MCP initialize/list-tools, not by replacing MCP calls with REST.
- [ ] Verify anonymous, expired, and cross-user bearer tokens are rejected.
- [ ] Run compile -> clarify -> confirmed capture -> owned list/get with one user; check the same SQL record appears on web after refresh.
- [ ] Run the stored-evidence MISMATCH -> grounded explanation flow; verify MATCH/UNKNOWN never trigger contradiction explanation.
- [ ] Test duplicate requests and service restart. No second expectation, duplicate notification or leaked user context.
- [ ] Record safe identifiers and result statuses; never paste secrets, JWTs, raw private emails or account credentials into logs/submission.

## P0: Ring/Bee simulator integration

- [ ] Ring event produces **SIMULATED** `ring_simulator` evidence bound to the exact authorized, compatible expectation.
- [ ] Bee event produces **SIMULATED** `bee_simulator` evidence bound to the exact authorized, compatible expectation.
- [ ] Persist both through authenticated CountOn APIs and display actual backend evaluation, not hard-coded MATCH/MISMATCH text.
- [ ] A missing package observation alone results in UNKNOWN, not proof of nondelivery.
- [ ] A Bee conversation promise alone is not proof an appointment happened.
- [ ] Replay the same source event: no duplicate evidence or alert.
- [ ] Confirm MATCH silence, UNKNOWN waiting, MISMATCH notification when actual evidence warrants it.

## P1: Multi-agent orchestration — only missing integration, not a rewrite

- [ ] Confirm shared compiler, source planner, grounded investigator and explanation use existing Pydantic contracts.
- [ ] Preserve user approval of sources, scoped tokens, model limits/timeouts, trace IDs, bounded retries and deterministic evaluation authority.
- [ ] Run three synthetic end-to-end journeys: bill mismatch, delivery with Ring simulator, landlord/Bee simulator context.
- [ ] Do not add independent AI verdict writers, privileged free-form agents, or new MCP tool contracts without a demonstrated integration gap.

## Final acceptance and handoff

- [ ] Alexa voice -> CountOn compiled expectation -> explicit confirmation -> PostgreSQL -> web dashboard.
- [ ] Authorized email/calendar evidence (Person 3) or explicitly simulated Ring/Bee event -> matching -> evaluator -> appropriate silent/notify outcome.
- [ ] Real Bedrock invocation and grounded explanation (Person 2).
- [ ] Connected Accounts, evidence and timeline correctly shown in web app (Person 4).
- [ ] Hosted CI, readiness, secret scans and end-to-end smoke pass on actual deployed commit.
- [ ] Demo video <= 3 minutes with spoken disclaimer for simulated evidence and ASK vs Alexa+ distinction.

**Unverified from this snapshot:** skill configuration in your Amazon account, registered OAuth client, real Echo, hosted credentials, current CI state and current deployment. Completing those requires authorized account/device actions and cannot be established by code inspection.
