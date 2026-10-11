SELECT id, expectation_id, user_id, status, next_run_at, last_run_at,
       attempt_count, max_attempts, last_error, interval_seconds, recurring,
       scheduled_at, window_start_at, lease_expires_at, connection_id,
       max_evidence_age_seconds, created_at, updated_at
FROM public.monitoring_jobs
ORDER BY next_run_at, id;
