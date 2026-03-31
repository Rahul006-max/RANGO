"""
Ask service - handles fast and compare mode question answering.
"""
import os
import random
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from langchain_community.vectorstores import Chroma

from config import get_settings
from dependencies import (
    get_supabase_user_client,
    PIPELINE_DB_PATHS,
    QA_CACHE,
    COLLECTION_FULLTEXT,
    PREFERRED_PIPELINE_CACHE,
    BUILD_STATS_CACHE,
    get_embeddings,
    get_vectorstore,
    supabase_vector_search,
)
from core.pipelines import SYSTEM_PIPELINES, normalize_search_type, randomized_weights, jitter_int
from core.scoring import pipeline_score, compute_advanced_metrics
from core.retrieval import build_vectordb_for_pipeline, dedupe_docs
from core.llm import generate_answer_with_retry, _is_extraction_question
from services.analytics_service import persist_query_analytics
from utils.text_utils import (
    clean_text,
    enrich_answer_if_duration,
    smart_extract_answer,
    normalize,
)
from utils.timing_utils import now_ms, elapsed_ms as _elapsed_ms, empty_global_timings
from utils.token_utils import estimate_cost_usd
from models import AskRequest

settings = get_settings()


def ask_question(data: AskRequest, user_id: str, access_token: str, model_name: str | None = None, api_key: str | None =None, temperature: float | None = None):
    """
    Answer a question using fast or compare mode.
    
    Args:
        data: AskRequest with question, collection_id, mode, custom_pipeline
        user_id: User ID
        access_token: User's access token
        model_name: Optional model name override (None = system default)
        api_key: Optional API key for custom models
        temperature: Optional temperature override
    
    Returns:
        dict with question, collection_id, mode, best_pipeline, final_answer, metrics, 
        retrieval_comparison, citations
    """
    embeddings = get_embeddings()
    sb = get_supabase_user_client(access_token)

    question = data.question.strip()
    mode = (data.mode or "fast").lower().strip()

    # ── QA_CACHE check FIRST — no DB round-trip on cache hit ──────────────────
    cache_key = f"{data.collection_id}:{question.lower().strip()}"
    if mode == "fast":
        cached = QA_CACHE.get(data.collection_id, {}).get(cache_key)
        if cached:
            cached["metrics"]["cache_hit"] = True
            return cached

    # Validate collection (only runs on cache miss)
    collection_res = sb.table("rag_collections") \
        .select("id,index_type") \
        .eq("id", data.collection_id) \
        .eq("user_id", user_id) \
        .maybe_single() \
        .execute()
    
    if not collection_res.data:
        return {"error": "Collection not found", "status_code": 400}

    # ── Route tree-indexed collections to PageIndex retrieval ─────────────
    col_index_type = (collection_res.data.get("index_type") or "vector").lower()
    if col_index_type == "tree":
        from services.page_index_service import answer_with_tree
        return answer_with_tree(
            question=question,
            collection_id=data.collection_id,
            user_id=user_id,
            sb=sb,
            fast=(mode == "fast"),
        )

    if data.collection_id not in PIPELINE_DB_PATHS:
        return {"error": {"error": "index_missing_locally", "message": "Index missing locally. Rebuild index."}, "status_code": 422}

    collection_paths = PIPELINE_DB_PATHS[data.collection_id]
    
    # Controlled randomization (PER RUN)
    run_weights = randomized_weights()

    # ── Single-pipeline fast path ─────────────────────────────────────────────
    # In fast mode, if we already know the best pipeline from a prior question on
    # this collection, only retrieve from that one pipeline (1 Supabase RPC call
    # instead of 4). Fall back to the full 4-pipeline scan when no preference
    # exists yet (first question on a fresh collection).
    preferred_key = f"{user_id}:{data.collection_id}"
    fast_single_pipeline = (
        mode == "fast"
        and not (data.custom_pipeline and data.custom_pipeline.enabled)
        and preferred_key in PREFERRED_PIPELINE_CACHE
    )

    if fast_single_pipeline:
        preferred_name = PREFERRED_PIPELINE_CACHE[preferred_key]
        pipelines_to_use = [p for p in SYSTEM_PIPELINES if p["name"] == preferred_name]
        if not pipelines_to_use:
            pipelines_to_use = SYSTEM_PIPELINES.copy()
            fast_single_pipeline = False
    else:
        pipelines_to_use = SYSTEM_PIPELINES.copy()
        if data.custom_pipeline and data.custom_pipeline.enabled:
            pipelines_to_use.append({
                "name": "Custom User Pipeline",
                "chunk_size": data.custom_pipeline.chunk_size,
                "overlap": data.custom_pipeline.overlap,
                "search_type": normalize_search_type(data.custom_pipeline.search_type),
                "k": data.custom_pipeline.top_k,
            })
        random.shuffle(pipelines_to_use)
    
    # Smart full-text extraction
    t_global_start = now_ms()
    full_text = COLLECTION_FULLTEXT.get(data.collection_id, "")
    t_se_start = now_ms()
    extracted_full = smart_extract_answer(question, full_text)
    t_se_ms = _elapsed_ms(t_se_start)
    
    if extracted_full:
        total_ms = _elapsed_ms(t_global_start)
        extract_timings = empty_global_timings()
        extract_timings["smart_extract_ms"] = round(t_se_ms, 2)
        extract_timings["total_ms"] = round(total_ms, 2)
        
        payload = {
            "question": question,
            "collection_id": data.collection_id,
            "mode": mode,
            "best_pipeline": "FULLTEXT_EXTRACT",
            "final_answer": extracted_full,
            "metrics": {
                "cache_hit": False,
                "smart_extract_used": True,
                "timings_ms": extract_timings,
                "pipeline_latencies": [],
                "tokens": None,
                "cost_usd": None
            },
            "retrieval_comparison": [],
            "citations": []
        }
        
        def _save_fulltext_history():
            try:
                sb.table("rag_chat_history").insert({
                    "user_id": user_id,
                    "collection_id": data.collection_id,
                    "question": question,
                    "answer": extracted_full,
                    "mode": mode,
                    "best_pipeline": "FULLTEXT_EXTRACT",
                    "citations": [],
                    "retrieval_comparison": [],
                    "metrics": payload["metrics"]
                }).execute()
            except Exception as e:
                print(f"[WARN] History insert failed: {e}")
        threading.Thread(target=_save_fulltext_history, daemon=True).start()

        QA_CACHE.setdefault(data.collection_id, {})[cache_key] = payload
        return payload
    
    # Retrieval + Scoring
    t_start_ms = now_ms()
    retrieval_results = []
    pipeline_latencies = []
    cumulative_embedding_ms = 0.0
    
    # ── Build stats (static after upload — cached in memory) ─────────────────
    if data.collection_id not in BUILD_STATS_CACHE:
        build_stats_res = sb.table("rag_pipeline_builds") \
            .select("pipeline_name,chunks_created,build_time_sec") \
            .eq("collection_id", data.collection_id) \
            .eq("user_id", user_id) \
            .limit(10) \
            .execute()
        BUILD_STATS_CACHE[data.collection_id] = build_stats_res.data or []

    build_map = {
        r["pipeline_name"]: r for r in BUILD_STATS_CACHE[data.collection_id]
    }

    # Pre-compute the query embedding ONCE — reused across all pipeline threads
    # to avoid N redundant embed_query() calls (~300-600 ms each).
    query_embedding = embeddings.embed_query(question)

    # Extraction questions need more chunks to sweep the whole document for every match
    _extraction_q = _is_extraction_question(question)

    t_all_retrieval_start = now_ms()

    def _retrieve_pipeline(p):
        """Retrieve and score a single pipeline (runs in thread)."""
        t_pipe_start = now_ms()
        base_k = min(p["k"] * 2, 16) if _extraction_q else p["k"]
        actual_top_k = jitter_int(base_k, 2, min_val=1)

        t_embed_start = now_ms()
        docs = dedupe_docs(supabase_vector_search(
            collection_id=data.collection_id,
            pipeline_name=p["name"] if p["name"] != "Custom User Pipeline" else "Balanced (MMR)",
            query_text=question,
            k=actual_top_k,
            search_type=normalize_search_type(p["search_type"]),
            access_token=access_token,
            query_embedding=query_embedding,
        ))
        pipe_retrieval_ms = _elapsed_ms(t_embed_start)
        if not docs:
            print(f"[WARN] No docs returned for {p['name']}")
            return None, None

        t_ctx_start = now_ms()
        context = clean_text("\n\n".join(d.page_content for d in docs))
        pipe_context_build_ms = _elapsed_ms(t_ctx_start)

        t_score_start = now_ms()
        scores = pipeline_score(
            question=question,
            context=context,
            top_k=actual_top_k,
            answer="",
            weights=run_weights
        )
        pipe_scoring_ms = _elapsed_ms(t_score_start)
        pipe_total_ms = _elapsed_ms(t_pipe_start)

        latency_entry = {
            "pipeline": p["name"],
            "retrieval_ms": round(pipe_retrieval_ms, 2),
            "context_build_ms": round(pipe_context_build_ms, 2),
            "scoring_ms": round(pipe_scoring_ms, 2),
            "total_ms": round(pipe_total_ms, 2),
        }
        result_entry = {
            "pipeline": p["name"],
            "chunk_size": p["chunk_size"],
            "overlap": p["overlap"],
            "search_type": p["search_type"],
            "top_k": actual_top_k,
            "score_weights": run_weights,
            "retrieval_time_sec": round(pipe_total_ms / 1000, 3),
            "context_preview": context[:320] + ("..." if len(context) > 320 else ""),
            "sources": [{"source": d.metadata.get("source"), "page": d.metadata.get("page")} for d in docs],
            "scores": scores,
            "chunks_created": build_map.get(p["name"], {}).get("chunks_created"),
            "build_time_sec": build_map.get(p["name"], {}).get("build_time_sec"),
            "context": context,
            # Kept temporarily so advanced metrics can access individual chunks
            # after the LLM answer is generated; popped before serialization.
            "chunk_texts": [d.page_content for d in docs],
            "retrieval_ms": pipe_retrieval_ms,
        }
        return latency_entry, result_entry

    # Run all pipeline retrievals in parallel
    with ThreadPoolExecutor(max_workers=min(len(pipelines_to_use), 6)) as executor:
        futures = {executor.submit(_retrieve_pipeline, p): p for p in pipelines_to_use}
        for future in as_completed(futures):
            latency_entry, result_entry = future.result()
            if latency_entry is not None:
                pipeline_latencies.append(latency_entry)
                cumulative_embedding_ms += result_entry.pop("retrieval_ms", 0)
                retrieval_results.append(result_entry)
    
    global_retrieval_ms = _elapsed_ms(t_all_retrieval_start)

    # Sort by final score descending (parallel results arrive in non-deterministic order)
    retrieval_results.sort(key=lambda x: x["scores"]["final"], reverse=True)
    best = max(retrieval_results, key=lambda x: x["scores"]["final"])
    best_context = best["context"]
    
    # Smart extract attempt
    t_se_start = now_ms()
    extracted = smart_extract_answer(question, best_context)
    smart_extract_ms = _elapsed_ms(t_se_start)
    
    # LLM generation
    t_llm_start = now_ms()
    if extracted:
        final_answer = extracted
        tokens = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    else:
        base_answer, retry_meta, tokens = generate_answer_with_retry(
            question, best_context, fast=(mode == "fast"), model_name=model_name, api_key=api_key, temperature=temperature
        )
        final_answer = enrich_answer_if_duration(question, best_context, base_answer)
    llm_ms = _elapsed_ms(t_llm_start)
    
    best["scores"] = pipeline_score(
        question=question,
        context=best_context,
        top_k=best["top_k"],
        answer=final_answer,
        weights=run_weights
    )

    # In compare mode, generate per-pipeline LLM answers for all non-best pipelines
    # so the frontend can show a side-by-side 2×2 answer grid.
    if mode == "compare":
        best["answer"] = final_answer

        def _gen_compare_answer(r):
            ctx = r["context"]
            try:
                ans_base, _, _ = generate_answer_with_retry(question, ctx, model_name=model_name, api_key=api_key, temperature=temperature)
                r["answer"] = enrich_answer_if_duration(question, ctx, ans_base)
            except Exception:
                r["answer"] = ""
            # Re-score with actual answer so grounded score is real
            r["scores"] = pipeline_score(
                question=question,
                context=ctx,
                top_k=r["top_k"],
                answer=r["answer"],
                weights=run_weights,
            )
            return r

        non_best = [r for r in retrieval_results if r is not best]
        if non_best:
            with ThreadPoolExecutor(max_workers=min(len(non_best), 4)) as ex_cmp:
                list(ex_cmp.map(_gen_compare_answer, non_best))
        # Re-sort with real grounded scores and update references
        retrieval_results.sort(key=lambda x: x["scores"]["final"], reverse=True)
        best = retrieval_results[0]
        final_answer = best.get("answer", final_answer)
        best_context = best["context"]

    # Compute advanced metrics for the winning pipeline using its chunk texts + final answer
    advanced_metrics = compute_advanced_metrics(
        chunk_texts=best.get("chunk_texts", []),
        answer=final_answer,
        question=question,
    )

    for r in retrieval_results:
        r.pop("context", None)
        r.pop("chunk_texts", None)  # strip raw chunks before serialization
    
    total_ms = _elapsed_ms(t_start_ms)
    active_model = settings.groq_model
    tokens["model"] = active_model
    cost_usd = estimate_cost_usd(tokens, active_model)
    
    # Build global timings_ms (research-grade)
    timings_ms = {
        "embedding_ms": round(cumulative_embedding_ms, 2),
        "retrieval_ms": round(global_retrieval_ms, 2),
        "rerank_ms": 0,
        "llm_ms": round(llm_ms, 2),
        "smart_extract_ms": round(smart_extract_ms, 2),
        "total_ms": round(total_ms, 2),
    }
    
    payload = {
        "question": question,
        "collection_id": data.collection_id,
        "mode": mode,
        "best_pipeline": best["pipeline"],
        "final_answer": final_answer,
        "metrics": {
            "cache_hit": False,
            "timings_ms": timings_ms,
            "pipeline_latencies": pipeline_latencies,
            "tokens": tokens,
            "cost_usd": cost_usd,
            "advanced_metrics": advanced_metrics,
        },
        "retrieval_comparison": retrieval_results,
        "citations": best["sources"][:5]
    }
    
    def _save_history():
        try:
            sb.table("rag_chat_history").insert({
                "user_id": user_id,
                "collection_id": data.collection_id,
                "question": question,
                "answer": final_answer,
                "mode": mode,
                "best_pipeline": best["pipeline"],
                "citations": payload["citations"],
                "retrieval_comparison": retrieval_results,
                "metrics": payload["metrics"]
            }).execute()
            persist_query_analytics(
                sb,
                user_id=user_id,
                collection_id=data.collection_id,
                question=question,
                mode=mode,
                index_type="vector",
                best_pipeline=best["pipeline"],
                metrics=payload["metrics"],
                retrieval_comparison=retrieval_results,
            )
        except Exception as e:
            print(f"[WARN] History insert failed: {e}")
    threading.Thread(target=_save_history, daemon=True).start()

    QA_CACHE.setdefault(data.collection_id, {})[cache_key] = payload
    # Update preferred pipeline cache so chat uses the best pipeline immediately
    if best["pipeline"] != "FULLTEXT_EXTRACT":
        PREFERRED_PIPELINE_CACHE[f"{user_id}:{data.collection_id}"] = best["pipeline"]
    return payload
