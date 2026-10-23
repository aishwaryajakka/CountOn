# CountOn

CountOn is an expectation-monitoring system that remembers what you're counting on, watches evidence, and only interrupts when reality changes.

*Reminders remember what you need to do. CountOn remembers what you're counting on.*

## The problem

“My package should arrive Friday.” “My electricity bill should stay under $150.”
“The plumber said he'll come tomorrow.” These are expectations, not reminders.
Today, checking them means reopening email, calendars, bills, delivery pages and
messages. CountOn turns a stated expectation into something that can be checked
against authorized evidence. **Silence is success.**

## How CountOn works

**Expectation → Evidence → Evaluation → Exception**

| Evaluation | Meaning | Response |
| --- | --- | --- |
| MATCH | Observed facts satisfy the expectation. | Stay quiet. |
| UNKNOWN | Evidence is missing, unusable or insufficient. | Keep monitoring. |
| MISMATCH | Observed facts meaningfully differ from the expectation. | Create an in-app alert when enabled; explain on request. |

**AI understands and explains. CountOn decides.** Amazon Bedrock interprets
language and explains recorded mismatches. Deterministic Python code assigns the
final result. A promise is evidence of a commitment, not proof it was fulfilled.

## Architecture

```text
Alexa Custom Skill                       Web /alexa
  signed POST /api/v1/alexa                Next.js /api/agent
          \                                /api/v1/agent/converse
           +------ authenticated Trust Orchestrator ------+
                                  |
                       MCP Streamable HTTP /mcp
                                  |
                    CountOn services + PostgreSQL
                                  ^
     approved providers / DEMO evidence --> normalization
                                  |
                    deterministic evaluation
                     /            |            \
                  MATCH        UNKNOWN       MISMATCH
                  quiet        watching      notification
                                             grounded Why
                                             via Bedrock
Dashboard / detail / activity ------ FastAPI ------ same database
```

- **Web:** displays persisted expectations, evidence, results, notifications and audit history.
- **Alexa and orchestration:** resolve owned records, clarify language and request capture approval.
- **MCP:** exposes typed actions through existing services, with authenticated user context.
- **Backend and workers:** authorize sources, correlate evidence, evaluate and deduplicate delivery.
- **Bedrock:** supplies validated interpretations and evidence-grounded explanations.
- **PostgreSQL:** retains shared records, provenance and durable workflow state.

## Amazon Alexa+ / MCP

CountOn has a self-hosted Python MCP server using **Streamable HTTP**. All six
tools accept `{"request": {...}}`:

`capture_expectation` · `get_expectation` · `list_expectations` ·
`compile_expectation` · `continue_expectation_compilation` ·
`explain_expectation_mismatch`.

The `/alexa` web experience uses the same orchestrator, MCP tools and persistence
as the signed Alexa Skills Kit Custom Skill adapter. The browser sends language
to its authenticated server route; it cannot select arbitrary tools. MCP clients
initialize and discover tools through the real SDK. Transport tests explicitly
exercise protocol version `2025-06-18`; SDK package versions are separate.

The ASK adapter verifies signatures, timestamps and linked Supabase identity.
**Native Alexa+ MCP onboarding, live account linking and Echo acceptance are not
verified in the current repository.** Console setup and deployed model latency
remain external gates. An Agent Skill artifact is also included; it is an
instruction package, not an MCP App UI. See [MCP](docs/mcp.md),
[Alexa setup](docs/traditional-alexa.md) and [Agent Skill](docs/agent-skill.md).

## Amazon Bedrock

The trusted backend uses **boto3 Bedrock Runtime Converse** for expectation
compilation, stateful clarification and grounded mismatch investigation. Pydantic
models provide JSON Schema and strict output validation. Grounding checks reject
invented amounts and evidence references. JSON repair, selective retries,
timeouts, concurrency limits and token budgets are bounded; safe fallback speech
preserves the recorded evaluation when investigation is unavailable.

Bedrock is disabled by default (`BEDROCK_ENABLED=false`). The configured default
is `openai.gpt-oss-120b-1:0` in `us-east-2`; credentials use the AWS runtime provider
chain. Model access must be verified in the deployment account. Bedrock does not
choose the verdict, authorize users or write records directly. Source planning
and current email/calendar normalization are deterministic services. Details:
[Bedrock](docs/bedrock.md).

## Demo scenarios

Sign in and open `/demos`. Running a card creates a normal owned expectation and
explicitly approves its named demo evidence source.

| Scenario | Expectation and evidence | Expected demonstration |
| --- | --- | --- |
| **Electricity Bill Surprise** | “My next electricity bill should be below $150.” DEMO bill: **$180**. | **MISMATCH**; $30 over target, in-app notification and grounded Why. |
| **Package Arrived** | “My package should arrive by Friday.” Positive DEMO delivery confirmation plus **SIMULATED Ring** observation. | **MATCH**; no mismatch alert. |
| **Plumber Commitment** | “My landlord said the plumber will arrive Friday.” **SIMULATED Bee** commitment. | **UNKNOWN**; arrival remains unconfirmed. |

