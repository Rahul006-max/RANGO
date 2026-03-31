"""Shared dependencies, clients, and singletons for the backend."""

from __future__ import annotations

import os
import time
import threading
from typing import Any, Dict, Tuple

from fastapi import Header, HTTPException
from supabase import Client, create_client

from config import get_settings

settings = get_settings()


# -------------------------
# Supabase clients
# -------------------------
_supabase_admin: Client | None = None


def get_supabase_admin() -> Client:
    """Return the service-role Supabase client (bypasses RLS)."""
    global _supabase_admin
    if _supabase_admin is None:
        _supabase_admin = create_client(settings.supabase_url, settings.supabase_service_role_key)
    return _supabase_admin


def get_supabase_user_client(access_token: str) -> Client:
    """Return a user-scoped Supabase client with RLS enabled."""
    client = create_client(settings.supabase_url, settings.supabase_anon_key)
    client.postgrest.auth(access_token)
    return client


# -------------------------
# JWT helpers
# -------------------------
def verify_supabase_jwt(token: str) -> Dict[str, Any]:
    """Validate a Supabase JWT via the Supabase admin API (handles all key types)."""
    now = time.time()
    cached = _TOKEN_CACHE.get(token)
    if cached:
        payload, expires_at = cached
        if now < expires_at:
            return payload

    try:
        admin = get_supabase_admin()
        response = admin.auth.get_user(token)
        user = response.user
        if not user:
            raise ValueError("No user returned")
        payload = {
            "sub": user.id,
            "email": user.email,
            "role": user.role,
            "access_token": token,
        }
        _TOKEN_CACHE[token] = (payload, now + _TOKEN_CACHE_TTL)
        return payload
    except Exception as exc:
        raise HTTPException(status_code=401, detail=f"JWT verification failed: {exc}") from exc


def get_current_user(authorization: str = Header(None)) -> Dict[str, Any]:
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing Authorization header")
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid Authorization header format")

    token = authorization.replace("Bearer ", "").strip()
    if not token:
        raise HTTPException(status_code=401, detail="Empty token")

    return verify_supabase_jwt(token)


# -------------------------
# Global caches
# -------------------------
PIPELINE_DB_PATHS: Dict[str, Dict[str, str]] = {}
QA_CACHE: Dict[str, Dict[str, Any]] = {}
COLLECTION_FULLTEXT: Dict[str, str] = {}
PREFERRED_PIPELINE_CACHE: Dict[str, str] = {}  # key: "user_id:collection_id" -> pipeline name
BUILD_STATS_CACHE: Dict[str, list] = {}  # key: collection_id -> list of build stat rows

# 55-second token validation cache — avoids a Supabase round-trip on every request
_TOKEN_CACHE: Dict[str, Tuple[Dict[str, Any], float]] = {}
_TOKEN_CACHE_TTL = 55  # seconds

# Chroma vectorstore instance cache (keyed by persist_directory path)
_VECTORSTORE_CACHE: Dict[str, Any] = {}


def get_vectorstore(persist_dir: str, embeddings=None):
    """Return a cached Chroma vectorstore instance, creating one if needed."""
    if persist_dir in _VECTORSTORE_CACHE:
        return _VECTORSTORE_CACHE[persist_dir]
    from langchain_community.vectorstores import Chroma
    if embeddings is None:
        embeddings = get_embeddings()
    vs = Chroma(persist_directory=persist_dir, embedding_function=embeddings)
    _VECTORSTORE_CACHE[persist_dir] = vs
    return vs


def invalidate_vectorstore_cache(collection_id: str) -> None:
    """Remove cached vectorstores for a collection (e.g. after delete/rebuild)."""
    keys_to_remove = [k for k in _VECTORSTORE_CACHE if collection_id in k]
    for k in keys_to_remove:
        _VECTORSTORE_CACHE.pop(k, None)


# -------------------------
# Supabase pgvector search
# -------------------------
import numpy as np


