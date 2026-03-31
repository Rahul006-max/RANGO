"""Scoring utilities for pipeline evaluation."""

from __future__ import annotations

from utils.text_utils import normalize


def context_quality_score(context: str) -> int:
    length = len(context)
    if length < 150:
        return 3
    if length <= 1200:
        return 10
    if length <= 2500:
        return 7
    return 5


def efficiency_score(context: str, top_k: int) -> int:
    length = len(context)
    score = 10
    if top_k >= 12:
        score -= 4
    elif top_k >= 10:
        score -= 3
    elif top_k >= 8:
        score -= 2
    elif top_k >= 6:
        score -= 1

    if length > 3000:
        score -= 3
    elif length > 2000:
        score -= 2
    elif length > 1200:
        score -= 1
    return max(0, min(10, score))


def relevance_score(question: str, context: str, top_k: int = 4) -> int:
    q = normalize(question)
    ctx = normalize(context)
    q_words = [w for w in q.split() if len(w) >= 4]
    if not q_words:
        return 5
    hits = sum(1 for w in q_words if w in ctx)
    ratio = hits / len(q_words)
    # Normalize by k: larger-k pipelines retrieve more context which inflates raw
    # keyword coverage — apply a mild sub-linear penalty so accuracy/deepsearch
    # can't win purely by volume.
    k_factor = (max(top_k, 4) / 4) ** 0.3
    adj_ratio = ratio / k_factor
    if adj_ratio >= 0.6:
        return 10
    if adj_ratio >= 0.4:
        return 8
    if adj_ratio >= 0.25:
        return 6
    return 3


def grounded_score(answer: str, context: str) -> int:
    ans = normalize(answer)
    ctx = normalize(context)

    if not ans or "i dont know" in ans or "i don't know" in ans:
        return 6
    ans_words = [w for w in ans.split() if len(w) >= 4]
    if not ans_words:
        return 5

    hits = sum(1 for w in ans_words if w in ctx)
    ratio = hits / len(ans_words)

    if ratio >= 0.6:
        return 10
    if ratio >= 0.4:
        return 8
    if ratio >= 0.25:
        return 6
    return 3


def compute_advanced_metrics(chunk_texts: list[str], answer: str, question: str) -> dict:
    """
    Compute advanced retrieval metrics for the winning pipeline.

    Args:
        chunk_texts: List of raw page_content strings from retrieved Document objects.
        answer:      Final answer text produced by the LLM.
        question:    Original user question.

    Returns:
        dict with precision_at_k, context_coverage_percent,
        chunk_utilization_rate, retrieval_efficiency_ratio.
    """
    # Reuse the same normalizer as the rest of the scoring module
    q_norm = normalize(question)
    ans_norm = normalize(answer)

    # Significant words: length >= 4 to match existing scoring convention
    q_words = set(w for w in q_norm.split() if len(w) >= 4)
    ans_words = [w for w in ans_norm.split() if len(w) >= 4]
    ans_word_set = set(ans_words)

    k = len(chunk_texts)  # actual number of chunks returned (may be < top_k after dedup)

    # ── precision_at_k ──────────────────────────────────────────────────────
    # A chunk is "relevant" if it contains >= 25% of the question's sig words.
    # Mirrors the threshold used by relevance_score() at the "ratio >= 0.25" band.
    if k == 0 or not q_words:
        precision_at_k = 0.0
    else:
        relevant_chunks = sum(
            1 for chunk in chunk_texts
            if sum(1 for w in q_words if w in normalize(chunk)) / len(q_words) >= 0.25
        )
        precision_at_k = round(relevant_chunks / k, 4)

    # ── context_coverage_percent ─────────────────────────────────────────────
    # Fraction of answer's sig words that appear anywhere in the retrieved context.
    if not ans_words:
        context_coverage_percent = 0.0
    else:
        full_context_norm = normalize(" ".join(chunk_texts))
        covered = sum(1 for w in ans_words if w in full_context_norm)
        context_coverage_percent = round((covered / len(ans_words)) * 100, 2)

    # ── chunk_utilization_rate ───────────────────────────────────────────────
    # Fraction of chunks that share at least one sig word with the answer.
    if k == 0 or not ans_word_set:
        chunk_utilization_rate = 0.0
    else:
        utilized = sum(
            1 for chunk in chunk_texts
            if ans_word_set & set(w for w in normalize(chunk).split() if len(w) >= 4)
        )
        chunk_utilization_rate = round(utilized / k, 4)

    # ── retrieval_efficiency_ratio ───────────────────────────────────────────
    # Answer token count / total context token count.
    # Uses simple whitespace split to avoid importing tiktoken here
    # (keeps this module dependency-free; ask_service can call estimate_tokens
    # separately if higher accuracy is ever needed).
    context_token_count = sum(len(chunk.split()) for chunk in chunk_texts)
    answer_token_count = len(answer.split())
    if context_token_count == 0:
        retrieval_efficiency_ratio = 0.0
    else:
        retrieval_efficiency_ratio = round(answer_token_count / context_token_count, 4)

    return {
        "precision_at_k": precision_at_k,
        "context_coverage_percent": context_coverage_percent,
        "chunk_utilization_rate": chunk_utilization_rate,
        "retrieval_efficiency_ratio": retrieval_efficiency_ratio,
    }


def pipeline_score(question: str, context: str, top_k: int, answer: str = "", weights: dict | None = None) -> dict:
    rel = relevance_score(question, context, top_k)  # pass top_k for k-normalization
    qual = context_quality_score(context)
    eff = efficiency_score(context, top_k)
    gro = grounded_score(answer, context) if answer else 5

    w = weights or {
        "relevance": 0.35,
        "grounded": 0.35,
        "quality": 0.15,
        "efficiency": 0.15,
    }

    final = round(
        (w["relevance"] * rel)
        + (w["grounded"] * gro)
        + (w["quality"] * qual)
        + (w["efficiency"] * eff),
        2,
    )

    return {
        "relevance": rel,
        "grounded": gro,
        "quality": qual,
        "efficiency": eff,
        "final": final,
        "weights": w,
    }
