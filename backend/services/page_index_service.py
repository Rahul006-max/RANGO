"""
PageIndex service — high-level operations for building, storing, loading,
and querying PageIndex trees.
"""

from __future__ import annotations

import time
import os
from typing import Optional

from config import get_settings
from core.page_index_builder import build_page_index_tree
from core.page_index_retrieval import retrieve_with_tree_trace
from services.analytics_service import persist_query_analytics
from core.llm import generate_answer_with_retry
from utils.text_utils import clean_text, enrich_answer_if_duration
from utils.token_utils import estimate_cost_usd

settings = get_settings()


def _iter_leaf_nodes(node: dict) -> list[dict]:
    """Return all leaf nodes in left-to-right order."""
    children = node.get("children") or []
    if not children:
        return [node]
    leaves: list[dict] = []
    for child in children:
        leaves.extend(_iter_leaf_nodes(child))
    return leaves


def build_and_store_tree(
    collection_id: str,
    documents: list,
    supabase_admin,
    user_id: str,
    file_id_map: Optional[dict] = None,
) -> dict:
    """
    Build a PageIndex tree from documents and store it in Supabase.

    Returns:
        dict with tree build stats.
    """
    t0 = time.time()
    tree = build_page_index_tree(documents)
    build_time = round(time.time() - t0, 2)

    # Upsert: delete any existing tree for this collection, then insert new one
    try:
        supabase_admin.table("page_index_trees") \
            .delete() \
            .eq("collection_id", collection_id) \
            .execute()
    except Exception:
        pass  # table may be empty

    supabase_admin.table("page_index_trees").insert({
        "collection_id": collection_id,
        "tree_json": tree,
    }).execute()

    # Persist tree leaves as chunks so tree-indexed collections also have
    # row-level content in Supabase for inspection and analytics.
    persisted_chunks = 0
    try:
        supabase_admin.table("rag_chunks") \
            .delete() \
            .eq("collection_id", collection_id) \
            .eq("pipeline_name", "PageIndex Tree") \
            .execute()
    except Exception:
        pass

    try:
        leaves = _iter_leaf_nodes(tree)
        chunk_rows = []
        for idx, doc in enumerate(documents):
            source_path = doc.metadata.get("source", "")
            matched_file_id = None
            if file_id_map:
                matched_file_id = file_id_map.get(source_path) or file_id_map.get(os.path.abspath(source_path))
                if not matched_file_id and file_id_map:
                    matched_file_id = next(iter(file_id_map.values()))

            leaf_summary = ""
            if idx < len(leaves):
                leaf_summary = (leaves[idx].get("summary") or "").strip()

            page_text = (doc.page_content or "")[:4000]
            if leaf_summary:
                chunk_text = f"Summary: {leaf_summary}\n\n{page_text}"
            else:
                chunk_text = page_text

            chunk_rows.append({
                "user_id": user_id,
                "collection_id": collection_id,
                "pipeline_name": "PageIndex Tree",
                "chunk_text": chunk_text,
                "chunk_index": idx,
                "page_number": doc.metadata.get("page"),
                "file_id": matched_file_id,
            })

        for i in range(0, len(chunk_rows), 500):
            batch = chunk_rows[i:i + 500]
            if not batch:
                continue
            supabase_admin.table("rag_chunks").insert(batch).execute()
            persisted_chunks += len(batch)
    except Exception as e:
        print(f"[WARN] Persisting PageIndex chunks failed: {e}")

    try:
        supabase_admin.table("rag_pipeline_builds").insert({
            "user_id": user_id,
            "collection_id": collection_id,
            "pipeline_name": "PageIndex Tree",
            "chunk_size": None,
            "overlap": 0,
            "search_type": "tree",
            "top_k": 1,
            "chunks_created": len(documents),
            "build_time_sec": build_time,
        }).execute()
    except Exception as e:
        print(f"[WARN] rag_pipeline_builds insert failed (PageIndex Tree): {e}")

    print(f"[OK] PageIndex tree stored for collection {collection_id} ({build_time}s)")
    if persisted_chunks:
        print(f"[OK] Stored {persisted_chunks} PageIndex chunks in Supabase rag_chunks")

    return {
        "pipeline_name": "PageIndex Tree",
        "build_time_sec": build_time,
        "pages": len(documents),
        "chunks_persisted": persisted_chunks,
    }