def _mmr_rerank(query_embedding, candidate_embeddings, candidate_docs, k: int, lambda_mult: float = 0.5):
    """
    Maximal Marginal Relevance re-ranking.
    Picks k documents that balance relevance to the query with diversity among themselves.
    """
    if not candidate_docs or k <= 0:
        return []
    q = np.array(query_embedding, dtype=np.float32)
    embs = np.array(candidate_embeddings, dtype=np.float32)
    # Cosine similarities to query
    q_norm = q / (np.linalg.norm(q) + 1e-9)
    emb_norms = embs / (np.linalg.norm(embs, axis=1, keepdims=True) + 1e-9)
    sim_to_query = emb_norms @ q_norm  # shape (n,)

    selected_indices = []
    remaining = list(range(len(candidate_docs)))

    for _ in range(min(k, len(remaining))):
        if not remaining:
            break
        if not selected_indices:
            # First pick: highest similarity to query
            best_idx = max(remaining, key=lambda i: sim_to_query[i])
        else:
            best_score = -1e9
            best_idx = remaining[0]
            sel_embs = emb_norms[selected_indices]  # (s, d)
            for idx in remaining:
                relevance = float(sim_to_query[idx])
                max_sim_to_selected = float(np.max(emb_norms[idx] @ sel_embs.T))
                mmr_score = lambda_mult * relevance - (1 - lambda_mult) * max_sim_to_selected
                if mmr_score > best_score:
                    best_score = mmr_score
                    best_idx = idx
        selected_indices.append(best_idx)
        remaining.remove(best_idx)

    return [candidate_docs[i] for i in selected_indices]


def supabase_vector_search(
    collection_id: str,
    pipeline_name: str,
    query_text: str,
    k: int,
    search_type: str,
    access_token: str,
    query_embedding=None,
):
    """
    Vector similarity search via Supabase pgvector.
    Replaces ChromaDB-backed retrieval with a direct Supabase RPC call.

    Pass a pre-computed `query_embedding` to skip redundant embed_query calls
    when the same question is searched across multiple pipelines in parallel.

    Returns a list of LangChain Document objects.
    """
    from langchain_core.documents import Document
    embeddings_model = get_embeddings()
    if query_embedding is None:
        query_embedding = embeddings_model.embed_query(query_text)

    sb = get_supabase_user_client(access_token)

    # For MMR, fetch more candidates then re-rank
    fetch_k = k * 3 if search_type == "mmr" else k

    try:
        rpc_res = sb.rpc("match_chunks", {
            "query_embedding": query_embedding,
            "p_collection_id": collection_id,
            "p_pipeline_name": pipeline_name,
            "p_k": fetch_k,
        }).execute()
    except Exception as e:
        print(f"[WARN] pgvector RPC failed, falling back to Chroma: {e}")
        # Graceful fallback to local Chroma if RPC not set up yet
        db_path = PIPELINE_DB_PATHS.get(collection_id, {}).get(pipeline_name)
        if db_path:
            vs = get_vectorstore(db_path, embeddings_model)
            if search_type == "mmr":
                return vs.max_marginal_relevance_search(query_text, k=k)
            else:
                return vs.similarity_search(query_text, k=k)
        return []

    rows = rpc_res.data or []
    if not rows:
        return []

    docs = []
    for r in rows:
        doc = Document(
            page_content=r["chunk_text"],
            metadata={
                "source": r.get("filename", ""),
                "page": r.get("page_number"),
                "file_id": r.get("file_id"),
                "chunk_index": r.get("chunk_index"),
                "similarity": r.get("similarity", 0),
            }
        )
        docs.append(doc)

    if search_type == "mmr" and len(docs) > k:
        # Fast page-diversity heuristic — no re-embedding needed.
        # Prefer chunks from different (file_id, page) pairs before falling
        # back to duplicate pages. This avoids the ~400-800 ms embed_documents
        # call while still achieving meaningful result diversity.
        seen_pages: set = set()
        diverse: list = []
        rest: list = []
        for d in docs:
            key = (d.metadata.get("file_id"), d.metadata.get("page"))
            if key not in seen_pages:
                seen_pages.add(key)
                diverse.append(d)
            else:
                rest.append(d)
        docs = (diverse + rest)

    return docs[:k]


# -------------------------
# Embeddings & LLM singletons
# -------------------------
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_ollama import OllamaEmbeddings
from langchain_groq import ChatGroq

_embeddings = None
_llm = None
_llm_fast = None  # Smaller max_tokens variant for fast mode — reduces Groq latency
_embeddings_lock = threading.Lock()


def _init_embedding_model():
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
    os.environ.setdefault(
        "SENTENCE_TRANSFORMERS_HOME",
        os.path.join(os.path.expanduser("~"), ".cache", "huggingface", "hub"),
    )
    provider = (settings.embedding_provider or "huggingface").strip().lower()

    if provider == "ollama":
        return OllamaEmbeddings(model=settings.ollama_embed_model)

    # Default provider is HuggingFace sentence-transformers.
    # Force CPU device to avoid torch meta-device transfer issues in some
    # transformers/sentence-transformers combinations.
    return HuggingFaceEmbeddings(
        model_name=settings.huggingface_model,
        model_kwargs={
            "local_files_only": True,
            "trust_remote_code": False,
            "device": "cpu",
        },
        encode_kwargs={"normalize_embeddings": True},
    )


