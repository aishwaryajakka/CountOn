# CountOn consolidation inventory — 2026-10-23

This inventory was written before application files were changed. The source is
five user-supplied ZIP snapshots, compared by normalized path and SHA-256 with
current commit `8d4b72f` on `feature/alexa-mcp`. The initial worktree was clean.
`backup/pre-consolidation-2026-10-23` preserves that commit; consolidation occurs on
`integration/counton-canonical`. No commit, push, deployment, or production
migration is authorized.

Archive directories, macOS metadata, build/cache output, and non-template env
files are excluded from project comparison. No credentials are imported.

## Before-merge inventory

| Subsystem | main archive | Alexa/Ring archive (one identical source) | Backend archive | Bedrock archive | Proposed winner |
|---|---|---|---|---|---|
| MCP | Older core surface | Six nested-request tools, Streamable HTTP, auth | Older core | Older/parallel intelligence | Current six-tool server; preserve transport/auth |
| Alexa | Earlier web path | ASK signature/replay/account-linking adapter and web simulator; frontend explanation deep links | Earlier web | Earlier web | Current ASK/orchestrator; selectively port owned explanation context |
| Bedrock | Parallel AI files | Current compiler/clarification/investigator plus changed disabled-model fallback | Earlier core | Alternate compiler/investigator/schemas, mock context extraction and UTC default parser | Current typed, grounded implementation; no second client/compiler |
| Evaluator | Core deterministic model | Current evaluator unchanged; additional numeric regression tests | Core semantics reference | Parallel AI-side result models | Current deterministic evaluator and ownership; additive reference tests only |
| OAuth/integrations | Separate `oauth_credentials`/`oauth_states`, calendar storage, sync-health/delivery services | Current encrypted grants, PKCE, scoped sync, fencing, lease/backoff, minimal projections | Earlier connection model | Alternate connector helpers | Current one connection/grant/sync path; map main behavior to existing equivalents |
| Ring/Bee | Earlier adapters | Simulator/API/UI; optional local Bee CLI | Earlier adapters | Additional context mocks | Current privacy-preserving adapters and bridge; compatible frontend work |
| Frontend | Older dashboard; quality page depends on seeded global stores | New criteria builder, reality/resolution cards, source management and tests; fake AI suggestions also present | Earlier dashboard | Duplicate `app/lib` and mock quality pages | Selective Alexa/Ring UI, preserving current audit and auth; reject fabricated records/claims |
| Migrations | Two extra branches from `5d201f68ac90`; duplicate OAuth schema creation | Same 13-revision chain as current | First five revisions | First five revisions | Current linear chain through `d6a71c9e24f0`; do not activate incompatible histories |
| Agent | Older/experimental variants | Existing controlled orchestrator | Earlier surface | Alternate helpers | Current constrained orchestrator; no new agent framework |
| Dependencies/env | Adds Google SDK/alternative crypto settings for duplicate services | Same package/lock dependencies as current | Older pins | Older SDK/mock dependencies | Current audited dependency and root-ignore setup |

## File comparison

| Snapshot | Project files | Identical to current | Different at same path | Snapshot-only | Current-only |
|---|---:|---:|---:|---:|---:|
| main | 238 | 64 | 115 | 59 | 273 |
| Alexa | 462 | 420 | 32 | 10 | 0 |
| Ring/Bee | 462 | 420 | 32 | 10 | 0 |
| backend | 179 | 65 | 112 | 2 | 275 |
| Bedrock | 298 | 107 | 136 | 55 | 209 |

Alexa and Ring/Bee have identical file sets and file bytes after normalization.
Current code already includes all 452 tracked project files represented in that
shared archive except its ten additions. The original ZIPs remain untouched.

## Main behavior reconciliation

| Main-only behavior/path family | Current implementation retained | Decision |
|---|---|---|
| `api/v1/oauth.py`, `*oauth*`, `*token*`, OAuth models/repositories | `api/v1/provider_oauth.py`, `integrations/accounts.py`, `integrations/microsoft.py`, `IntegrationCredential`, `ProviderOAuthState` | PKCE, encrypted rotating grants, identity/scope verification, owner constraints and revocation already exist. No duplicate token authority. |
| `gmail_service.py`, `google_calendar_service.py`, `microsoft_*service.py`, `outlook_sync_service.py`, `api/v1/calendar.py` | `integrations/adapters.py`, `normalization.py`, `worker.py`, provider-sync/source-plan APIs | Incremental selected-stream sync, exact source correlation and privacy boundaries supersede raw message/calendar listing and archive tables. |
| `integration_retry.py`, `integration_sync_health.py` | ProviderSyncState, worker leases/retry/backoff/safe errors; connection lifecycle metadata | Existing durable system covers those capabilities. |
| `notification_delivery_service.py`, repository and `email_delivery.py` | `notifications/worker.py`, `notifications/delivery.py`, delivery models and notification service | Current durable delivery/outbox supports idempotency, restart fencing, encrypted recipients and bounded retry. |
| `supabase_user_service.py` | Existing JWT verifier/profile repository and API ownership | Preserve Supabase identity without a competing client/session authority. |

## Migration collection and decisions

All source migration files were collected in an external temporary review tree,
not installed into the application migration directory. The original ZIPs preserve
all historical artifacts; none were deleted or renumbered.

Main diverges at `5d201f68ac90`:

```text
5d201f68ac90 -> f7a9c2d1b640 -> 298fc0cf83dc -> 70e96a04757b
             -> 8b10af011a55 -> 501e82ab1613 -> e8b2dc123ad7
                -> 4c35f2c88019 -> 07bc7f5ce116 -> e5e411421101
```

- `f7a9c2d1b640` and `e8b2dc123ad7` both create `oauth_credentials` using
  different ORM layouts; `f7a9c2d1b640` and `4c35f2c88019` also create competing
  OAuth-state schemas. These are incompatible alternative implementations.
- `07bc7f5ce116` creates `notification_deliveries`, already created by canonical
  `ac746eb3f145` with a different durable-delivery contract. Adding a merge revision
  would not resolve duplicate table creation.
- `8b10af011a55` makes monitoring expectation ownership nullable; current monitoring
  deliberately requires an owned expectation. It is not a compatible additive change.
- `501e82ab1613` adds duplicate-monitoring protection already covered by the current
  active-expectation unique index. `298fc0cf83dc` adds a parallel sync-health state
  machine already handled by canonical worker state/lifecycle fields.
- `70e96a04757b` adds general calendar-event persistence. Canonical authorized,
  bounded encrypted fact projections and normalized evidence satisfy monitoring
  without a separate provider calendar archive.
- `e5e411421101` depends on the rejected alternative delivery queue.

Retain current 13 migrations unchanged. Databases already stamped with any of the
main-only revision IDs require a separately reviewed data/credential migration;
**do not stamp them to the canonical head or run this history against them**.
Only isolated local test databases are used during consolidation validation.

## Planned application changes

Port compatible frontend source-management, explanation navigation, criteria and
result-display components/tests from the shared Alexa/Ring source. Preserve the
current six-column minimized Audit History and all existing auth/security tests.
Exclude static AI recommendations/suggestions that claim to come from connected
accounts or Bedrock without actual calls. Port no archived backend subsystem
wholesale. Any backend edits are limited to the authenticated explanation-context
contract needed by those existing frontend links, with ownership regression tests.

Resolution details, exact imported paths, validation and remaining live-provider
limitations are recorded in `consolidation-report.md` after implementation.
