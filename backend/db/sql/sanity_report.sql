-- Read-only: independent child counts avoid multiplying rows by joining both children.
SELECT expectation.id AS expectation_id,
       expectation.claim,
       expectation.status,
       (SELECT count(*) FROM public.evidence
        WHERE expectation_id = expectation.id) AS evidence_count,
       (SELECT count(*) FROM public.evaluations
        WHERE expectation_id = expectation.id) AS evaluation_count
FROM public.expectations AS expectation
ORDER BY expectation.created_at DESC, expectation.id DESC;
