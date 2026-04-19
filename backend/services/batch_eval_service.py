"""
Batch evaluation service - processes questions synchronously, returns results inline.
No Supabase table persistence needed; results come back directly in the POST response.
"""
import asyncio
import uuid

from dependencies import (
    get_supabase_user_client,
    PIPELINE_DB_PATHS,
    COLLECTION_FULLTEXT,
    supabase_vector_search,
)
from core.pipelines import SYSTEM_PIPELINES, normalize_search_type
from core.scoring import pipeline_score
from core.retrieval import dedupe_docs
from core.llm import generate_answer_with_retry, _is_summary_question, _is_extraction_question
from utils.text_utils import clean_text, enrich_answer_if_duration, smart_extract_answer
from utils.timing_utils import now_ms, elapsed_ms as _elapsed_ms
from models import BatchEvalRequest


async def create_batch_eval_run(
    collection_id: str,
    user_id: str,
    access_token: str,
    data: BatchEvalRequest,
    model_name: str | None = None,
    api_key: str | None = None,
    temperature: float | None = None,
):
    """
    Process all questions synchronously and return full results inline.
    The POST response already contains every answer — no polling needed.
    """
    sb = get_supabase_user_client(access_token)

    # Verify ownership
    collection_res = (
        sb.table("rag_collections")
        .select("id")
        .eq("id", collection_id)
        .eq("user_id", user_id)
        .maybe_single()
        .execute()
    )
    if not collection_res.data:
        return {"error": "Collection not found", "status_code": 404}

    run_id = str(uuid.uuid4())
    t_batch_start = now_ms()
    items_out = []
    total_score = 0.0

    for item in data.items:
        t_q_start = now_ms()
        question = item.question.strip()
        error_msg = None
        best_pipeline = "error"
        final_answer = ""
        token_usage = {"total_tokens": 0, "estimated_cost_usd": 0}
        retrieval_ms = 0.0
        llm_ms = 0.0
        final_score = 0.0

        try:
            # 1. Fast-path: fulltext keyword extract
            full_text = COLLECTION_FULLTEXT.get(collection_id, "")
            t_se = now_ms()
            extracted_full = smart_extract_answer(question, full_text)
            se_ms = _elapsed_ms(t_se)

            if extracted_full:
                q_total = _elapsed_ms(t_q_start)
                items_out.append({
                    "id": str(uuid.uuid4()),
                    "question": item.question,
                    "expected_answer": item.expected_answer,
                    "best_pipeline": "FULLTEXT_EXTRACT",
                    "final_answer": extracted_full,
                    "scores": {"final_score": 10.0},
                    "latency": {"total_ms": round(q_total, 2), "retrieval_ms": round(se_ms, 2), "llm_ms": 0},
                    "tokens": {"total_tokens": 0, "estimated_cost_usd": 0},
                    "created_at": None,
                })
                total_score += 10.0
                continue

            # 2. Vector retrieval across all system pipelines
            # For summary/broad questions, use 3× k; for extraction/enumeration, use 2× k
            summary_q = _is_summary_question(question)
            extraction_q = _is_extraction_question(question)
            retrieval_results = []
            t_ret_start = now_ms()

            for p in SYSTEM_PIPELINES:
                try:
                    if summary_q:
                        effective_k = min(p["k"] * 3, 24)
                    elif extraction_q:
                        effective_k = min(p["k"] * 2, 16)
                    else:
                        effective_k = p["k"]
                    docs = dedupe_docs(supabase_vector_search(
                        collection_id=collection_id,
                        pipeline_name=p["name"],
                        query_text=question,
                        k=effective_k,
                        search_type=normalize_search_type(p["search_type"]),
                        access_token=access_token,
                    ))
                    context = clean_text("\n\n".join(d.page_content for d in docs))
                    scores = pipeline_score(question=question, context=context, top_k=effective_k, answer="")
                    retrieval_results.append({"pipeline": p["name"], "context": context, "scores": scores})
                except Exception as pipe_err:
                    print(f"  [batch_eval] Pipeline {p['name']} failed: {pipe_err}")

            retrieval_ms = _elapsed_ms(t_ret_start)

            if not retrieval_results:
                raise RuntimeError("All pipelines failed to retrieve context.")

            best = max(retrieval_results, key=lambda x: x["scores"]["final"])
            best_context = best["context"]
            best_pipeline = best["pipeline"]
            final_score = best["scores"]["final"]

            # 3. LLM answer generation in thread pool so event loop stays free
            t_llm = now_ms()
            base_answer, _retry_meta, token_usage = await asyncio.to_thread(
                generate_answer_with_retry, question, best_context, False, model_name, api_key, temperature
            )
            final_answer = enrich_answer_if_duration(question, best_context, base_answer)
            llm_ms = _elapsed_ms(t_llm)

        except Exception as exc:
            print(f"[batch_eval] question failed — {exc}")
            error_msg = str(exc)
            final_answer = f"Error: {error_msg}"

        q_total = _elapsed_ms(t_q_start)
        total_score += final_score

        items_out.append({
            "id": str(uuid.uuid4()),
            "question": item.question,
            "expected_answer": item.expected_answer,
            "best_pipeline": best_pipeline,
            "final_answer": final_answer,
            "scores": {
                "final_score": round(final_score, 4),
                "error": error_msg,
            },
            "latency": {
                "total_ms": round(q_total, 2),
                "retrieval_ms": round(retrieval_ms, 2),
                "llm_ms": round(llm_ms, 2),
            },
            "tokens": {
                "total_tokens": token_usage.get("total_tokens", 0),
                "estimated_cost_usd": token_usage.get("estimated_cost_usd", 0),
            },
            "created_at": None,
        })

    batch_total_ms = _elapsed_ms(t_batch_start)
    completed = len([i for i in items_out if not (i["scores"] or {}).get("error")])
    avg_score = round(total_score / max(len(items_out), 1), 4)

    q_times = [i["latency"]["total_ms"] for i in items_out if i["latency"]["total_ms"] > 0]
    sorted_t = sorted(q_times) if q_times else [0]
    n = len(sorted_t)

    def _pct(data, pct):
        idx = int(pct / 100.0 * max(len(data) - 1, 0))
        return round(data[min(idx, len(data) - 1)], 2)

    return {
        "run_id": run_id,
        "status": "done",
        "total_questions": len(data.items),
        "completed_questions": completed,
        "avg_final_score": avg_score,
        "latency_stats": {
            "avg_question_ms": round(sum(sorted_t) / max(n, 1), 2),
            "p95_ms": _pct(sorted_t, 95),
            "p99_ms": _pct(sorted_t, 99),
            "total_batch_ms": round(batch_total_ms, 2),
        },
        "items": items_out,
    }
