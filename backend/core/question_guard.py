"""Guards that keep the assistant scoped to uploaded documents."""

from __future__ import annotations

import re


DOCUMENT_SCOPE_REFUSAL = (
    "I can only answer questions about the uploaded documents. "
    "Please ask something that can be answered from this collection."
)

_DOC_REFERENCE_PATTERNS = (
    r"\b(document|documents|doc|docs|pdf|file|files|collection|context|paper|report)\b",
    r"\b(uploaded|attached|this|these|above)\b",
    r"\baccording to\b",
    r"\bbased on\b",
)

_SMALL_TALK_PATTERNS = (
    r"^\s*(hi|hello|hey|yo|sup|good morning|good afternoon|good evening)\s*[!.?]*\s*$",
    r"\bhow are you\b",
    r"\bwhat are you\b",
    r"\bwhat are u\b",
    r"\bwho are you\b",
    r"\bwho are u\b",
    r"\btell me about yourself\b",
    r"\bwhat can you do\b",
    r"\bare you (an )?(ai|bot|assistant)\b",
    r"\byour name\b",
)

_GENERAL_TASK_PATTERNS = (
    r"\b(recipe|recipes|cook|cooking|bake|baking|cake|pizza|pasta)\b",
    r"\bweather\b",
    r"\bnews\b",
    r"\bjoke\b",
    r"\bstory\b",
    r"\bpoem\b",
    r"\bsong\b",
    r"\bmovie recommendation\b",
    r"\btravel plan\b",
    r"\bworkout\b",
    r"\bdiet plan\b",
    r"\bwrite (a )?(code|program|script|essay|email|letter)\b",
    r"\bsolve this math\b",
    r"\btranslate\b",
)


def has_document_reference(question: str) -> bool:
    q = (question or "").lower().strip()
    return any(re.search(pattern, q) for pattern in _DOC_REFERENCE_PATTERNS)


def is_out_of_document_scope(question: str) -> bool:
    """Return True for small talk and general requests not tied to the docs."""
    q = (question or "").lower().strip()
    if not q:
        return False
    if has_document_reference(q):
        return False
    if any(re.search(pattern, q) for pattern in _SMALL_TALK_PATTERNS):
        return True
    if any(re.search(pattern, q) for pattern in _GENERAL_TASK_PATTERNS):
        return True
    return False
