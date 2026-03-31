-- ============================================================
-- Dual Indexing System — Database Migration
-- Run this ONCE in Supabase SQL Editor.
-- ============================================================

-- 1. Add index_type column to existing rag_collections table
ALTER TABLE rag_collections
  ADD COLUMN IF NOT EXISTS index_type TEXT NOT NULL DEFAULT 'vector';

-- Add check constraint (idempotent — skip if it already exists)
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'rag_collections_index_type_check'
  ) THEN
    ALTER TABLE rag_collections
      ADD CONSTRAINT rag_collections_index_type_check
      CHECK (index_type IN ('vector', 'tree'));
  END IF;
END $$;


-- 2. New table: page_index_trees (stores hierarchical JSON tree per collection)
CREATE TABLE IF NOT EXISTS page_index_trees (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  collection_id UUID NOT NULL REFERENCES rag_collections(id) ON DELETE CASCADE,
  tree_json   JSONB NOT NULL,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_page_index_trees_collection
  ON page_index_trees(collection_id);

-- Enable RLS
ALTER TABLE page_index_trees ENABLE ROW LEVEL SECURITY;

-- RLS policy: users can read their own trees (via collection ownership)
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_policies
    WHERE tablename = 'page_index_trees' AND policyname = 'Users can read own trees'
  ) THEN
    CREATE POLICY "Users can read own trees" ON page_index_trees
      FOR SELECT USING (
        collection_id IN (
          SELECT id FROM rag_collections WHERE user_id = auth.uid()::text
        )
      );
  END IF;
END $$;
