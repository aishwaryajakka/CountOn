# Architecture

## High-level architecture

```text
Signed Alexa ASK request                 Authenticated Web /alexa
POST /api/v1/alexa                       Next POST /api/agent
signature + linked JWT                  FastAPI POST /api/v1/agent/converse
             \                          /
              AgentOrchestrator + owned conversation state
                                 |
                    StreamableMcpAdapter (Python client)
                                 |
                    authenticated MCP HTTP /mcp
                                 |
                    canonical services / repositories
                                 |
                              PostgreSQL
                                 ^
approved OAuth sources -> provider sync -> confirmed source binding
simulator/manual API -------------------> normalized evidence
                                 |
                    evaluation_service / monitoring worker
                                 |
                   Evaluation + inbox + audit in SQL
                                 |
           normal FastAPI reads -> dashboard / detail / activity
```

The code entrypoints are `backend/app/main.py`, `backend/app/mcp/server.py` and
`frontend/app/`. FastAPI mounts versioned routers at `/api/v1`. The separate MCP
ASGI application uses the same models and services; there is no Alexa database.

## Components

### Frontend

Next.js App Router renders server-owned data through `frontend/lib/api.ts`.
Supabase Auth handles user sessions; authenticated API reads use `no-store`.
`/alexa` sends utterances/opaque references to a bounded Next server route. Its
`/api/mcp` browser route permits tool discovery only. It cannot execute arbitrary
tools, write directly to Supabase tables, or calculate evaluation outcomes.
Presentation arithmetic such as dollars over a target is not an evaluator.

### Alexa / conversational interface

`app/api/v1/alexa.py` accepts signed ASK envelopes, validates certificate/signature,
timestamp and Skill ID, then verifies the linked Supabase access token. The token's
UUID `sub` supplies CountOn identity; Alexa `userId` scopes transport state only.
The adapter converts known intents into input for the same orchestrator. Its
interaction model and code are implemented; Console/OAuth/Echo acceptance is not
verified. See [traditional Alexa](traditional-alexa.md).

### Trust orchestrator

`app/agent/orchestrator.py` defines `AgentOrchestrator`. Its bounded capabilities
are list, get, compile, continue clarification, capture, explain and cancel.
Cancellation terminates a draft, not an arbitrary saved record. Typed plans,
owner rechecks, confirmation, execution budgets and source policy constrain calls.
The coordinator is deterministic Python, not a separate model-driven agent.

`AgentSessionState` retains a selected expectation, signed clarification or capture
reference, bounded disambiguation IDs, version and expiry. Memory storage is for
development; production requires the encrypted PostgreSQL conversation store.
The compilation ledger is separate JSON state, not an encrypted conversation row.
See [security](security.md) for that distinction.

### MCP

`app/mcp/tools.py` registers six typed tools. Each accepts exactly one top-level
`request` argument. `StreamableMcpAdapter` initializes a real SDK client and invokes
the same MCP boundary for both conversational transports. MCP performs CountOn
actions, not independent business-rule or schema implementations. [Contracts](mcp.md)
specify inputs, outputs, authorization and replay limits.

### Backend

FastAPI dependencies verify identity before services perform owned queries.
Repositories contain persistence operations. `expectation_service`,
`evidence_service` and `evaluation_service` are canonical domain entrypoints.
`notification_service` persists inbox records; `audit`/`operations` append safe
lifecycle events. Schema creation belongs to Alembic.

`investigator_service.py` loads an owned expectation/latest evaluation/evidence;
`investigation_service.py` runs the typed explanation operation. These are
different responsibilities, not duplicate investigator implementations.

### Amazon Bedrock

Only the compiler, clarification engine and mismatch investigator call the shared
`BedrockClient`. They use boto3 Converse, typed schema validation and grounding.
Source planning and current email/calendar fact extraction are deterministic.
Bedrock has no database-write authority. [Bedrock reference](bedrock.md).

### Deterministic evaluator

`app/evaluators/numeric.py` and `boolean.py` implement direct comparisons.
`evaluation_service` records their output and performs notification/audit writes.
The manual generic temporal/event evaluator returns UNKNOWN.

`app/monitoring/evidence.py` adds narrower worker policies: approved bindings,
freshness, occurrence/correlation identity, conflicts and supported deadline or
mailbox-coverage checks. This is not universal temporal inference. Absence can
justify a missed-reply rule only with the required complete synchronized coverage.
Ring absence and Bee promises cannot substitute for outcome evidence.

### PostgreSQL / Supabase

SQLAlchemy models share PostgreSQL tables for expectations, evidence, evaluations,
notifications, audit, connections and workflow state. Supabase Auth provides the
identity UUID; hosted PostgreSQL is selected independently through settings.
Composite owner constraints, RLS migrations and application ownership checks have
different roles. Trusted backend database roles still require service authorization.

## Request flow

1. Authenticate at the transport boundary.
2. Compile/clarify without creating an expectation row.
3. Require approval in web conversation and configured production ASK.
4. Capture with the compiler ticket through MCP; atomically record the row and
   durable capture receipt. A matching ticket replay returns the same owned row.
5. Reload via ordinary FastAPI reads. Direct structured API/MCP capture remains a
   supported path; it is not automatically compiler-ticket-idempotent.
6. Propose and confirm authorized monitoring sources separately.

## Evaluation flow

Evidence → normalization → relevance/permission checks → deterministic evaluator
→ persisted Evaluation/status → eligible notification/audit → on-demand explanation.

Provider sync and monitoring run as separate worker processes with durable leases,
fencing, retries and deduplication. Encrypted source projections/checkpoints support
restart recovery. Normalized evidence ingestion can wake existing monitoring jobs;
it does not silently enroll an unrelated source. Dedicated simulator endpoints
persist and evaluate synchronously. Generic evidence submission and evaluation are
separate API operations.

## Separation of responsibilities

AI handles language interpretation and explanation. The CountOn backend owns
evaluation and persistence. Database constraints reinforce ownership/idempotency.
The UI displays those records. Public endpoints, deployed credentials and healthy
model access must be verified separately; source code alone proves none of them.
