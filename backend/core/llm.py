"""LLM helpers for textual and vision workflows."""

from __future__ import annotations

import base64
import re
from typing import Any, Dict, Tuple

from langchain_core.prompts import ChatPromptTemplate

from config import get_settings
from dependencies import get_llm, get_llm_fast
from core.scoring import grounded_score
from utils.text_utils import enrich_answer_if_duration
from utils.token_utils import estimate_cost_usd, estimate_tokens

settings = get_settings()

FAILURE_VISION_UNAVAILABLE = "vision_unavailable"
FAILURE_VISION_TIMEOUT = "vision_timeout"
FAILURE_LLM = "llm_failure"
FAILURE_STORAGE = "storage_failure"


def describe_image_with_groq(image_bytes: bytes, mime_type: str = "image/jpeg") -> str:
    """
    Use Groq Vision API to describe an image.
    Returns a detailed text description suitable for RAG indexing.
    """
    if not settings.groq_api_key:
        return ""
    try:
        from langchain_groq import ChatGroq
        from langchain_core.messages import HumanMessage

        vision_llm = ChatGroq(
            model=settings.groq_vision_model,
            api_key=settings.groq_api_key,
            temperature=0.1,
        )
        b64 = base64.b64encode(image_bytes).decode("utf-8")
        message = HumanMessage(content=[
            {
                "type": "text",
                "text": (
                    "Describe this image in precise, factual detail. "
                    "Include all visible text, numbers, labels, chart values, "
                    "diagram elements, and any other content. "
                    "Be thorough — this description will be used to answer questions about a document."
                ),
            },
            {
                "type": "image_url",
                "image_url": {"url": f"data:{mime_type};base64,{b64}"},
            },
        ])
        response = vision_llm.invoke([message])
        content = response.content if hasattr(response, "content") else str(response)
        if not isinstance(content, str):
            content = str(content)
        return content.strip()
    except Exception as exc:
        print(f"[WARN] Groq Vision failed ({type(exc).__name__}): {exc}")
        return ""


NORMAL_PROMPT = ChatPromptTemplate.from_template(
    """
You are a helpful assistant.
Answer the question ONLY using the context below.
If the answer is not in the context, say: "I don't know based on the documents."
Be concise — answer in 1-2 sentences.

Context:
{context}

Question:
{question}

Answer:
"""
)

STRICT_PROMPT = ChatPromptTemplate.from_template(
    """
You are an answer extraction system.

RULES:
- Use ONLY the provided context.
- Return ONLY the final answer (no explanation).
- If the answer is not present, return exactly: I don't know based on the documents.

Context:
{context}

Question:
{question}

Final Answer:
"""
)

SUMMARY_PROMPT = ChatPromptTemplate.from_template(
    """
You are a document analyst. Using ONLY the context provided below, write a clear and
complete response to the request. Synthesize information from all parts of the context.
Do NOT say "I don't know" — if partial information exists, use it.
Write 2-5 sentences.

Context:
{context}

Request:
{question}

Response:
"""
)

EXTRACTION_PROMPT = ChatPromptTemplate.from_template(
    """
You are an information extractor. Your ONLY job is to scan ALL of the provided context
chunks and extract every item that answers the question below.

RULES:
- Be EXHAUSTIVE — scan every sentence in the context.
- List ALL matches you find, even if you only find one.
- Format your answer as a clean comma-separated list or bullet list.
- Do NOT say "I don't know". If you find even partial information, list it.
- Do NOT add commentary — just the extracted items.

Context:
{context}

Question:
{question}

Extracted items:
"""
)

_SUMMARY_KEYWORDS = (
    "summarize", "summary", "overview", "describe", "what is this",
    "what does this", "what are the main", "main argument", "main point",
    "key point", "key argument", "main theme", "main topic", "outline",
    "briefly explain", "explain the", "what is the document",
)

