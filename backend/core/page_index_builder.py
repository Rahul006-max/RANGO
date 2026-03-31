"""
Page Index Tree Builder — constructs a hierarchical summary tree from documents.

Each leaf node holds raw page text + a summary.  Parent nodes hold a summary
of their children.  The recursion continues until a single root node remains.
"""

from __future__ import annotations

import uuid
from typing import List

from langchain_core.documents import Document
from langchain_core.messages import HumanMessage

from dependencies import get_llm_fast


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------
_SUMMARIZE_PAGE_PROMPT = (
    "Summarize the following page of a document in 2-3 concise sentences. "
    "Focus on the key facts, topics, and arguments.\n\n"
    "Page text:\n{text}\n\nSummary:"
)

_SUMMARIZE_GROUP_PROMPT = (
    "Below are summaries of consecutive sections of a document. "
    "Write a single concise summary (2-3 sentences) that captures the "
    "main themes across all sections.\n\n"
    "{summaries}\n\nCombined summary:"
)

GROUP_SIZE = 5  # pages per parent node


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _llm_summarize(text: str, model_name: str | None = None, api_key: str | None = None, temperature: float | None = None) -> str:
    """Call the fast LLM to produce a short summary."""
    llm = get_llm_fast(model_name=model_name, api_key=api_key, temperature=temperature)
    prompt = _SUMMARIZE_PAGE_PROMPT.format(text=text[:3000])
    result = llm.invoke([HumanMessage(content=prompt)])
    return (result.content if hasattr(result, "content") else str(result)).strip()


def _llm_summarize_group(summaries: List[str], model_name: str | None = None, api_key: str | None = None, temperature: float | None = None) -> str:
    """Summarize a group of child summaries into one parent summary."""
    llm = get_llm_fast(model_name=model_name, api_key=api_key, temperature=temperature)
    block = "\n\n".join(f"- {s}" for s in summaries)
    prompt = _SUMMARIZE_GROUP_PROMPT.format(summaries=block)
    result = llm.invoke([HumanMessage(content=prompt)])
    return (result.content if hasattr(result, "content") else str(result)).strip()


def _make_leaf(page_num: int, text: str, summary: str) -> dict:
    return {
        "id": str(uuid.uuid4()),
        "title": f"Page {page_num + 1}",
        "summary": summary,
        "children": [],
        "text": text,  # only leaf nodes carry raw text
    }


def _make_parent(title: str, summary: str, children: List[dict]) -> dict:
    return {
        "id": str(uuid.uuid4()),
        "title": title,
        "summary": summary,
        "children": children,
        # no "text" key — parent nodes only hold summaries
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def build_page_index_tree(
    documents: List[Document],
    model_name: str | None = None,
    api_key: str | None = None,
    temperature: float | None = None,
) -> dict:
    """
    Build a hierarchical PageIndex tree from a list of LangChain Documents.

    Each Document is assumed to represent one page (as produced by PyPDFLoader).

    Args:
        documents: List of Document objects (one per page).
        model_name: Optional model name override (None = system default).
        api_key: Optional API key for custom models.
        temperature: Optional temperature override.

    Returns a nested dict:
        {id, title, summary, children[], text?}
    """
    if not documents:
        return _make_parent("Root", "Empty document.", [])

    # Step 1 — Create leaf nodes (one per page) with LLM summaries
    print(f"[PageIndex] Building tree for {len(documents)} page(s)...")
    leaves: List[dict] = []
    for idx, doc in enumerate(documents):
        page_text = doc.page_content.strip()
        if not page_text:
            page_text = "(blank page)"
        try:
            summary = _llm_summarize(page_text, model_name=model_name, api_key=api_key, temperature=temperature)
        except Exception as exc:
            print(f"  [WARN] Summarize failed for page {idx}: {exc}")
            summary = page_text[:200]
        leaves.append(_make_leaf(idx, page_text, summary))
        print(f"  [OK] Page {idx + 1}/{len(documents)} summarized")

    # Step 2 — Recursively group leaves into parent nodes
    current_level = leaves
    level_num = 0

    while len(current_level) > 1:
        level_num += 1
        next_level: List[dict] = []

        for i in range(0, len(current_level), GROUP_SIZE):
            group = current_level[i : i + GROUP_SIZE]
            child_summaries = [n["summary"] for n in group]
            try:
                parent_summary = _llm_summarize_group(child_summaries, model_name=model_name, api_key=api_key, temperature=temperature)
            except Exception as exc:
                print(f"  [WARN] Group summarize failed at level {level_num}: {exc}")
                parent_summary = " ".join(child_summaries)[:300]

            start_page = group[0]["title"]
            end_page = group[-1]["title"]
            title = f"Section: {start_page} – {end_page}" if len(group) > 1 else start_page
            next_level.append(_make_parent(title, parent_summary, group))

        print(f"  [TREE] Level {level_num}: {len(current_level)} nodes -> {len(next_level)} parent(s)")
        current_level = next_level

    root = current_level[0]
    root["title"] = "Root"
    print("[OK] PageIndex tree built successfully")
    return root
