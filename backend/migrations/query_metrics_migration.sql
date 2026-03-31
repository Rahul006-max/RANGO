-- Query-level metrics + retrieval logs for analytics and visualization

create table if not exists query_metrics (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null,
  collection_id uuid not null,
  question text,
  mode text,
  index_type text default 'vector',
  best_pipeline text,
  prompt_tokens integer default 0,
  completion_tokens integer default 0,
  total_tokens integer default 0,
  cost_usd double precision default 0,
  total_latency_ms double precision default 0,
  retrieval_latency_ms double precision default 0,
  llm_latency_ms double precision default 0,
  smart_extract_ms double precision default 0,
  retrieval_comparison jsonb,
  advanced_metrics jsonb,
  created_at timestamptz not null default now()
);

create index if not exists idx_query_metrics_user_created_at on query_metrics(user_id, created_at desc);
create index if not exists idx_query_metrics_collection_created_at on query_metrics(collection_id, created_at desc);
create index if not exists idx_query_metrics_best_pipeline on query_metrics(best_pipeline);

create table if not exists retrieval_logs (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null,
  collection_id uuid not null,
  question text,
  index_type text default 'vector',
  best_pipeline text,
  path_json jsonb,
  chunks_json jsonb,
  latency_ms double precision default 0,
  cost_usd double precision default 0,
  created_at timestamptz not null default now()
);

create index if not exists idx_retrieval_logs_user_created_at on retrieval_logs(user_id, created_at desc);
create index if not exists idx_retrieval_logs_collection_created_at on retrieval_logs(collection_id, created_at desc);

alter table query_metrics enable row level security;
alter table retrieval_logs enable row level security;

create policy if not exists "query_metrics_owner_select" on query_metrics
for select using (auth.uid() = user_id);
create policy if not exists "query_metrics_owner_insert" on query_metrics
for insert with check (auth.uid() = user_id);

create policy if not exists "retrieval_logs_owner_select" on retrieval_logs
for select using (auth.uid() = user_id);
create policy if not exists "retrieval_logs_owner_insert" on retrieval_logs
for insert with check (auth.uid() = user_id);