_EXTRACTION_KEYWORDS = (
    "what are the names", "names present", "names in the", "names in this",
    "list all", "list the", "list every", "all the names", "all names",
    "who are the", "who are all", "people in", "people mentioned",
    "what are all the", "give me all", "give all", "enumerate",
    "what words", "what terms", "what topics", "what subjects",
    "what dates", "what numbers", "what figures", "what values",
    "all mentions of", "every mention", "all occurrences",
)


def _is_summary_question(question: str) -> bool:
    """Return True when the question calls for synthesis rather than fact lookup."""
    q = question.lower()
    return any(kw in q for kw in _SUMMARY_KEYWORDS)


def _is_extraction_question(question: str) -> bool:
    """Return True when the question asks for a list/enumeration of items."""
    q = question.lower()
    return any(kw in q for kw in _EXTRACTION_KEYWORDS)


def generate_answer_with_retry(
    question: str,
    context: str,
    fast: bool = False,
    model_name: str | None = None,
    api_key: str | None = None,
    temperature: float | None = None,
):
    """Generate an answer with optional retry logic.

    Automatically selects SUMMARY_PROMPT for broad/synthesis questions and
    NORMAL_PROMPT for specific fact-lookup questions.

    When ``fast=True``:
    - Smaller max_tokens LLM, no retry.

    When ``fast=False``:
    - Full LLM, retries with STRICT_PROMPT if grounded_score < 4
      (only for non-summary questions).
    
    Args:
        question: The user's question.
        context: The context/document text to answer from.
        fast: If True, use fast LLM (lower tokens). If False, full LLM with retry.
        model_name: Optional model name override (None = system default).
        api_key: Optional API key for custom models.
        temperature: Optional temperature override.
    """
    llm = get_llm_fast(model_name=model_name, api_key=api_key, temperature=temperature) if fast else get_llm(model_name=model_name, api_key=api_key, temperature=temperature)
    is_summary = _is_summary_question(question)
    is_extraction = _is_extraction_question(question)

    if is_summary:
        prompt_template = SUMMARY_PROMPT
    elif is_extraction:
        prompt_template = EXTRACTION_PROMPT
    else:
        prompt_template = NORMAL_PROMPT
    prompt1_text = prompt_template.format(context=context, question=question)
    chain1 = prompt_template | llm
    result1 = chain1.invoke({"context": context, "question": question})
    answer1 = (result1.content if hasattr(result1, "content") else str(result1)).strip()
    grounded1 = grounded_score(answer1, context)

    prompt_tokens = estimate_tokens(prompt1_text)
    completion_tokens = estimate_tokens(answer1)

    # Fast mode: single call, no retry
    if fast:
        tokens = {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
        }
        return answer1, {"attempts": 1, "grounded_before": grounded1, "grounded_after": grounded1}, tokens

    # Summary/extraction questions synthesize from context — no STRICT retry needed
    if is_summary or is_extraction or grounded1 >= 4:
        tokens = {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
        }
        return answer1, {"attempts": 1, "grounded_before": grounded1, "grounded_after": grounded1}, tokens

    # Fact-lookup fell below threshold — retry with STRICT_PROMPT
    prompt2_text = STRICT_PROMPT.format(context=context, question=question)
    chain2 = STRICT_PROMPT | llm
    result2 = chain2.invoke({"context": context, "question": question})
    answer2 = (result2.content if hasattr(result2, "content") else str(result2)).strip()
    grounded2 = grounded_score(answer2, context)

    prompt_tokens += estimate_tokens(prompt2_text)
    completion_tokens += estimate_tokens(answer2)

    tokens = {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": prompt_tokens + completion_tokens,
    }

    if grounded2 >= grounded1:
        return answer2, {"attempts": 2, "grounded_before": grounded1, "grounded_after": grounded2}, tokens
    return answer1, {"attempts": 2, "grounded_before": grounded1, "grounded_after": grounded1}, tokens


