"""
Page Index Tree Retrieval — traverse the tree using the LLM to find the
most relevant leaf node for a given query.

No embeddings or vector database involved — the LLM reads summaries at each
level and chooses the most relevant branch.
"""

from __future__ import annotations

from langchain_core.messages import HumanMessage

from dependencies import get_llm_fast


# ---------------------------------------------------------------------------
# Prompt
# ---------------------------------------------------------------------------
_SELECT_BRANCH_PROMPT = (
    "You are a document navigation assistant. A user asked:\n\n"
    "Question: {question}\n\n"
    "Below are summaries of different sections of a document. "
    "Reply with ONLY the number (1-based index) of the section most likely "
    "to contain the answer. Reply with a single integer and nothing else.\n\n"
    "{options}"
)


def _pick_best_child(question: str, children: list[dict], model_name: str | None = None, api_key: str | None = None, temperature: float | None = None) -> int:
    """Use the LLM to select the index of the most relevant child node."""
    if len(children) == 1:
        return 0

    options_text = "\n".join(
        f"{i + 1}. [{child['title']}]: {child['summary']}"
        for i, child in enumerate(children)
    )
    prompt = _SELECT_BRANCH_PROMPT.format(question=question, options=options_text)

    llm = get_llm_fast(model_name=model_name, api_key=api_key, temperature=temperature)
    result = llm.invoke([HumanMessage(content=prompt)])
    content = (result.content if hasattr(result, "content") else str(result)).strip()

    # Parse the integer from the response
    try:
        idx = int(content.strip().split()[0]) - 1  # 1-based → 0-based
        if 0 <= idx < len(children):
            return idx
    except (ValueError, IndexError):
        pass

    # Fallback: return 0 (first child)
    print(f"[WARN] Could not parse branch choice '{content}', defaulting to first child")
    return 0


def retrieve_with_tree(question: str, tree: dict, model_name: str | None = None, api_key: str | None = None, temperature: float | None = None) -> str:
    """
    Traverse the PageIndex tree top-down, using the LLM to pick the best
    branch at each level, until a leaf node is reached.
    
    Args:
        question: User's query.
        tree: PageIndex tree root node.
        model_name: Optional model name override (None = system default).
        api_key: Optional API key for custom models.
        temperature: Optional temperature override.

    Returns:
        The raw page text from the selected leaf node.
    """
    node = tree

    depth = 0
    while node.get("children"):
        depth += 1
        children = node["children"]
        best_idx = _pick_best_child(question, children, model_name=model_name, api_key=api_key, temperature=temperature)
        chosen = children[best_idx]
        print(f"  [SEARCH] Depth {depth}: chose '{chosen['title']}' (branch {best_idx + 1}/{len(children)})")
        node = chosen

    # Leaf node — return its text
    leaf_text = node.get("text", node.get("summary", ""))
    print(f"  [LEAF] Reached leaf: '{node['title']}' ({len(leaf_text)} chars)")
    return leaf_text


def retrieve_with_tree_trace(question: str, tree: dict, model_name: str | None = None, api_key: str | None = None, temperature: float | None = None) -> tuple[str, list[dict]]:
    """Same traversal as retrieve_with_tree, but also returns a structured path."""
    node = tree
    path: list[dict] = []
    depth = 0

    while node.get("children"):
        depth += 1
        children = node["children"]
        best_idx = _pick_best_child(question, children, model_name=model_name, api_key=api_key, temperature=temperature)
        chosen = children[best_idx]
        path.append(
            {
                "depth": depth,
                "chosen_branch": best_idx + 1,
                "total_branches": len(children),
                "title": chosen.get("title"),
                "summary": chosen.get("summary", "")[:300],
            }
        )
        print(f"  [SEARCH] Depth {depth}: chose '{chosen['title']}' (branch {best_idx + 1}/{len(children)})")
        node = chosen

    leaf_text = node.get("text", node.get("summary", ""))
    path.append(
        {
            "depth": depth + 1,
            "node_type": "leaf",
            "title": node.get("title"),
            "leaf_chars": len(leaf_text),
        }
    )
    print(f"  [LEAF] Reached leaf: '{node['title']}' ({len(leaf_text)} chars)")
    return leaf_text, path
