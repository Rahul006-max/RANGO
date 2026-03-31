-- ==========================================
-- PIPELINE CONFIG MIGRATION
-- ==========================================
-- Run this SQL in your Supabase SQL Editor
-- OR via the Supabase dashboard

-- Add pipeline_config column to rag_collections table
ALTER TABLE rag_collections 
ADD COLUMN IF NOT EXISTS pipeline_config JSONB;

-- Optional: Add an index for faster queries
CREATE INDEX IF NOT EXISTS idx_collections_pipeline_config 
ON rag_collections USING GIN (pipeline_config);

-- Example pipeline_config structure:
-- {
--   "preset_name": "Balanced",
--   "chunk_size": 800,
--   "overlap": 120,
--   "top_k": 6,
--   "search_type": "mmr"
-- }

-- Test query to verify column exists
SELECT column_name, data_type 
FROM information_schema.columns 
WHERE table_name = 'rag_collections' 
  AND column_name = 'pipeline_config';
