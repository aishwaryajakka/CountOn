# Integrations

This is the current integration matrix. IMPLEMENTED describes code and local
contracts; LIVE CONFIG REQUIRED identifies a deployment/account prerequisite.
NOT VERIFIED is a live-acceptance statement, not a synonym for missing code.
Python `app/...` references below are beneath `backend/`; frontend paths start
at the repository root.

| Integration | Purpose | Implementation | Live credentials required | Simulation available | Current status | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| Web conversation | User capture, reads and Why | `frontend/app/alexa`, `/api/agent`, `app/agent` | Supabase session; AWS for language inference | Isolated tests | IMPLEMENTED | Uses the same services/database as dashboard. |
| MCP | Typed authenticated actions | `backend/app/mcp`; six registered tools | Supabase access token | Local network fixtures | IMPLEMENTED | Real Streamable HTTP; deployed surface must be probed separately. |
| Alexa Custom Skill | Signed voice transport | `app/alexa`, `app/api/v1/alexa.py` | ASK Skill ID, registered Supabase OAuth client, linking | Signed request fixtures | LIVE CONFIG REQUIRED | Console/real account/Echo recognition is NOT VERIFIED. |
| Native Alexa+ MCP onboarding | Hosted add-on registration/discovery | Existing MCP surface is a foundation | Developer/track access and compatible onboarding | `/alexa` is not native onboarding | NOT VERIFIED | CountOn does not implement MCP-hosted OAuth resource metadata. |
| Amazon Bedrock | Compile, clarify, explain confirmed mismatch | `app/ai/bedrock_client.py` and typed specialists | AWS model access and runtime credential provider | Mocked runtime/fallback | LIVE CONFIG REQUIRED | It never supplies the final evaluator verdict. |
| PostgreSQL / Supabase database | Shared persistence and durable jobs | SQLAlchemy models, Alembic chain | Configured database; TLS in production | Local PostgreSQL | IMPLEMENTED | Supabase Auth identity is separate from database hosting selection. |
| Supabase Auth | Signup/login, confirmation, reset, refresh, JWT identity | `frontend/lib/auth`, auth pages; `app/core/auth.py` | Project configuration and real user | JWT/Auth fixtures | LIVE CONFIG REQUIRED | CountOn does not store user passwords or issue its own sessions. |
| Login with Amazon | Optional sign-in/provider linking | Supabase `custom:amazon`; `/api/v1/auth/amazon/userinfo` | Compatible custom OAuth2 configuration, Amazon Security Profile | Provider-response fixtures | LIVE CONFIG REQUIRED | Translator returns stable subject only. Actual Amazon-to-Supabase session is NOT VERIFIED. |
| Gmail | Authorized read-only email facts | `app/integrations/accounts.py`, provider sync/normalization | Google OAuth and consent | Sanitized provider fixtures | LIVE CONFIG REQUIRED | Incremental sync/checkpoints, exact source permissions; no attachment archive. |
| Google Calendar | Selected calendar facts | Same provider framework | Google OAuth and chosen calendar | Sanitized provider fixtures | LIVE CONFIG REQUIRED | No universal recurring-rule expansion or attendance proof. |
| Outlook | Delegated read-only email facts | Microsoft OAuth/Graph, provider sync | Entra application, delegated consent | Sanitized provider fixtures | LIVE CONFIG REQUIRED | Tokens/checkpoints encrypted; permission failures stop unsafe use. |
| Microsoft Calendar | Selected Graph calendar facts | Same Microsoft/provider framework | Entra calendar permissions and consent | Sanitized provider fixtures | LIVE CONFIG REQUIRED | Event state and actual real-world attendance remain distinct. |
| Amazon order email | Shipping/order facts from approved inbox | Existing deterministic normalizer and correlation | Authorized Gmail/Outlook source | DEMO/provider fixtures | LIVE CONFIG REQUIRED | Login with Amazon does not grant shopping history. |
| Direct consumer Amazon orders API | Unrestricted retail history import | No verified implementation | Separate officially supported access would be needed | None claimed | OUT OF SCOPE | Do not substitute Amazon identity for orders authorization. |
| Ring simulator | Package/doorbell/motion observations | `app/integrations/ring`, `/api/v1/simulators/ring/...` | CountOn user and declared simulator source | Yes | SIMULATED | Backend stamps SIMULATED_RING; no-detection is not nondelivery. |
| Live Ring hardware | Real device ingestion | No verified device connection path | Independent provider/device authorization | Separate simulator | OUT OF SCOPE | Generic adapter code is not proof of live device access. |
| Bee simulator | Promise/conversation context | `app/integrations/bee`, `/api/v1/simulators/bee/...` | CountOn user and declared simulator source | Yes | SIMULATED | Context/confirmed promise is not an observed outcome. |
| Bee CLI bridge | Optional selected local imports | `cli_bridge.py`, `bee_connector_service.py` | Independently authenticated Bee CLI, CountOn pairing/consent | Sanitized CLI fixtures | LIVE CONFIG REQUIRED | Real account retrieval/import is NOT VERIFIED; credentials remain local. |
| In-app notifications | Persisted user attention inbox | Notification service/models/API | Same CountOn identity/database | Real local SQL tests | IMPLEMENTED | Deduplication and preferences; MATCH produces no mismatch alert. |
| Email notifications | Optional outbox delivery | `app/notifications`, Resend/SMTP configuration | Verified destination/sender and sending service | Mock transport tests | LIVE CONFIG REQUIRED | Implemented delivery pipeline; actual recipient acceptance is NOT VERIFIED. |
| Proactive Alexa notifications | Unsolicited device delivery | No verified implementation | Platform approval/capability would be needed | None | OUT OF SCOPE | An in-app alert does not imply an Echo announcement. |

## User and permission contract

Every connection belongs to the verified CountOn user. Public connection metadata
describes provider, connection type/status, scopes, sync timestamps and safe failure
state; encrypted credentials reside separately. A connected metadata row does not
establish usable provider access.

The source planner proposes eligible sources from actual owned, authorized,
synchronized connections. Preview is not a grant. Confirmation binds the expectation
to a narrow matching rule. Sync, correlation and evaluation recheck source status,
generation/scopes and ownership. Disconnect/revocation prevents subsequent authorized
imports; history remains distinct from permission to fetch again.

Gmail/Outlook/Calendar setup and callbacks are documented in
[provider acceptance](integrations-acceptance.md). Legacy compatibility URLs delegate
to the same account authority; they are not a second OAuth implementation.

## Bee and Ring boundaries

The local Bee bridge invokes a fixed CLI argument set, detects version/auth readiness,
pairs using a short-lived one-use code and receives a scoped revocable connector
credential. It submits bounded preview candidates; the signed-in user chooses import
and the owned expectation. CountOn Amazon/Supabase login does not authenticate Bee.
Do not expose a public unauthenticated local proxy. The current commands and manual
provider acceptance remain in [Bee/Ring integration](bee-ring-integration-acceptance.md).

Ring/Bee simulators remain independent of live account setup. Their event IDs and
provenance survive normalized persistence and backend evaluation. The API does not
allow simulator content to change a verdict or select another user's expectation.

## Current evidence processing

Email/calendar facts are extracted by bounded deterministic normalization, with
stable provider identity/version and exact occurrence correlation. This is not a
general model-driven email agent. Bee suggestions and source-plan review are narrower
than a universal recommendation system. Worker operation, retention and retry
boundaries are covered by [monitoring](monitoring.md), [automatic tracking](automatic-tracking.md)
and [data policy](data-minimization-and-audit-policy.md).
