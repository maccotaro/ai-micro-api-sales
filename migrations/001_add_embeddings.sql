-- Migration: Add embedding support to salesdb
-- Version: 001
-- Description: Creates embedding tables and adds vector columns for similarity search

-- Ensure pgvector extension is available
CREATE EXTENSION IF NOT EXISTS vector;

-- =====================================================
-- Meeting Minute Embeddings Table
-- =====================================================
CREATE TABLE IF NOT EXISTS meeting_minute_embeddings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    meeting_minute_id UUID NOT NULL UNIQUE REFERENCES meeting_minutes(id) ON DELETE CASCADE,
    content TEXT NOT NULL,
    embedding vector(768),
    emb_metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

-- Index for vector similarity search
CREATE INDEX IF NOT EXISTS idx_meeting_minute_embeddings_vector
ON meeting_minute_embeddings USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

-- Index for meeting_minute_id lookup
CREATE INDEX IF NOT EXISTS idx_meeting_minute_embeddings_minute_id
ON meeting_minute_embeddings(meeting_minute_id);

-- =====================================================
-- Add embedding column to existing tables if not exists
-- =====================================================

-- Product Embeddings - add vector column if not exists
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'product_embeddings' AND column_name = 'embedding'
    ) THEN
        ALTER TABLE product_embeddings ADD COLUMN embedding vector(768);
    END IF;
END $$;

-- Create vector index for product_embeddings
CREATE INDEX IF NOT EXISTS idx_product_embeddings_vector
ON product_embeddings USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

-- Success Case Embeddings - add vector column if not exists
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'success_case_embeddings' AND column_name = 'embedding'
    ) THEN
        ALTER TABLE success_case_embeddings ADD COLUMN embedding vector(768);
    END IF;
END $$;

-- Create vector index for success_case_embeddings
CREATE INDEX IF NOT EXISTS idx_success_case_embeddings_vector
ON success_case_embeddings USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

-- Sales Talk Embeddings - add vector column if not exists
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'sales_talk_embeddings' AND column_name = 'embedding'
    ) THEN
        ALTER TABLE sales_talk_embeddings ADD COLUMN embedding vector(768);
    END IF;
END $$;

-- Create vector index for sales_talk_embeddings
CREATE INDEX IF NOT EXISTS idx_sales_talk_embeddings_vector
ON sales_talk_embeddings USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

-- =====================================================
-- Update trigger for updated_at
-- =====================================================
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Trigger for meeting_minute_embeddings
DROP TRIGGER IF EXISTS update_meeting_minute_embeddings_updated_at ON meeting_minute_embeddings;
CREATE TRIGGER update_meeting_minute_embeddings_updated_at
    BEFORE UPDATE ON meeting_minute_embeddings
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- =====================================================
-- Comments
-- =====================================================
COMMENT ON TABLE meeting_minute_embeddings IS 'Vector embeddings for meeting minutes for similarity search';
COMMENT ON COLUMN meeting_minute_embeddings.embedding IS '768-dimensional vector from nomic-embed-text model';
COMMENT ON COLUMN meeting_minute_embeddings.content IS 'Text content that was embedded';
COMMENT ON COLUMN meeting_minute_embeddings.emb_metadata IS 'Additional metadata about the embedding';

-- =====================================================
-- Migration record
-- =====================================================
CREATE TABLE IF NOT EXISTS schema_migrations (
    version VARCHAR(255) PRIMARY KEY,
    applied_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

INSERT INTO schema_migrations (version) VALUES ('001_add_embeddings')
ON CONFLICT (version) DO NOTHING;
