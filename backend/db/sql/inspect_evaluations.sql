-- Read-only: deterministic evaluation history.
SELECT id, expectation_id, result, expected, observed, confidence, reasoning, created_at
FROM public.evaluations
ORDER BY created_at DESC, id DESC;
