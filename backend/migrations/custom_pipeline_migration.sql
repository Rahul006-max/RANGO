-- ==========================================
-- CUSTOM PIPELINE MIGRATION
-- ==========================================
-- Run this SQL in your Supabase SQL Editor

-- Add custom_pipeline_config column to rag_collections table
ALTER TABLE rag_collections 
ADD COLUMN IF NOT EXISTS custom_pipeline_config JSONB;

-- Optional: Add an index for faster queries
CREATE INDEX IF NOT EXISTS idx_collections_custom_pipeline_config 
ON rag_collections USING GIN (custom_pipeline_config);

-- Example custom_pipeline_config structure:
-- {
--   "enabled": true,
--   "preset_name": "Custom",
--   "chunk_size": 900,
--   "overlap": 150,
--   "top_k": 8,
--   "search_type": "mmr"
-- }

-- Test query to verify column exists
SELECT column_name, data_type 
FROM information_schema.columns 
WHERE table_name = 'rag_collections' 
  AND column_name = 'custom_pipeline_config';
