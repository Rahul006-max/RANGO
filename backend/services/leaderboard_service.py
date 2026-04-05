"""
Leaderboard service - aggregates pipeline performance statistics.
"""
import traceback
from datetime import datetime
from dateutil.relativedelta import relativedelta

from dependencies import get_supabase_user_client


def get_leaderboard(
    collection_id: str,
    user_id: str,
    access_token: str,
    mode: str = "all",
    range_filter: str = "30d"
):
    """
    Enhanced leaderboard with mode and time range filters.
    
    Args:
        collection_id: Collection ID
        user_id: User ID
        access_token: User's access token
        mode: Filter by mode (all|fast|compare|chat)
        range_filter: Time range (7d|30d|all)
    
    Returns:
        dict with collection_id, mode, range, total_questions, chat_interactions, 
        best_pipeline_today, pipelines (list of pipeline stats)
    """
    try:
        sb = get_supabase_user_client(access_token)
        
        # Parse filters
        mode = (mode or "all").lower().strip()
        range_filter = (range_filter or "30d").lower().strip()
        
        # Build time filter
        cutoff_date = None
        if range_filter == "7d":
            cutoff_date = datetime.now() - relativedelta(days=7)
        elif range_filter == "30d":
            cutoff_date = datetime.now() - relativedelta(days=30)
        # range_filter == "all" → no cutoff
        
        # Query rag_chat_history with filters
        query = sb.table("rag_chat_history") \
            .select("best_pipeline,retrieval_comparison,created_at,mode,metrics") \
            .eq("collection_id", collection_id) \
            .eq("user_id", user_id)
        
        # Apply time filter
        if cutoff_date:
            query = query.gte("created_at", cutoff_date.isoformat())
        
        # Apply mode filter
        if mode != "all":
            query = query.eq("mode", mode)
        
        res = query.order("created_at", desc=False).execute()
        
        # Get chat message count
        if mode in ("all", "chat"):
            chat_query = sb.table("rag_chat_messages") \
                .select("id", count="exact") \
                .eq("collection_id", collection_id) \
                .eq("user_id", user_id)
                
            if cutoff_date:
                chat_query = chat_query.gte("created_at", cutoff_date.isoformat())
                
            chat_res = chat_query.execute()
            chat_count = chat_res.count or 0
        else:
            chat_count = 0
        total_questions = len(rows)
        
        if not rows:
            return {
                "collection_id": collection_id,
                "mode": mode,
                "range": range_filter,
                "total_questions": 0,
                "chat_interactions": chat_count,
                "best_pipeline_today": None,
                "pipelines": []
            }
        
        # Compute stats per pipeline
        stats = {}
        
        for r in rows:
            best = r.get("best_pipeline")
            if best:
                stats.setdefault(best, {
                    "pipeline": best,
                    "wins": 0,
                    "avg_final_score": 0,
                    "avg_retrieval_time_sec": 0,
                    "avg_llm_time_sec": 0,
                    "avg_total_time_sec": 0,
                    "avg_retrieval_ms": 0,
                    "avg_llm_ms": 0,
                    "avg_total_ms": 0,
                    "samples": 0,
                })
                stats[best]["wins"] += 1
            
            comp = r.get("retrieval_comparison") or []
            metrics = r.get("metrics") or {}
            timings = metrics.get("timings_ms") or {}
            pipeline_latencies = metrics.get("pipeline_latencies") or []
            
            # Build a lookup from pipeline_latencies for per-pipeline ms
            pl_lookup = {pl.get("pipeline"): pl for pl in pipeline_latencies}
            
            for p in comp:
                name = p.get("pipeline")
                if not name:
                    continue
                
                final_score = (p.get("scores") or {}).get("final", 0)
                rt = p.get("retrieval_time_sec", 0)
                
                # Per-pipeline ms from pipeline_latencies (new), fallback to retrieval_time_sec
                pl = pl_lookup.get(name, {})
                pipe_retrieval_ms = pl.get("retrieval_ms", rt * 1000)
                pipe_total_ms = pl.get("total_ms", rt * 1000)
                
                # Global LLM & total from timings_ms (shared across all pipelines for this query)
                llm_ms = timings.get("llm_ms", 0)
                total_ms_val = timings.get("total_ms", 0)
                
                stats.setdefault(name, {
                    "pipeline": name,
                    "wins": 0,
                    "avg_final_score": 0,
                    "avg_retrieval_time_sec": 0,
                    "avg_llm_time_sec": 0,
                    "avg_total_time_sec": 0,
                    "avg_retrieval_ms": 0,
                    "avg_llm_ms": 0,
                    "avg_total_ms": 0,
                    "samples": 0,
                })
                
                stats[name]["avg_final_score"] += float(final_score or 0)
                stats[name]["avg_retrieval_time_sec"] += float(rt or 0)
                stats[name]["avg_llm_time_sec"] += float(llm_ms / 1000.0)
                stats[name]["avg_total_time_sec"] += float(total_ms_val / 1000.0)
                stats[name]["avg_retrieval_ms"] += float(pipe_retrieval_ms or 0)
                stats[name]["avg_llm_ms"] += float(llm_ms or 0)
                stats[name]["avg_total_ms"] += float(total_ms_val or 0)
                stats[name]["samples"] += 1
        
        # Compute averages and win_rate
        pipelines = []
        for _, v in stats.items():
            if v["samples"] > 0:
                v["avg_final_score"] = round(v["avg_final_score"] / v["samples"], 2)
                v["avg_retrieval_time_sec"] = round(v["avg_retrieval_time_sec"] / v["samples"], 3)
                v["avg_llm_time_sec"] = round(v["avg_llm_time_sec"] / v["samples"], 3)
                v["avg_total_time_sec"] = round(v["avg_total_time_sec"] / v["samples"], 3)
                v["avg_retrieval_ms"] = round(v["avg_retrieval_ms"] / v["samples"], 2)
                v["avg_llm_ms"] = round(v["avg_llm_ms"] / v["samples"], 2)
                v["avg_total_ms"] = round(v["avg_total_ms"] / v["samples"], 2)
            
            # Compute win_rate
            v["win_rate"] = round(v["wins"] / total_questions, 3) if total_questions > 0 else 0.0

            # Composite leaderboard_score: 40% win_rate + 60% normalised quality
            # avg_final_score is 0-10 → normalise to 0-1 before combining
            normalized_score = v["avg_final_score"] / 10.0 if v["avg_final_score"] else 0.0
            v["leaderboard_score"] = round(
                (v["win_rate"] * 0.4) + (normalized_score * 0.6), 4
            )

            pipelines.append(v)

        # Sort by composite leaderboard_score (quality-weighted), not raw wins
        pipelines.sort(key=lambda x: x["leaderboard_score"], reverse=True)

        # Assign 1-based rank after sorting
        for i, p in enumerate(pipelines):
            p["rank"] = i + 1
        
        # Compute best_pipeline_today (last 24h)
        best_pipeline_today = None
        cutoff_today = datetime.now() - relativedelta(days=1)
        
        today_query = sb.table("rag_chat_history") \
            .select("best_pipeline") \
            .eq("collection_id", collection_id) \
            .eq("user_id", user_id) \
            .gte("created_at", cutoff_today.isoformat()) \
            .execute()
        
        today_rows = today_query.data or []
        if today_rows:
            today_stats = {}
            for r in today_rows:
                best = r.get("best_pipeline")
                if best:
                    today_stats[best] = today_stats.get(best, 0) + 1
            
            if today_stats:
                best_pipeline_today = max(today_stats.items(), key=lambda x: x[1])[0]
        
        return {
            "collection_id": collection_id,
            "mode": mode,
            "range": range_filter,
            "total_questions": total_questions,
            "chat_interactions": chat_count,
            "best_pipeline_today": best_pipeline_today,
            "pipelines": pipelines
        }
    
    except Exception as e:
        print("[ERROR] LEADERBOARD ERROR:")
        print(traceback.format_exc())
        # Return safe default instead of crashing
        return {
            "collection_id": collection_id,
            "mode": mode or "all",
            "range": range_filter or "30d",
            "total_questions": 0,
            "chat_interactions": 0,
            "best_pipeline_today": None,
            "pipelines": [],
            "error": str(e)
        }


