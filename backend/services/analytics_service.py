"""Analytics service for cost tracking, retrieval logs, and report export."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from io import BytesIO
from typing import Any, Dict, List, Optional
import csv
import json

from dependencies import get_supabase_user_client


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except Exception:
        return default


def _to_int(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return default
        return int(value)
    except Exception:
        return default


def _format_day(created_at: str) -> str:
    if not created_at:
        return "unknown"
    try:
        return datetime.fromisoformat(created_at.replace("Z", "+00:00")).date().isoformat()
    except Exception:
        return "unknown"


def persist_query_analytics(
    sb,
    *,
    user_id: str,
    collection_id: str,
    question: str,
    mode: str,
    index_type: str,
    best_pipeline: str,
    metrics: Dict[str, Any],
    retrieval_comparison: Optional[List[Dict[str, Any]]] = None,
    retrieval_path: Optional[List[Dict[str, Any]]] = None,
) -> None:
    """Persist per-query metrics and retrieval trace; best-effort only."""
    metrics = metrics or {}
    timings = metrics.get("timings_ms") or {}
    tokens = metrics.get("tokens") or {}

    cost_usd = _to_float(metrics.get("cost_usd"), 0.0)
    if cost_usd == 0:
        cost_usd = _to_float(tokens.get("estimated_cost_usd"), 0.0)

    payload = {
        "user_id": user_id,
        "collection_id": collection_id,
        "question": question,
        "mode": mode,
        "index_type": index_type or "vector",
        "best_pipeline": best_pipeline,
        "prompt_tokens": _to_int(tokens.get("prompt_tokens"), 0),
        "completion_tokens": _to_int(tokens.get("completion_tokens"), 0),
        "total_tokens": _to_int(tokens.get("total_tokens"), 0),
        "cost_usd": cost_usd,
        "total_latency_ms": _to_float(timings.get("total_ms"), 0.0),
        "retrieval_latency_ms": _to_float(
            timings.get("retrieval_ms", timings.get("tree_traverse_ms", 0.0)),
            0.0,
        ),
        "llm_latency_ms": _to_float(timings.get("llm_ms"), 0.0),
        "smart_extract_ms": _to_float(timings.get("smart_extract_ms"), 0.0),
        "retrieval_comparison": retrieval_comparison or [],
        "advanced_metrics": metrics.get("advanced_metrics") or {},
    }

    try:
        sb.table("query_metrics").insert(payload).execute()
    except Exception as e:
        print(f"[WARN] query_metrics insert skipped: {e}")

    # Keep retrieval logs compact but useful for flow-chart style visualization.
    chunk_rows: List[Dict[str, Any]] = []
    for p in retrieval_comparison or []:
        top_sources = (p.get("sources") or [])[:6]
        chunk_rows.append(
            {
                "pipeline": p.get("pipeline"),
                "score": (p.get("scores") or {}).get("final"),
                "top_k": p.get("top_k"),
                "search_type": p.get("search_type"),
                "sources": top_sources,
            }
        )

    path_payload = retrieval_path or []
    if not path_payload and retrieval_comparison:
        path_payload = [
            {
                "stage": "ranked_pipeline",
                "pipeline": p.get("pipeline"),
                "final_score": (p.get("scores") or {}).get("final"),
            }
            for p in retrieval_comparison
        ]

    retrieval_payload = {
        "user_id": user_id,
        "collection_id": collection_id,
        "question": question,
        "index_type": index_type or "vector",
        "best_pipeline": best_pipeline,
        "path_json": path_payload,
        "chunks_json": chunk_rows,
        "latency_ms": _to_float(timings.get("total_ms"), 0.0),
        "cost_usd": cost_usd,
    }

    try:
        sb.table("retrieval_logs").insert(retrieval_payload).execute()
    except Exception as e:
        print(f"[WARN] retrieval_logs insert skipped: {e}")


def _fallback_from_chat_history(
    sb,
    *,
    user_id: str,
    collection_id: Optional[str],
    since_iso: str,
) -> List[Dict[str, Any]]:
    query = (
        sb.table("rag_chat_history")
        .select("collection_id,best_pipeline,created_at,metrics")
        .eq("user_id", user_id)
        .gte("created_at", since_iso)
        .order("created_at", desc=False)
        .limit(2000)
    )
    if collection_id:
        query = query.eq("collection_id", collection_id)
    res = query.execute()

    rows = []
    for row in res.data or []:
        metrics = row.get("metrics") or {}
        timings = metrics.get("timings_ms") or {}
        tokens = metrics.get("tokens") or {}
        rows.append(
            {
                "collection_id": row.get("collection_id"),
                "best_pipeline": row.get("best_pipeline") or "unknown",
                "created_at": row.get("created_at"),
                "cost_usd": _to_float(
                    metrics.get("cost_usd", tokens.get("estimated_cost_usd", 0.0)),
                    0.0,
                ),
                "total_tokens": _to_int(tokens.get("total_tokens"), 0),
                "total_latency_ms": _to_float(timings.get("total_ms"), 0.0),
            }
        )
    return rows


def get_cost_analytics(
    *,
    user_id: str,
    access_token: str,
    collection_id: Optional[str] = None,
    days: int = 30,
) -> Dict[str, Any]:
    sb = get_supabase_user_client(access_token)
    days = max(1, min(int(days or 30), 365))
    since = datetime.now(timezone.utc) - timedelta(days=days)
    since_iso = since.isoformat()

    rows: List[Dict[str, Any]] = []
    try:
        query = (
            sb.table("query_metrics")
            .select("collection_id,best_pipeline,created_at,cost_usd,total_tokens,total_latency_ms")
            .eq("user_id", user_id)
            .gte("created_at", since_iso)
            .order("created_at", desc=False)
            .limit(3000)
        )
        if collection_id:
            query = query.eq("collection_id", collection_id)
        res = query.execute()
        rows = res.data or []
    except Exception as e:
        print(f"[WARN] query_metrics select failed, falling back to chat_history: {e}")

    if not rows:
        rows = _fallback_from_chat_history(
            sb,
            user_id=user_id,
            collection_id=collection_id,
            since_iso=since_iso,
        )

    total_queries = len(rows)
    total_cost = sum(_to_float(r.get("cost_usd"), 0.0) for r in rows)
    total_tokens = sum(_to_int(r.get("total_tokens"), 0) for r in rows)
    avg_latency = (
        sum(_to_float(r.get("total_latency_ms"), 0.0) for r in rows) / total_queries
        if total_queries
        else 0.0
    )

    by_pipeline: Dict[str, Dict[str, Any]] = defaultdict(
        lambda: {"queries": 0, "cost_usd": 0.0, "total_tokens": 0, "avg_latency_ms": 0.0}
    )
    by_day: Dict[str, Dict[str, Any]] = defaultdict(
        lambda: {"queries": 0, "cost_usd": 0.0, "total_tokens": 0}
    )

    latency_accumulator: Dict[str, float] = defaultdict(float)

    for row in rows:
        pipeline = row.get("best_pipeline") or "unknown"
        day_key = _format_day(row.get("created_at"))

        p = by_pipeline[pipeline]
        p["queries"] += 1
        p["cost_usd"] += _to_float(row.get("cost_usd"), 0.0)
        p["total_tokens"] += _to_int(row.get("total_tokens"), 0)
        latency_accumulator[pipeline] += _to_float(row.get("total_latency_ms"), 0.0)

        d = by_day[day_key]
        d["queries"] += 1
        d["cost_usd"] += _to_float(row.get("cost_usd"), 0.0)
        d["total_tokens"] += _to_int(row.get("total_tokens"), 0)

    for pipeline, p in by_pipeline.items():
        if p["queries"]:
            p["avg_latency_ms"] = round(latency_accumulator[pipeline] / p["queries"], 2)
        p["cost_usd"] = round(p["cost_usd"], 6)

    by_day_list = [
        {"date": day, **vals, "cost_usd": round(vals["cost_usd"], 6)}
        for day, vals in sorted(by_day.items(), key=lambda x: x[0])
    ]

    return {
        "summary": {
            "days": days,
            "total_queries": total_queries,
            "total_cost_usd": round(total_cost, 6),
            "total_tokens": total_tokens,
            "avg_latency_ms": round(avg_latency, 2),
        },
        "by_pipeline": [
            {"pipeline": name, **vals} for name, vals in sorted(by_pipeline.items(), key=lambda x: x[1]["cost_usd"], reverse=True)
        ],
        "by_day": by_day_list,
    }


def get_retrieval_logs(
    *,
    user_id: str,
    access_token: str,
    collection_id: str,
    limit: int = 20,
) -> Dict[str, Any]:
    sb = get_supabase_user_client(access_token)
    limit = max(1, min(int(limit or 20), 100))

    try:
        res = (
            sb.table("retrieval_logs")
            .select("id,question,index_type,best_pipeline,path_json,chunks_json,latency_ms,cost_usd,created_at")
            .eq("user_id", user_id)
            .eq("collection_id", collection_id)
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )
        rows = res.data or []
        if rows:
            return {"logs": rows}
    except Exception as e:
        print(f"[WARN] retrieval_logs table unavailable, falling back: {e}")

    # Fallback to ask history comparison payload
    res = (
        sb.table("rag_chat_history")
        .select("id,question,best_pipeline,retrieval_comparison,metrics,created_at")
        .eq("user_id", user_id)
        .eq("collection_id", collection_id)
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )
    logs = []
    for row in res.data or []:
        metrics = row.get("metrics") or {}
        timings = metrics.get("timings_ms") or {}
        logs.append(
            {
                "id": row.get("id"),
                "question": row.get("question"),
                "index_type": "vector",
                "best_pipeline": row.get("best_pipeline"),
                "path_json": [
                    {
                        "stage": "ranked_pipeline",
                        "pipeline": p.get("pipeline"),
                        "final_score": (p.get("scores") or {}).get("final"),
                    }
                    for p in (row.get("retrieval_comparison") or [])
                ],
                "chunks_json": [
                    {
                        "pipeline": p.get("pipeline"),
                        "sources": (p.get("sources") or [])[:6],
                    }
                    for p in (row.get("retrieval_comparison") or [])
                ],
                "latency_ms": _to_float(timings.get("total_ms"), 0.0),
                "cost_usd": _to_float(metrics.get("cost_usd"), 0.0),
                "created_at": row.get("created_at"),
            }
        )
    return {"logs": logs}


def build_compare_report(
    *,
    report_format: str,
    payload: Dict[str, Any],
) -> Dict[str, Any]:
    """Build compare report bytes/content in requested format."""
    fmt = (report_format or "json").lower().strip()
    data = payload or {}
    pipelines = data.get("pipelines") or []

    if fmt == "json":
        text = json.dumps(data, indent=2)
        return {
            "filename": f"rag-compare-report-{int(datetime.now().timestamp())}.json",
            "media_type": "application/json",
            "content": text.encode("utf-8"),
        }

    if fmt == "csv":
        # csv.writer needs a text file-like; use StringIO then encode.
        from io import StringIO

        sio = StringIO()
        cw = csv.writer(sio)
        cw.writerow(
            [
                "pipeline",
                "final_score",
                "relevance",
                "grounded",
                "quality",
                "efficiency",
                "retrieval_time_sec",
                "chunk_size",
                "overlap",
                "top_k",
                "search_type",
            ]
        )
        for p in pipelines:
            scores = p.get("scores") or {}
            cw.writerow(
                [
                    p.get("pipeline"),
                    scores.get("final"),
                    scores.get("relevance"),
                    scores.get("grounded"),
                    scores.get("quality"),
                    scores.get("efficiency"),
                    p.get("retrieval_time_sec"),
                    p.get("chunk_size"),
                    p.get("overlap"),
                    p.get("top_k"),
                    p.get("search_type"),
                ]
            )
        return {
            "filename": f"rag-compare-report-{int(datetime.now().timestamp())}.csv",
            "media_type": "text/csv",
            "content": sio.getvalue().encode("utf-8"),
        }

    if fmt == "txt":
        lines = [
            "RAG Compare Report",
            "===================",
            f"Generated: {datetime.now().isoformat()}",
            f"Collection: {data.get('collection_id')}",
            f"Question: {data.get('question')}",
            "",
            f"Best pipeline: {data.get('best_pipeline')}",
            f"Final answer: {data.get('final_answer')}",
            "",
            "Pipelines:",
        ]
        for idx, p in enumerate(pipelines, start=1):
            scores = p.get("scores") or {}
            lines.append(
                f"{idx}. {p.get('pipeline')} | final={scores.get('final')} | relevance={scores.get('relevance')} | grounded={scores.get('grounded')}"
            )
        text = "\n".join(lines)
        return {
            "filename": f"rag-compare-report-{int(datetime.now().timestamp())}.txt",
            "media_type": "text/plain",
            "content": text.encode("utf-8"),
        }

    if fmt == "pdf":
        try:
            from reportlab.lib.pagesizes import letter
            from reportlab.pdfgen import canvas

            buffer = BytesIO()
            c = canvas.Canvas(buffer, pagesize=letter)
            y = 760
            c.setFont("Helvetica-Bold", 14)
            c.drawString(40, y, "RAG Compare Report")
            y -= 26
            c.setFont("Helvetica", 10)
            c.drawString(40, y, f"Generated: {datetime.now().isoformat()}")
            y -= 20
            c.drawString(40, y, f"Collection: {data.get('collection_id', '-')}")
            y -= 16
            c.drawString(40, y, f"Best pipeline: {data.get('best_pipeline', '-')}")
            y -= 24
            c.setFont("Helvetica-Bold", 11)
            c.drawString(40, y, "Pipelines")
            y -= 16
            c.setFont("Helvetica", 9)
            for idx, p in enumerate(pipelines, start=1):
                scores = p.get("scores") or {}
                line = f"{idx}. {p.get('pipeline')} | final={scores.get('final')} | latency={p.get('retrieval_time_sec')}s"
                c.drawString(40, y, line[:120])
                y -= 14
                if y < 60:
                    c.showPage()
                    y = 760
                    c.setFont("Helvetica", 9)
            c.showPage()
            c.save()
            buffer.seek(0)
            return {
                "filename": f"rag-compare-report-{int(datetime.now().timestamp())}.pdf",
                "media_type": "application/pdf",
                "content": buffer.read(),
            }
        except Exception as e:
            raise ValueError(
                "PDF export requires reportlab. Install it or use json/csv/txt."
            ) from e

    raise ValueError("Unsupported format. Use one of: json,csv,txt,pdf")
