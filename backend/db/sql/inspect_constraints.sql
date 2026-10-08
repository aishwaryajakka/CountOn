-- Read-only: foreign keys in public, with target and delete rule.
SELECT ns.nspname AS table_schema,
       source.relname AS table_name,
       constraint_row.conname AS constraint_name,
       target.relname AS referenced_table,
       pg_get_constraintdef(constraint_row.oid) AS definition
FROM pg_constraint AS constraint_row
JOIN pg_class AS source ON source.oid = constraint_row.conrelid
JOIN pg_namespace AS ns ON ns.oid = source.relnamespace
JOIN pg_class AS target ON target.oid = constraint_row.confrelid
WHERE ns.nspname = 'public' AND constraint_row.contype = 'f'
ORDER BY source.relname, constraint_row.conname;