def get_global_leaderboard(
    user_id: str,
    access_token: str,
    mode: str = "all",
    range_filter: str = "30d"
):
    """
    Global leaderboard — aggregates pipeline stats across ALL collections for
    the authenticated user.  Same shape as get_leaderboard() minus collection_id.
    """
    try:
        sb = get_supabase_user_client(access_token)

        mode = (mode or "all").lower().strip()
        range_filter = (range_filter or "30d").lower().strip()

        cutoff_date = None
        if range_filter == "7d":
            cutoff_date = datetime.now() - relativedelta(days=7)
        elif range_filter == "30d":
            cutoff_date = datetime.now() - relativedelta(days=30)

        query = sb.table("rag_chat_history") \
            .select("best_pipeline,retrieval_comparison,created_at,mode,metrics") \
            .eq("user_id", user_id)

        if cutoff_date:
            query = query.gte("created_at", cutoff_date.isoformat())
        if mode != "all":
            query = query.eq("mode", mode)

        res = query.order("created_at", desc=False).execute()

        if mode in ("all", "chat"):
            chat_query = sb.table("rag_chat_messages") \
                .select("id", count="exact") \
                .eq("user_id", user_id)
                
            if cutoff_date:
                chat_query = chat_query.gte("created_at", cutoff_date.isoformat())
                
            chat_res = chat_query.execute()
            chat_count = chat_res.count or 0
        else:
            chat_count = 0

        rows = res.data or []
        total_questions = len(rows)

        if not rows:
            return {
                "mode": mode,
                "range": range_filter,
                "total_questions": 0,
                "chat_interactions": chat_count,
                "best_pipeline_today": None,
                "pipelines": []
            }

        # --- reuse same aggregation logic as per-collection ---
        stats = {}

        for r in rows:
            best = r.get("best_pipeline")
            if best:
                stats.setdefault(best, {
                    "pipeline": best, "wins": 0,
                    "avg_final_score": 0,
                    "avg_retrieval_time_sec": 0, "avg_llm_time_sec": 0, "avg_total_time_sec": 0,
                    "avg_retrieval_ms": 0, "avg_llm_ms": 0, "avg_total_ms": 0,
                    "samples": 0,
                })
                stats[best]["wins"] += 1

            comp = r.get("retrieval_comparison") or []
            metrics = r.get("metrics") or {}
            timings = metrics.get("timings_ms") or {}
            pipeline_latencies = metrics.get("pipeline_latencies") or []
            pl_lookup = {pl.get("pipeline"): pl for pl in pipeline_latencies}

            for p in comp:
                name = p.get("pipeline")
                if not name:
                    continue
                final_score = (p.get("scores") or {}).get("final", 0)
                rt = p.get("retrieval_time_sec", 0)
                pl = pl_lookup.get(name, {})
                pipe_retrieval_ms = pl.get("retrieval_ms", rt * 1000)
                pipe_total_ms = pl.get("total_ms", rt * 1000)
                llm_ms = timings.get("llm_ms", 0)
                total_ms_val = timings.get("total_ms", 0)

                stats.setdefault(name, {
                    "pipeline": name, "wins": 0,
                    "avg_final_score": 0,
                    "avg_retrieval_time_sec": 0, "avg_llm_time_sec": 0, "avg_total_time_sec": 0,
                    "avg_retrieval_ms": 0, "avg_llm_ms": 0, "avg_total_ms": 0,
                    "samples": 0,
                })
                stats[name]["avg_final_score"] += float(final_score or 0)
                stats[name]["avg_retrieval_time_sec"] += float(rt or 0)
                stats[name]["avg_llm_time_sec"] += float(llm_ms / 1000.0)
                stats[name]["avg_total_time_sec"] += float(total_ms_val / 1000.0)
                stats[name]["avg_retrieval_ms"] += float(pipe_retrieval_ms or 0)
                stats[name]["avg_llm_ms"] += float(llm_ms or 0)
                stats[name]["avg_total_ms"] += float(total_ms_val or 0)
                stats[name]["samples"] += 1

        pipelines = []
        for _, v in stats.items():
            if v["samples"] > 0:
                v["avg_final_score"] = round(v["avg_final_score"] / v["samples"], 2)
                v["avg_retrieval_time_sec"] = round(v["avg_retrieval_time_sec"] / v["samples"], 3)
                v["avg_llm_time_sec"] = round(v["avg_llm_time_sec"] / v["samples"], 3)
                v["avg_total_time_sec"] = round(v["avg_total_time_sec"] / v["samples"], 3)
                v["avg_retrieval_ms"] = round(v["avg_retrieval_ms"] / v["samples"], 2)
                v["avg_llm_ms"] = round(v["avg_llm_ms"] / v["samples"], 2)
                v["avg_total_ms"] = round(v["avg_total_ms"] / v["samples"], 2)

            v["win_rate"] = round(v["wins"] / total_questions, 3) if total_questions > 0 else 0.0
            normalized_score = v["avg_final_score"] / 10.0 if v["avg_final_score"] else 0.0
            v["leaderboard_score"] = round(
                (v["win_rate"] * 0.4) + (normalized_score * 0.6), 4
            )
            pipelines.append(v)

        pipelines.sort(key=lambda x: x["leaderboard_score"], reverse=True)
        for i, p in enumerate(pipelines):
            p["rank"] = i + 1

        # Best pipeline today (last 24 h, all collections)
        best_pipeline_today = None
        cutoff_today = datetime.now() - relativedelta(days=1)
        today_q = sb.table("rag_chat_history") \
            .select("best_pipeline") \
            .eq("user_id", user_id) \
            .gte("created_at", cutoff_today.isoformat()) \
            .execute()
        today_rows = today_q.data or []
        if today_rows:
            today_stats = {}
            for r in today_rows:
                best = r.get("best_pipeline")
                if best:
                    today_stats[best] = today_stats.get(best, 0) + 1
            if today_stats:
                best_pipeline_today = max(today_stats.items(), key=lambda x: x[1])[0]

        return {
            "mode": mode,
            "range": range_filter,
            "total_questions": total_questions,
            "chat_interactions": chat_count,
            "best_pipeline_today": best_pipeline_today,
            "pipelines": pipelines
        }

    except Exception as e:
        print("[ERROR] GLOBAL LEADERBOARD ERROR:")
        print(traceback.format_exc())
        return {
            "mode": mode or "all",
            "range": range_filter or "30d",
            "total_questions": 0,
            "chat_interactions": 0,
            "best_pipeline_today": None,
            "pipelines": [],
            "error": str(e)
        }
