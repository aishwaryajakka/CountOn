# Release acceptance change manifest — October 12, 2026

Branch: `feature/alexa-mcp`. Starting HEAD: `e7c74ac5db21fba05bb46bf49053e53c911ed05f`.
This is a dirty working-tree release, not a deployed immutable commit. No commit,
push, production deployment or migration was performed. Nothing was deleted.

## Work performed in this pass

| Files | Change |
| --- | --- |
| `backend/app/alexa/adapter.py`, `backend/tests/test_alexa.py` | Owned GET speech reports persisted lifecycle; six status regression cases. Why/capture behavior retained. |
| `backend/tests/test_release_journey.py` | Two connected Google/Microsoft local journeys: signed JWT, HTTP MCP, restart-safe confirmed capture, authorized normalized source, worker, one inbox entry, shared web/voice status, edits/cancellation and isolation. External model/provider responses are mocked. |
| `backend/db/scripts/backup_restore_smoke.py`, `backend/tests/test_backup_restore_smoke.py` | Real isolated local archive restore and exact cleanup, plus eight unsafe-target guard cases. No production restoration claimed. |
| `backend/db/scripts/production_smoke.py` | Fifth connected provider/notification recovery group. |
| `backend/app/api/v1/notifications.py` | Docstring truth fix only. |
| `frontend/app/(workspace)/expectations/new/page.tsx`, `frontend/tests/creation.test.tsx` | Accurate conversational setup/source guidance; two manual review/confirm regression tests. |
| `frontend/app/layout.tsx`, `frontend/public/fonts/*` | Same font families/variables/weights, locally hosted pinned assets and original OFL licenses; removes fresh-build font network requirement. |
| `.github/workflows/ci.yml` | Required nondeployment API build origin, and visible high-severity full dependency audit gate. Advisory remains unresolved; no forced dependency changes. |
| `docs/production-readiness.md`, `docs/production-readiness-history.md`, this manifest | Current matrix/commands/live limits and rollout gates; prior report preserved as history. |
| `frontend/README.md`, `docs/traditional-alexa.md`, `backend/db/README.md` | Fonts/build requirement, actual speech/voice scope, isolated restore instructions. |

The original settings, evaluator, compiler, clarification, investigator, MCP tools,
providers, monitoring infrastructure and migrations remain canonical. Existing
pending provider/monitoring/UI work is retained. Files below already pending at the
start can include additional changes in the table above; the initial status snapshot
cannot establish line-by-line authorship. Review the entire pending diff before any
release. This inventory excludes ignored secrets, caches and build artifacts.

## New pending paths in this pass

- `.github/workflows/ci.yml`
- `backend/app/alexa/adapter.py`
- `backend/db/README.md`
- `backend/db/scripts/backup_restore_smoke.py`
- `backend/db/scripts/production_smoke.py`
- `backend/tests/test_alexa.py`
- `backend/tests/test_backup_restore_smoke.py`
- `backend/tests/test_release_journey.py`
- `docs/production-readiness-history.md`
- `docs/release-change-manifest.md`
- `docs/traditional-alexa.md`
- `frontend/app/(workspace)/expectations/new/page.tsx`
- `frontend/app/layout.tsx`
- `frontend/public/fonts/README.md`
- `frontend/public/fonts/inter-OFL.txt`
- `frontend/public/fonts/inter-variable.ttf`
- `frontend/public/fonts/space-grotesk-variable.ttf`
- `frontend/public/fonts/spacegrotesk-OFL.txt`
- `frontend/tests/creation.test.tsx`

## Pre-existing pending paths retained

- `README.md`
- `backend/alembic/versions/9b635da2e034_provider_synchronization.py`
- `backend/alembic/versions/ac746eb3f145_automatic_monitoring_delivery.py`
- `backend/app/api/v1/notification_preferences.py`
- `backend/app/api/v1/notifications.py`
- `backend/app/api/v1/provider_oauth.py`
- `backend/app/api/v1/provider_sync.py`
- `backend/app/api/v1/router.py`
- `backend/app/core/config.py`
- `backend/app/db/models/__init__.py`
- `backend/app/db/models/delivery.py`
- `backend/app/db/models/operations.py`
- `backend/app/db/models/provider_sync.py`
- `backend/app/integrations/accounts.py`
- `backend/app/integrations/adapters.py`
- `backend/app/integrations/microsoft.py`
- `backend/app/integrations/normalization.py`
- `backend/app/integrations/provider.py`
- `backend/app/integrations/watches.py`
- `backend/app/integrations/worker.py`
- `backend/app/monitoring/evidence.py`
- `backend/app/monitoring/sources.py`
- `backend/app/monitoring/worker.py`
- `backend/app/notifications/__init__.py`
- `backend/app/notifications/delivery.py`
- `backend/app/notifications/worker.py`
- `backend/app/schemas/provider_sync.py`
- `backend/app/services/evidence_service.py`
- `backend/app/services/expectation_service.py`
- `backend/app/services/integration_service.py`
- `backend/app/services/notification_service.py`
- `backend/app/services/provider_sync_service.py`
- `backend/notifications.env.sample`
- `backend/providers.env.sample`
- `backend/tests/test_automatic_tracking.py`
- `backend/tests/test_deployment_readiness.py`
- `backend/tests/test_provider_sync.py`
- `docs/automatic-tracking.md`
- `docs/integrations-acceptance.md`
- `docs/monitoring.md`
- `docs/production-readiness.md`
- `frontend/README.md`
- `frontend/app/(workspace)/expectations/[id]/page.tsx`
- `frontend/app/(workspace)/expectations/page.tsx`
- `frontend/app/(workspace)/integrations/page.tsx`
- `frontend/app/(workspace)/notifications/page.tsx`
- `frontend/components/app-shell.tsx`
- `frontend/components/integration.tsx`
- `frontend/components/notification-preferences.tsx`
- `frontend/components/notification.tsx`
- `frontend/components/provider-account.tsx`
- `frontend/components/source-binding.tsx`
- `frontend/components/tracking-controls.tsx`
- `frontend/hooks/use-resource.ts`
- `frontend/lib/monitoring.ts`
- `frontend/lib/presentation.ts`
- `frontend/lib/providers.ts`
- `frontend/lib/types.ts`
- `frontend/tests/presentation.test.ts`
- `frontend/tests/providers.test.tsx`
- `frontend/tests/resource.test.tsx`
- `frontend/tests/screens.test.tsx`
- `frontend/tests/tracking.test.tsx`

Final inventory: 82 pending file paths; 63 already pending at start, 19 newly pending. All 63 initial pending paths retained.

Validation and release blockers: [production readiness](production-readiness.md).
