"""Timing helpers for latency instrumentation."""

from __future__ import annotations

import time


def now_ms() -> float:
    return time.perf_counter() * 1000


def elapsed_ms(start: float) -> float:
    return round(now_ms() - start, 2)


def empty_global_timings() -> dict:
    return {
        "embedding_ms": 0,
        "retrieval_ms": 0,
        "rerank_ms": 0,
        "llm_ms": 0,
        "smart_extract_ms": 0,
        "total_ms": 0,
    }


def empty_pipeline_latency(pipeline_name: str) -> dict:
    return {
        "pipeline": pipeline_name,
        "retrieval_ms": 0,
        "context_build_ms": 0,
        "scoring_ms": 0,
        "total_ms": 0,
    }