def load_tree(collection_id: str, sb) -> Optional[dict]:
    """
    Load the PageIndex tree JSON from Supabase for a given collection.

    Returns:
        The tree dict, or None if not found.
    """
    res = (
        sb.table("page_index_trees")
        .select("tree_json")
        .eq("collection_id", collection_id)
        .order("created_at", desc=True)
        .limit(1)
        .maybe_single()
        .execute()
    )
    if res.data:
        return res.data["tree_json"]
    return None


def answer_with_tree(
    question: str,
    collection_id: str,
    user_id: str,
    sb,
    fast: bool = True,
    model_name: str | None = None,
    api_key: str | None = None,
    temperature: float | None = None,
) -> dict:
    """
    Full ask pipeline for a tree-indexed collection:
    1. Load tree from DB
    2. Traverse tree to find best leaf
    3. Generate answer from leaf text

    Args:
        question: User's query.
        collection_id: Collection ID.
        user_id: User ID.
        sb: Supabase client.
        fast: If True, use fast/low-token mode.
        model_name: Optional model name override (None = system default).
        api_key: Optional API key for custom models.
        temperature: Optional temperature override.

    Returns a dict matching the /ask response shape.
    """
    import threading
    from utils.timing_utils import now_ms, elapsed_ms

    t_start = now_ms()

    # 1. Load tree
    tree = load_tree(collection_id, sb)
    if not tree:
        return {"error": "PageIndex tree not found for this collection.", "status_code": 404}

    # 2. Traverse
    t_traverse_start = now_ms()
    leaf_text, traversal_path = retrieve_with_tree_trace(question, tree, model_name=model_name, api_key=api_key, temperature=temperature)
    traverse_ms = elapsed_ms(t_traverse_start)

    context = clean_text(leaf_text)
    if not context:
        context = "(No relevant content found in tree.)"

    # 3. Generate answer
    t_llm_start = now_ms()
    answer, _retry_meta, tokens = generate_answer_with_retry(question, context, fast=fast, model_name=model_name, api_key=api_key, temperature=temperature)
    final_answer = enrich_answer_if_duration(question, context, answer)
    llm_ms = elapsed_ms(t_llm_start)

    total_ms = elapsed_ms(t_start)
    active_model = settings.groq_model
    tokens["model"] = active_model
    cost_usd = estimate_cost_usd(tokens, active_model)

    payload = {
        "question": question,
        "collection_id": collection_id,
        "mode": "fast",
        "best_pipeline": "PageIndex Tree",
        "final_answer": final_answer,
        "metrics": {
            "cache_hit": False,
            "smart_extract_used": False,
            "timings_ms": {
                "tree_traverse_ms": round(traverse_ms, 2),
                "llm_ms": round(llm_ms, 2),
                "total_ms": round(total_ms, 2),
            },
            "pipeline_latencies": [],
            "tokens": tokens,
            "cost_usd": cost_usd,
        },
        "retrieval_comparison": [],
        "citations": [],
    }

    # Save to chat history in background
    def _save():
        try:
            sb.table("rag_chat_history").insert({
                "user_id": user_id,
                "collection_id": collection_id,
                "question": question,
                "answer": final_answer,
                "mode": "fast",
                "best_pipeline": "PageIndex Tree",
                "citations": [],
                "retrieval_comparison": [],
                "metrics": payload["metrics"],
            }).execute()
            persist_query_analytics(
                sb,
                user_id=user_id,
                collection_id=collection_id,
                question=question,
                mode="fast",
                index_type="tree",
                best_pipeline="PageIndex Tree",
                metrics=payload["metrics"],
                retrieval_comparison=[],
                retrieval_path=traversal_path,
            )
        except Exception as e:
            print(f"[WARN] Tree history insert failed: {e}")

    threading.Thread(target=_save, daemon=True).start()

    return payload
