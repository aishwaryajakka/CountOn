-- Read-only: expectation state, newest first.
SELECT id, user_id, claim, type, metric, comparison, baseline, target_value, status, created_at
FROM public.expectations
ORDER BY created_at DESC, id DESC;