def _is_meta_tensor_error(exc: Exception) -> bool:
    message = str(exc).lower()
    patterns = (
        "meta tensor",
        "to_empty",
        "cannot copy out of meta",
        "is on the meta device",
        "from meta",
    )
    return (
        any(pattern in message for pattern in patterns)
    )


def _retry_huggingface_embeddings_on_cpu():
    return HuggingFaceEmbeddings(
        model_name=settings.huggingface_model,
        model_kwargs={
            "local_files_only": True,
            "trust_remote_code": False,
            "device": "cpu",
        },
        encode_kwargs={"normalize_embeddings": True},
    )


def get_embeddings():
    global _embeddings
    if _embeddings is None:
        with _embeddings_lock:
            if _embeddings is None:
                provider = (settings.embedding_provider or "huggingface").strip().lower()
                try:
                    _embeddings = _init_embedding_model()
                except Exception as exc:
                    if provider == "huggingface" and _is_meta_tensor_error(exc):
                        print(
                            "[WARN] HuggingFace embeddings init hit meta tensor transfer issue "
                            f"for model '{settings.huggingface_model}'. Retrying on explicit CPU..."
                        )
                        _embeddings = _retry_huggingface_embeddings_on_cpu()
                    else:
                        raise
    return _embeddings


def get_llm(model_name=None, api_key=None, temperature=None):
    """
    Get LLM instance for answer generation.
    
    Args:
        model_name: Optional override model name. If None, uses system default (cached).
        api_key: Optional override API key (required if model_name provided).
        temperature: Optional override temperature (default 0.1).
    
    Returns:
        ChatGroq instance (cached for system default, fresh for custom models).
    """
    global _llm
    
    # Use system default if no model specified
    if model_name is None:
        if _llm is None:
            if not settings.groq_api_key:
                raise RuntimeError(
                    "GROQ_API_KEY is not set. Add it to backend/.env — "
                    "get a free key at https://console.groq.com"
                )
            _llm = ChatGroq(
                model=settings.groq_model,
                api_key=settings.groq_api_key,
                temperature=0.1,
                streaming=True,
                max_tokens=1024,
            )
            print(f"Using Groq LLM: {settings.groq_model} (max_tokens=1024)")
        return _llm
    
    # Use system default singleton if requested model matches system model
    if model_name == settings.groq_model:
        if _llm is None:
            if not settings.groq_api_key:
                raise RuntimeError("GROQ_API_KEY is not set.")
            _llm = ChatGroq(
                model=settings.groq_model,
                api_key=settings.groq_api_key,
                temperature=temperature or 0.1,
                streaming=True,
                max_tokens=1024,
            )
            print(f"Using Groq LLM: {settings.groq_model} (max_tokens=1024)")
        return _llm
    
    # Custom model: create fresh instance (not cached to avoid memory bloat per user)
    if not api_key:
        raise ValueError("api_key required for custom models")
    
    return ChatGroq(
        model=model_name,
        api_key=api_key,
        temperature=temperature or 0.1,
        streaming=True,
        max_tokens=1024,
    )


def get_llm_fast(model_name=None, api_key=None, temperature=None):
    """
    Get fast LLM instance (lower max_tokens for reduced latency).
    
    Args:
        model_name: Optional override model name. If None, uses system default (cached).
        api_key: Optional override API key (required if model_name provided).
        temperature: Optional override temperature (default 0.1).
    
    Returns:
        ChatGroq instance (cached for system default, fresh for custom models).
    """
    global _llm_fast
    
    # Use system default if no model specified
    if model_name is None:
        if _llm_fast is None:
            if not settings.groq_api_key:
                raise RuntimeError("GROQ_API_KEY is not set.")
            _llm_fast = ChatGroq(
                model=settings.groq_model,
                api_key=settings.groq_api_key,
                temperature=0.1,
                streaming=True,
                max_tokens=400,
            )
            print(f"Using Groq LLM (fast): {settings.groq_model} (max_tokens=400)")
        return _llm_fast
    
    # Use system default singleton if requested model matches system model
    if model_name == settings.groq_model:
        if _llm_fast is None:
            if not settings.groq_api_key:
                raise RuntimeError("GROQ_API_KEY is not set.")
            _llm_fast = ChatGroq(
                model=settings.groq_model,
                api_key=settings.groq_api_key,
                temperature=temperature or 0.1,
                streaming=True,
                max_tokens=400,
            )
            print(f"Using Groq LLM (fast): {settings.groq_model} (max_tokens=400)")
        return _llm_fast
    
    # Custom model: create fresh instance (not cached to avoid memory bloat per user)
    if not api_key:
        raise ValueError("api_key required for custom models")
    
    return ChatGroq(
        model=model_name,
        api_key=api_key,
        temperature=temperature or 0.1,
        streaming=True,
        max_tokens=400,
    )
