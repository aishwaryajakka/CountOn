SELECT id, user_id, expectation_id, evaluation_id, type, channel, status,
       message, metadata, sent_at, created_at
FROM public.notifications
ORDER BY created_at DESC, id DESC;