Simulators provide evidence only. Persistence, evaluation, notification logic,
and final MATCH / UNKNOWN / MISMATCH state are handled by the real CountOn backend.

Cards show actual saved IDs/results, provenance, notification status, audit history
and links to normal expectation details. Alerts respect user preferences. Package
success demonstrates a positive observation before the saved deadline; absence of
Ring detection never proves nondelivery. Generic temporal/event manual evaluation
remains UNKNOWN; supported worker deadline policies are documented separately.
See the [demo guide](docs/demo-guide.md).

## Tech stack

| Layer | Implementation |
| --- | --- |
| Frontend | Next.js App Router, React, TypeScript |
| Backend / MCP | FastAPI, Pydantic v2, Python MCP SDK 2.x |
| AI / voice | Amazon Bedrock Runtime, boto3, Alexa Skills Kit |
| Data / auth | PostgreSQL, SQLAlchemy, Alembic, Supabase Auth |
| Testing / delivery | pytest, Vitest, Testing Library, Playwright; Docker, GitHub Actions, Vercel configuration |

## Quick start

Prerequisites: Python **3.12** (container/CI baseline), Node.js **24**, npm,
Docker Compose and a Supabase Auth project. Local validation also uses Python 3.14. Configuration goes in ignored
`backend/.env.local` and `frontend/.env.local`. Use the templates and guidance in [setup](docs/setup.md).

```sh
# Repository root: local PostgreSQL
docker compose up -d

# Backend terminal, after configuring backend/.env.local
cd backend
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt -r requirements-dev.txt
alembic upgrade head
uvicorn app.main:app --reload
```

```sh
# Separate terminal: same backend environment and database
cd backend
source .venv/bin/activate
python -m app.mcp
```

```sh
# Frontend terminal, after configuring frontend/.env.local
cd frontend
npm ci
npm run dev
```

Open `http://localhost:3000`, FastAPI docs at `http://localhost:8000/docs`, and MCP
at `http://127.0.0.1:8003/mcp`. Authenticated business actions require a real
Supabase access token; there is no runtime authentication bypass. Conversational
capture also needs enabled Bedrock access and a private clarification signing key.
Evidence demos can use the deterministic explanation fallback.

## Testing

Use a separate loopback PostgreSQL database ending in `_test`; never application
or production data. Without `TEST_DATABASE_URL`, database tests skip.

```sh
cd backend
source .venv/bin/activate
python -m pytest -q --tb=short
```

```sh
cd frontend
npm test
npm run lint
npm run typecheck
npm run build
```

Production frontend builds require a public HTTPS `NEXT_PUBLIC_API_BASE_URL`.
[Testing](docs/testing.md) covers isolated configuration, smoke commands and
manual acceptance. Check current executed results there; mocked inference and
local fixtures do not prove live Alexa, OAuth or AWS behavior.

## Integration status

| Integration | Status | Notes |
| --- | --- | --- |
| MCP / PostgreSQL | Implemented | Six tools, shared owned records, migrations and local network tests. |
| Amazon Bedrock | Implemented — live config required | Compiler, clarification and investigator; genuine account/model acceptance remains separate. |
| Supabase Auth / Amazon sign-in | Implemented — live config required | Email/password flows and optional `custom:amazon` provider path; live provider/session acceptance required. |
| Alexa web simulator | Implemented | Shared server orchestration and persisted records. |
| ASK Custom Skill | Implemented — live config required | Signed adapter and interaction model; Console linking/voice/device acceptance pending. |
| Native Alexa+ MCP onboarding | Not verified | A working MCP endpoint alone does not establish onboarding or eligibility. |
| Gmail / Google Calendar | Implemented — live config required | Read-only OAuth, synchronization and confirmed source bindings. |
| Outlook / Microsoft Calendar | Implemented — live config required | Delegated OAuth, encrypted tokens and synchronization. |
| Ring / Bee demos | Simulated | Explicitly labeled observations; no live hardware claim. |
| Bee CLI bridge | Implemented — live config required | Optional, locally authenticated and consent-gated; real-account import not verified. |

## Security and trust

Supabase JWT verification and owned service queries bind actions to one CountOn
user. Alexa `userId` is a transport reference, never database identity. Production
conversation snapshots and OAuth credentials use encryption; audit metadata and
logs exclude tokens, raw model prompts and provider payloads. Ingestion minimizes
provider data, and simulations retain provenance. Rate limits and metrics are
process-local; deployment must account for that boundary.

## Documentation

[Product](docs/product-overview.md) · [Architecture](docs/architecture.md) ·
[Lifecycle](docs/expectation-lifecycle.md) · [MCP](docs/mcp.md) ·
[Bedrock](docs/bedrock.md) · [Integrations](docs/integrations.md) ·
[Demo guide](docs/demo-guide.md) · [Setup](docs/setup.md) ·
[Testing](docs/testing.md) · [Deployment](docs/deployment.md) ·
[Security](docs/security.md).

## License

Licensed under the Apache License 2.0. See [LICENSE](LICENSE).
