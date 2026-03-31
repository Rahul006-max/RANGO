"""Pipeline definitions and helpers."""

from __future__ import annotations

import json
import random
from typing import Any, Dict, Optional

SYSTEM_PIPELINES = [
    {"name": "Balanced (MMR)", "chunk_size": 800, "overlap": 120, "search_type": "mmr", "k": 6},
    {"name": "Fastest (Similarity)", "chunk_size": 500, "overlap": 60, "search_type": "similarity", "k": 4},
    {"name": "Accurate (Similarity + Larger k)", "chunk_size": 900, "overlap": 150, "search_type": "similarity", "k": 8},
    {"name": "DeepSearch (MMR + Higher k)", "chunk_size": 1200, "overlap": 200, "search_type": "mmr", "k": 10},
]

PIPELINES = SYSTEM_PIPELINES  # Backwards-compatible alias

# Metadata-only descriptor for tree-indexed collections (not used in vector builds)
PAGE_INDEX_PIPELINE = {"name": "PageIndex Tree", "type": "tree"}

DEFAULT_PIPELINE_CONFIG = {
    "preset_name": "Balanced",
    "chunk_size": 800,
    "overlap": 120,
    "top_k": 6,
    "search_type": "mmr",
}


PIPELINE_PRESETS = {
    "fast": {
        "preset_name": "Fastest (Similarity)",
        "chunk_size": 500,
        "overlap": 60,
        "top_k": 4,
        "search_type": "similarity",
    },
    "balanced": {
        "preset_name": "Balanced (MMR)",
        "chunk_size": 800,
        "overlap": 120,
        "top_k": 6,
        "search_type": "mmr",
    },
    "accurate": {
        "preset_name": "Accurate (Similarity + Larger k)",
        "chunk_size": 900,
        "overlap": 150,
        "top_k": 8,
        "search_type": "similarity",
    },
    "deepsearch": {
        "preset_name": "DeepSearch (MMR + Higher k)",
        "chunk_size": 1200,
        "overlap": 200,
        "top_k": 10,
        "search_type": "mmr",
    },
}


def get_pipeline_preset(preset_key: str) -> Optional[Dict[str, Any]]:
    if not preset_key:
        return None
    return PIPELINE_PRESETS.get(str(preset_key).strip().lower())


def parse_pipeline_config_from_any(raw: Any) -> Optional[Dict[str, Any]]:
    if raw is None:
        return None
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        stripped = raw.strip()
        if not stripped:
            return None
        try:
            return json.loads(stripped)
        except Exception:
            return None
    return None


def normalize_search_type(search_type: str) -> str:
    if not search_type:
        return "similarity"
    value = str(search_type).lower().strip()
    allowed = {"similarity", "similarity_score_threshold", "mmr"}
    if value in allowed:
        return value
    if value == "semantic":
        return "similarity"
    if value == "hybrid":
        return "mmr"
    if value == "bm25":
        return "similarity"
    return "similarity"


def jitter_int(value: int, delta: int, min_val: int = 1) -> int:
    return max(min_val, int(value + random.uniform(-delta, delta)))


def randomized_weights() -> Dict[str, float]:
    weights = {
        "relevance": random.uniform(0.35, 0.45),
        "grounded": random.uniform(0.25, 0.35),
        "quality": random.uniform(0.15, 0.25),
        "efficiency": random.uniform(0.05, 0.15),
    }
    total = sum(weights.values())
    return {k: round(v / total, 3) for k, v in weights.items()}
