-- pgvector migration: match_chunks RPC + HNSW index
-- Run this in your Supabase SQL Editor (Dashboard → SQL Editor → New query)

-- 1. Ensure the vector extension is enabled
create extension if not exists vector;

-- 2. Create an HNSW index on the embedding column for fast cosine similarity search
--    (If you have many rows, this may take a few minutes)
create index if not exists rag_chunks_embedding_hnsw
  on rag_chunks using hnsw (embedding vector_cosine_ops);

-- 3. Create the match_chunks RPC function used by supabase_vector_search()
create or replace function match_chunks(
  query_embedding vector(384),
  p_collection_id uuid,
  p_pipeline_name text,
  p_k int default 6
)
returns table (
  id uuid,
  chunk_text text,
  chunk_index int,
  page_number int,
  filename text,
  file_id uuid,
  pipeline_name text,
  similarity float
)
language sql stable
as $$
  select
    c.id,
    c.chunk_text,
    c.chunk_index,
    c.page_number,
    f.filename,
    c.file_id,
    c.pipeline_name,
    1 - (c.embedding <=> query_embedding) as similarity
  from rag_chunks c
  left join rag_files f on f.id = c.file_id
  where c.collection_id = p_collection_id
    and c.pipeline_name = p_pipeline_name
    and c.embedding is not null
  order by c.embedding <=> query_embedding
  limit p_k;
$$;
