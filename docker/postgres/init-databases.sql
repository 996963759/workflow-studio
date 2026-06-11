SELECT 'CREATE DATABASE workflow_studio_test'
WHERE NOT EXISTS (
  SELECT FROM pg_database WHERE datname = 'workflow_studio_test'
)\gexec
