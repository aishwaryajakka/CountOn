SELECT id, user_id, expectation_id, entity_type, resource_id AS entity_id,
       action, metadata, request_id, created_at
FROM public.audit_events
ORDER BY created_at DESC, id DESC;
