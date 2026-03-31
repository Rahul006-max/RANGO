"""Token and cost estimation helpers."""

from __future__ import annotations

from typing import Any, Dict, Optional

import tiktoken

# Module-level encoding object — avoids re-initialising tiktoken on every call
# (tiktoken.get_encoding re-parses the vocab on each call, ~5–20 ms each time).
_ENC = tiktoken.get_encoding("cl100k_base")


def safe_int(value):
    try:
        return int(value)
    except Exception:
        return None


def extract_tokens_from_llm_response(llm_response: Any) -> Dict[str, Optional[int]]:
    prompt_tokens = None
    completion_tokens = None
    total_tokens = None

    try:
        if hasattr(llm_response, "usage"):
            usage = llm_response.usage
            prompt_tokens = safe_int(getattr(usage, "prompt_tokens", None))
            completion_tokens = safe_int(getattr(usage, "completion_tokens", None))
            total_tokens = safe_int(getattr(usage, "total_tokens", None))
        elif isinstance(llm_response, dict) and "usage" in llm_response:
            usage = llm_response["usage"]
            prompt_tokens = safe_int(usage.get("prompt_tokens"))
            completion_tokens = safe_int(usage.get("completion_tokens"))
            total_tokens = safe_int(usage.get("total_tokens"))
    except Exception:
        pass

    return {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
    }


def estimate_tokens(text: str, encoding_name: str = "cl100k_base") -> int:
    try:
        enc = _ENC if encoding_name == "cl100k_base" else tiktoken.get_encoding(encoding_name)
        return len(enc.encode(text))
    except Exception:
        return len(text) // 4


def estimate_cost_usd(tokens: Dict[str, Optional[int]], model: str = "qwen2.5:3b") -> Optional[float]:
    try:
        total = tokens.get("total_tokens")
        if not total:
            return 0.0
        if "ollama" in model.lower() or "qwen" in model.lower():
            return 0.0
        rate_per_token = 0.0000005
        return round(total * rate_per_token, 6)
    except Exception:
        return 0.0
