SELECT id, user_id, provider, connection_type, external_account_id, display_name,
       status, scopes, metadata, last_synced_at, created_at, updated_at
FROM public.integration_connections
ORDER BY created_at DESC, id DESC;
