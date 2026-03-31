-- ==========================================
-- USER SETTINGS TABLE MIGRATION
-- ==========================================
-- Run this SQL in your Supabase SQL Editor
-- This creates the table to store per-user settings like active model selection

-- Drop existing table if it has wrong schema
DROP TABLE IF EXISTS rag_user_settings CASCADE;

-- Create rag_user_settings table with correct schema
CREATE TABLE rag_user_settings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL UNIQUE REFERENCES auth.users(id) ON DELETE CASCADE,
    active_model_id TEXT NOT NULL DEFAULT 'system_default',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT TIMEZONE('utc', NOW()),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT TIMEZONE('utc', NOW())
);

-- Enable RLS (Row Level Security)
ALTER TABLE rag_user_settings ENABLE ROW LEVEL SECURITY;

-- Create policies for user access
DROP POLICY IF EXISTS "Users can read own settings" ON rag_user_settings;
CREATE POLICY "Users can read own settings" ON rag_user_settings
    FOR SELECT USING (auth.uid() = user_id);

DROP POLICY IF EXISTS "Users can update own settings" ON rag_user_settings;
CREATE POLICY "Users can update own settings" ON rag_user_settings
    FOR UPDATE USING (auth.uid() = user_id);

DROP POLICY IF EXISTS "Users can insert own settings" ON rag_user_settings;
CREATE POLICY "Users can insert own settings" ON rag_user_settings
    FOR INSERT WITH CHECK (auth.uid() = user_id);

-- Create index for faster lookups
CREATE INDEX IF NOT EXISTS idx_user_settings_user_id ON rag_user_settings(user_id);

-- Test query to verify table was created
SELECT column_name, data_type 
FROM information_schema.columns 
WHERE table_name = 'rag_user_settings' 
ORDER BY ordinal_position;
