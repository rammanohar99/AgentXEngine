-- Bootstrap script run once when the Postgres container is first created.
-- Enables the pgvector extension required for semantic search.

CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Verify extensions loaded
SELECT extname, extversion FROM pg_extension WHERE extname IN ('vector', 'uuid-ossp');