def answer_from_context(question: str, context: str) -> Tuple[str, Dict[str, int], str | None]:
    try:
        answer, _retry_meta, token_usage = generate_answer_with_retry(question, context)
        token_usage["model"] = settings.groq_model
        return answer.strip(), token_usage, None
    except Exception as exc:
        print(f"[WARN] LLM answer generation failed: {exc}")
        return "", {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "model": settings.groq_model}, FAILURE_LLM


def calculate_confidence(answer: str, description: str, failure_type: str | None) -> float:
    if failure_type in (FAILURE_VISION_UNAVAILABLE, FAILURE_VISION_TIMEOUT, FAILURE_LLM):
        return 2.0
    if not answer or not description:
        return 1.0

    score = 8.0
    if len(answer) < 20:
        score -= 2.0
    uncertainty_markers = ["unsure", "cannot", "don't know", "unclear", "maybe", "possibly"]
    hits = sum(1 for marker in uncertainty_markers if marker in answer.lower())
    score -= min(hits * 1.0, 3.0)
    if len(description) > 200:
        score += 0.5
    return round(max(0.0, min(10.0, score)), 1)


def check_vision_model() -> bool:
    """Return True if Groq Vision is available (requires GROQ_API_KEY)."""
    return bool(settings.groq_api_key)


def generate_image_description(image_bytes: bytes) -> tuple[str, str | None]:
    """Describe an image using Groq Vision (replaces old Ollama llava path)."""
    if not settings.groq_api_key:
        return "", FAILURE_VISION_UNAVAILABLE
    desc = describe_image_with_groq(image_bytes)
    return (desc, None) if desc else ("", FAILURE_VISION_UNAVAILABLE)


_CONF_GRADE_PROMPT = """You are an image QA evaluator.

Image description (what the vision model saw):
{description}

User question: {question}

Answer given: {answer}

Rate how accurately and completely the answer is supported by the image description.
Consider:
- Does the answer directly address the question using information from the description?
- Is the answer factually consistent with the description?
- Is the answer appropriately specific (not vague or evasive)?

Reply with ONLY a single integer from 1 to 10. Nothing else."""


def llm_grade_confidence(
    question: str,
    description: str,
    answer: str,
    failure_type: str | None,
    model_name: str | None = None,
    api_key: str | None = None,
    temperature: float | None = None,
) -> float:
    """Ask the LLM to self-grade how well the answer matches the image description.
    Falls back to calculate_confidence() on any error.
    
    Args:
        question: The user's question.
        description: The image description.
        answer: The generated answer.
        failure_type: Any failure type encountered (vision/llm).
        model_name: Optional model name override (None = system default).
        api_key: Optional API key for custom models.
        temperature: Optional temperature override.
    """
    if failure_type in (FAILURE_VISION_UNAVAILABLE, FAILURE_VISION_TIMEOUT, FAILURE_LLM):
        return 2.0
    if not answer or not description:
        return 1.0
    a_lower = answer.lower()
    refusals = [
        "i don't know based on", "cannot determine", "not enough information",
        "unable to answer", "not visible", "cannot see", "no information",
    ]
    if any(r in a_lower for r in refusals):
        return 3.0
    try:
        from langchain_core.messages import HumanMessage
        llm = get_llm_fast(model_name=model_name, api_key=api_key, temperature=temperature)
        prompt = _CONF_GRADE_PROMPT.format(
            description=description[:1000],
            question=question,
            answer=answer,
        )
        result = llm.invoke([HumanMessage(content=prompt)])
        content = result.content if hasattr(result, "content") else str(result)
        match = re.search(r"\b(\d+(?:\.\d+)?)\b", content.strip())
        if match:
            return round(max(0.0, min(10.0, float(match.group(1)))), 1)
    except Exception as exc:
        print(f"[WARN] LLM confidence grading failed: {exc}")
    return calculate_confidence(answer, description, failure_type)
