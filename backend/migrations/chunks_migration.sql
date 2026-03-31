-- ==========================================
-- RAG_CHUNKS TABLE MIGRATION
-- ==========================================
-- Run this SQL in your Supabase SQL Editor
-- This table stores individual text chunks for the chunk browser feature

CREATE TABLE IF NOT EXISTS rag_chunks (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    user_id UUID NOT NULL,
    collection_id UUID NOT NULL,
    pipeline_name TEXT NOT NULL,
    file_id UUID,
    chunk_text TEXT NOT NULL,
    chunk_index INTEGER DEFAULT 0,
    page_number INTEGER,
    created_at TIMESTAMPTZ DEFAULT now()
);

-- Enable RLS
ALTER TABLE rag_chunks ENABLE ROW LEVEL SECURITY;

-- RLS policy: users can only see their own chunks
CREATE POLICY "Users can view own chunks"
    ON rag_chunks FOR SELECT
    USING (auth.uid() = user_id);

CREATE POLICY "Users can insert own chunks"
    ON rag_chunks FOR INSERT
    WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can delete own chunks"
    ON rag_chunks FOR DELETE
    USING (auth.uid() = user_id);

-- Indexes for efficient querying
CREATE INDEX IF NOT EXISTS idx_chunks_collection
    ON rag_chunks (collection_id);

CREATE INDEX IF NOT EXISTS idx_chunks_pipeline
    ON rag_chunks (collection_id, pipeline_name);

CREATE INDEX IF NOT EXISTS idx_chunks_user
    ON rag_chunks (user_id);

CREATE INDEX IF NOT EXISTS idx_chunks_file
    ON rag_chunks (file_id);

-- Full-text search index on chunk_text
CREATE INDEX IF NOT EXISTS idx_chunks_text_search
    ON rag_chunks USING GIN (to_tsvector('english', chunk_text));
