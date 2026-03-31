"""Vector store helpers and retrieval utilities."""

from __future__ import annotations

import json
import os
import shutil
from typing import Iterable, List

from langchain_community.vectorstores import Chroma

from config import get_settings
from core.pipelines import SYSTEM_PIPELINES
from dependencies import COLLECTION_FULLTEXT, PIPELINE_DB_PATHS, QA_CACHE, get_embeddings
from utils.text_utils import clean_text, docs_to_fulltext, normalize, split_documents

FULLTEXT_FILENAME = "_fulltext.json"

settings = get_settings()


def safe_delete_folder(path: str) -> None:
    if os.path.exists(path):
        shutil.rmtree(path, ignore_errors=True)


def build_vectordb_for_pipeline(documents, chunk_size: int, chunk_overlap: int, persist_dir: str):
    safe_delete_folder(persist_dir)
    chunks = split_documents(documents, chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    vectordb = Chroma.from_documents(
        documents=chunks,
        embedding=get_embeddings(),
        persist_directory=persist_dir,
    )
    return vectordb, chunks, persist_dir


def build_vectordb_with_embeddings(chunks, embeddings_list: list, persist_dir: str, fresh: bool = False):
    """
    Build (or extend) a Chroma vectorstore from pre-computed embeddings.
    When fresh=True (first upload for a collection) the folder is wiped first.
    For subsequent uploads to an existing collection, chunks are ADDED so that
    previous documents remain searchable via the Chroma fallback path.
    """
    if fresh:
        safe_delete_folder(persist_dir)
    texts = [chunk.page_content for chunk in chunks]
    metadatas = [chunk.metadata for chunk in chunks]
    vectordb = Chroma(
        embedding_function=get_embeddings(),
        persist_directory=persist_dir,
    )
    vectordb.add_texts(texts=texts, embeddings=embeddings_list, metadatas=metadatas)
    return vectordb, persist_dir


def dedupe_docs(docs: Iterable) -> List:
    seen = set()
    unique = []
    for doc in docs:
        key = normalize(doc.page_content[:400])
        if key not in seen:
            seen.add(key)
            unique.append(doc)
    return unique


def persist_fulltext(collection_id: str, fulltext: str) -> None:
    """Persist fulltext to disk so it survives restarts."""
    collection_folder = os.path.join(settings.collection_root, collection_id)
    os.makedirs(collection_folder, exist_ok=True)
    path = os.path.join(collection_folder, FULLTEXT_FILENAME)
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"fulltext": fulltext}, f, ensure_ascii=False)


def _load_fulltext(collection_id: str) -> str | None:
    """Load persisted fulltext from disk."""
    path = os.path.join(settings.collection_root, collection_id, FULLTEXT_FILENAME)
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("fulltext")
    except Exception:
        return None


def store_fulltext(collection_id: str, documents) -> None:
    new_text = docs_to_fulltext(documents)
    # Append to any existing fulltext so previous uploads aren't lost
    existing = COLLECTION_FULLTEXT.get(collection_id) or _load_fulltext(collection_id) or ""
    combined = (existing.rstrip() + "\n\n" + new_text).strip() if existing else new_text
    COLLECTION_FULLTEXT[collection_id] = combined
    persist_fulltext(collection_id, combined)


def ensure_collection_cache(collection_id: str) -> None:
    QA_CACHE.setdefault(collection_id, {})


def _folder_name_for_pipeline(pipeline_name: str) -> str:
    return f"chroma_{pipeline_name.replace(' ', '_').lower()}"


def load_existing_collections() -> None:
    """
    Populate PIPELINE_DB_PATHS on startup.

    Strategy:
    1. Try Supabase — query distinct (collection_id, pipeline_name) from rag_chunks.
       This works even without local disk folders.
    2. Fallback to disk scan (legacy ChromaDB) if Supabase unavailable.
    """
    root = settings.collection_root

    # ---- Supabase path ----
    try:
        from dependencies import get_supabase_admin
        admin = get_supabase_admin()
        if admin:
            res = admin.table("rag_chunks") \
                .select("collection_id,pipeline_name") \
                .execute()
            rows = res.data or []
            pairs: dict[str, set[str]] = {}
            for r in rows:
                cid = r.get("collection_id")
                pname = r.get("pipeline_name")
                if cid and pname:
                    pairs.setdefault(cid, set()).add(pname)

            for cid, pnames in pairs.items():
                db_paths = {}
                collection_folder = os.path.join(root, cid)
                for pname in pnames:
                    # Still store a local path for Chroma fallback compatibility
                    folder = _folder_name_for_pipeline(pname)
                    db_paths[pname] = os.path.join(collection_folder, folder)
                PIPELINE_DB_PATHS[cid] = db_paths
                ensure_collection_cache(cid)
                fulltext = _load_fulltext(cid)
                if fulltext:
                    COLLECTION_FULLTEXT[cid] = fulltext

            if pairs:
                print(f"  Loaded {len(pairs)} collections from Supabase rag_chunks")
                return
    except Exception as e:
        print(f"  [WARN] Supabase collection scan failed ({e}), falling back to disk")

    # ---- Disk fallback (legacy ChromaDB) ----
    if not os.path.exists(root):
        return

    expected_folders = {
        _folder_name_for_pipeline(p["name"]): p["name"]
        for p in SYSTEM_PIPELINES
    }

    for collection_id in os.listdir(root):
        folder_path = os.path.join(root, collection_id)
        if not os.path.isdir(folder_path):
            continue

        collection_db_paths = {}
        for folder in os.listdir(folder_path):
            if not folder.startswith("chroma_"):
                continue
            folder_full_path = os.path.join(folder_path, folder)
            if not os.path.isdir(folder_full_path):
                continue
            pipeline_name = expected_folders.get(folder)
            if pipeline_name:
                collection_db_paths[pipeline_name] = folder_full_path

        if collection_db_paths:
            PIPELINE_DB_PATHS[collection_id] = collection_db_paths
            ensure_collection_cache(collection_id)
            # Restore fulltext from disk
            fulltext = _load_fulltext(collection_id)
            if fulltext:
                COLLECTION_FULLTEXT[collection_id] = fulltext
