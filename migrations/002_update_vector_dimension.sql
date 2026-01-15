-- Migration: Update vector dimension to 1024 for bge-m3 model
-- Version: 002
-- Description: Changes embedding columns from 768 to 1024 dimensions

-- Drop existing indexes first (they reference old dimension)
DROP INDEX IF EXISTS idx_meeting_minute_embeddings_vector;
DROP INDEX IF EXISTS idx_product_embeddings_vector;
DROP INDEX IF EXISTS idx_success_case_embeddings_vector;
DROP INDEX IF EXISTS idx_sales_talk_embeddings_vector;

-- Alter meeting_minute_embeddings column
ALTER TABLE meeting_minute_embeddings
    ALTER COLUMN embedding TYPE vector(1024);

-- Alter product_embeddings column
ALTER TABLE product_embeddings
    ALTER COLUMN embedding TYPE vector(1024);

-- Alter success_case_embeddings column
ALTER TABLE success_case_embeddings
    ALTER COLUMN embedding TYPE vector(1024);

-- Alter sales_talk_embeddings column
ALTER TABLE sales_talk_embeddings
    ALTER COLUMN embedding TYPE vector(1024);

-- Recreate indexes with new dimension
CREATE INDEX IF NOT EXISTS idx_meeting_minute_embeddings_vector
ON meeting_minute_embeddings USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

CREATE INDEX IF NOT EXISTS idx_product_embeddings_vector
ON product_embeddings USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

CREATE INDEX IF NOT EXISTS idx_success_case_embeddings_vector
ON success_case_embeddings USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

CREATE INDEX IF NOT EXISTS idx_sales_talk_embeddings_vector
ON sales_talk_embeddings USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

-- Update migration record
INSERT INTO schema_migrations (version) VALUES ('002_update_vector_dimension')
ON CONFLICT (version) DO NOTHING;
