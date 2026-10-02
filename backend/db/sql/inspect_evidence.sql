-- Read-only: normalized observations, newest observation first.
SELECT id, expectation_id, external_event_id, source, metric, value, unit, confidence, observed_at, created_at
FROM public.evidence
ORDER BY observed_at DESC, created_at DESC, id DESC;
