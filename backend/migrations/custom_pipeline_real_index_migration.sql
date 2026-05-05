-- ==========================================
-- REAL CUSTOM PIPELINE INDEX MIGRATION
-- ==========================================
-- Run this SQL in your Supabase SQL Editor.

ALTER TABLE rag_collections
ADD COLUMN IF NOT EXISTS custom_pipeline_config JSONB;

CREATE INDEX IF NOT EXISTS idx_collections_custom_pipeline_config
ON rag_collections USING GIN (custom_pipeline_config);

-- Remove older duplicate build rows before adding the unique constraint.
DELETE FROM rag_pipeline_builds a
USING rag_pipeline_builds b
WHERE a.user_id = b.user_id
  AND a.collection_id = b.collection_id
  AND a.pipeline_name = b.pipeline_name
  AND (
    COALESCE(a.created_at, 'epoch'::timestamptz) < COALESCE(b.created_at, 'epoch'::timestamptz)
    OR (
      COALESCE(a.created_at, 'epoch'::timestamptz) = COALESCE(b.created_at, 'epoch'::timestamptz)
      AND a.ctid < b.ctid
    )
  );

-- Allows backend upserts/replacements for one build row per pipeline.
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM pg_constraint
    WHERE conname = 'rag_pipeline_builds_user_collection_pipeline_key'
  ) THEN
    ALTER TABLE rag_pipeline_builds
    ADD CONSTRAINT rag_pipeline_builds_user_collection_pipeline_key
    UNIQUE (user_id, collection_id, pipeline_name);
  END IF;
END $$;

-- Expected custom_pipeline_config shape:
-- {
--   "enabled": true,
--   "pipeline_name": "My Custom Pipeline",
--   "preset_name": "My Custom Pipeline",
--   "chunk_size": 900,
--   "overlap": 150,
--   "top_k": 8,
--   "search_type": "mmr",
--   "index_status": "ready",
--   "chunks_created": 42,
--   "build_time_sec": 1.23,
--   "updated_at": "2026-05-05T00:00:00+00:00"
-- }
