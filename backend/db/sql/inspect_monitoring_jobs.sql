SELECT id, expectation_id, user_id, status, next_run_at, last_run_at,
       attempt_count, last_error, created_at, updated_at
FROM public.monitoring_jobs
ORDER BY next_run_at, id;
