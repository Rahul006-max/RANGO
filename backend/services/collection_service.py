"""
Collection service - handles collection CRUD operations, rebuilding, and pipeline configurations.
"""
import os
import time
import traceback
import uuid
from typing import Optional
from langchain_community.document_loaders import PyPDFLoader
from langchain_community.vectorstores import Chroma

from config import get_settings, STORAGE_BUCKET
from dependencies import (
    get_supabase_user_client,
    get_supabase_admin,
    PIPELINE_DB_PATHS,
    QA_CACHE,
    COLLECTION_FULLTEXT,
    get_embeddings,
    invalidate_vectorstore_cache,
)
from core.pipelines import SYSTEM_PIPELINES, PIPELINE_PRESETS, get_pipeline_preset, normalize_search_type
from core.retrieval import build_vectordb_for_pipeline, store_fulltext
from utils.text_utils import docs_to_fulltext


def safe_delete_folder(folder_path: str):
    """Safely delete a folder and its contents."""
    import shutil
    if os.path.exists(folder_path):
        try:
            shutil.rmtree(folder_path)
        except Exception as e:
            print(f"[WARN] Failed to delete {folder_path}: {e}")


def list_collections_for_user(user_id: str, access_token: str):
    """List all collections for a user."""
    sb = get_supabase_user_client(access_token)
    res = sb.table("rag_collections") \
        .select("id,name,created_at,index_type") \
        .eq("user_id", user_id) \
        .order("created_at", desc=True) \
        .execute()
    
    return {"collections": res.data or []}


def rename_collection(collection_id: str, new_name: str, user_id: str, access_token: str):
    """Rename a collection."""
    new_name = (new_name or "").strip()
    if not new_name:
        return {"error": "Name cannot be empty.", "status_code": 400}
    
    sb = get_supabase_user_client(access_token)
    sb.table("rag_collections").update({"name": new_name}) \
        .eq("id", collection_id).eq("user_id", user_id).execute()
    
    return {"status": "renamed [OK]", "collection_id": collection_id, "new_name": new_name}


def delete_collection(collection_id: str, user_id: str, access_token: str):
    """Delete a collection and all associated data."""
    sb = get_supabase_user_client(access_token)
    supabase_admin = get_supabase_admin()
    
    # Fetch storage paths before deleting DB rows
    storage_paths_to_delete = []
    try:
        files_res = sb.table("rag_files").select("storage_path").eq("collection_id", collection_id).eq("user_id", user_id).execute()
        if files_res.data:
            storage_paths_to_delete = [f["storage_path"] for f in files_res.data if f.get("storage_path")]
    except Exception as e:
        print(f"[WARN] Could not fetch file paths for cleanup: {e}")
    
    folder_path = os.path.join("collections", collection_id)
    safe_delete_folder(folder_path)
    
    # Clear from memory
    PIPELINE_DB_PATHS.pop(collection_id, None)
    QA_CACHE.pop(collection_id, None)
    COLLECTION_FULLTEXT.pop(collection_id, None)
    invalidate_vectorstore_cache(collection_id)
    
    # Delete from database — each step isolated so a missing table won't crash the whole delete
    for _table, _col in [
        ("rag_chat_history", "collection_id"),
        ("rag_compare_results", "collection_id"),
        ("rag_pipeline_builds", "collection_id"),
        ("rag_files", "collection_id"),
        ("rag_chat_messages", "collection_id"),
    ]:
        try:
            sb.table(_table).delete().eq(_col, collection_id).eq("user_id", user_id).execute()
        except Exception as e:
            print(f"[WARN] Could not delete from {_table}: {e}")

    # rag_chunks — use admin client to bypass RLS
    try:
        if supabase_admin:
            supabase_admin.table("rag_chunks").delete().eq("collection_id", collection_id).execute()
        else:
            sb.table("rag_chunks").delete().eq("collection_id", collection_id).eq("user_id", user_id).execute()
    except Exception as e:
        print(f"[WARN] Could not delete rag_chunks: {e}")

    # Delete the collection row itself — this is the critical step
    try:
        sb.table("rag_collections").delete().eq("id", collection_id).eq("user_id", user_id).execute()
    except Exception as e:
        print(f"[WARN] Could not delete rag_collections row: {e}")
        raise  # re-raise so the frontend receives a 500 and shows an error toast

    # Delete files from Supabase storage
    if storage_paths_to_delete and supabase_admin:
        try:
            supabase_admin.storage.from_(STORAGE_BUCKET).remove(storage_paths_to_delete)
            print(f"[OK] Deleted {len(storage_paths_to_delete)} files from Supabase storage")
        except Exception as e:
            print(f"[WARN] Failed to delete storage files: {e}")
    
    return {"status": "deleted [OK]", "collection_id": collection_id}


def rebuild_collection_index(collection_id: str, user_id: str, access_token: str):
    """Rebuild local vectorstore from Supabase files for an existing collection."""
    start = time.time()
    supabase_admin = get_supabase_admin()
    embeddings = get_embeddings()
    invalidate_vectorstore_cache(collection_id)
    
    if not supabase_admin:
        return {"error": "SERVICE ROLE KEY missing", "status_code": 500}
    
    sb = get_supabase_user_client(access_token)
    
    # Verify ownership
    try:
        collection_res = sb.table("rag_collections").select("id,name").eq("id", collection_id).eq("user_id", user_id).single().execute()
        if not collection_res.data:
            return {"error": "Invalid collection_id. Collection not found or access denied.", "status_code": 400}
    except Exception as e:
        return {"error": f"Collection validation failed: {str(e)}", "status_code": 400}
    
    # Get all files for this collection
    try:
        files_res = sb.table("rag_files").select("id,filename,storage_path").eq("collection_id", collection_id).eq("user_id", user_id).execute()
        
        if not files_res.data:
            return {"error": "No files found in this collection. Upload PDFs first.", "status_code": 400}
    except Exception as e:
        return {"error": f"Failed to fetch files: {str(e)}", "status_code": 500}
    
    # Download and process PDFs
    os.makedirs("uploads", exist_ok=True)
    os.makedirs("collections", exist_ok=True)
    
    all_documents = []
    failed_files = []
    temp_paths = []
    
    for file_row in files_res.data:
        try:
            # Download from Supabase storage
            file_data = supabase_admin.storage.from_(STORAGE_BUCKET).download(file_row["storage_path"])
            
            # Save temporarily
            temp_path = os.path.join("uploads", f"{collection_id}_{file_row['filename']}")
            with open(temp_path, "wb") as f:
                f.write(file_data)
            temp_paths.append(temp_path)
            
            # Load PDF
            loader = PyPDFLoader(temp_path)
            docs = loader.load()
            all_documents.extend(docs)
        except Exception as e:
            print(f"[WARN] Error loading {file_row['filename']}: {e}")
            failed_files.append(file_row['filename'])
            continue
    
    if not all_documents:
        if failed_files:
            return {"error": f"Failed to load all documents. Failed files: {', '.join(failed_files)}", "status_code": 500}
        else:
            return {"error": "No documents could be loaded from storage", "status_code": 400}
    
    # Store fulltext (persisted to disk)
    store_fulltext(collection_id, all_documents)
    
    # Build all 4 system pipelines with normalized search types
    collection_folder = os.path.join("collections", collection_id)
    os.makedirs(collection_folder, exist_ok=True)
    
    collection_db_paths = {}
    total_chunks = 0
    
    for p in SYSTEM_PIPELINES:
        try:
            db_path = os.path.join(collection_folder, f"chroma_{p['name'].replace(' ', '_').lower()}")
            
            _, chunks, final_path = build_vectordb_for_pipeline(
                all_documents,
                chunk_size=p["chunk_size"],
                chunk_overlap=p["overlap"],
                persist_dir=db_path
            )
            
            collection_db_paths[p["name"]] = final_path
            total_chunks += len(chunks)
            
            # Update pipeline builds table with normalized search_type
            sb.table("rag_pipeline_builds").upsert({
                "user_id": user_id,
                "collection_id": collection_id,
                "pipeline_name": p["name"],
                "chunk_size": p["chunk_size"],
                "overlap": p["overlap"],
                "search_type": normalize_search_type(p["search_type"]),
                "top_k": p["k"],
                "chunks_created": len(chunks),
                "build_time_sec": 0,
            }, on_conflict="user_id,collection_id,pipeline_name").execute()

            # Populate rag_chunks table (with embeddings for pgvector search)
            embeddings_model = get_embeddings()
            chunk_texts = [chunk.page_content[:4000] for chunk in chunks]
            chunk_embeddings = embeddings_model.embed_documents(chunk_texts)
            
            chunk_rows = []
            for idx, chunk in enumerate(chunks):
                chunk_rows.append({
                    "user_id": user_id,
                    "collection_id": collection_id,
                    "pipeline_name": p["name"],
                    "chunk_text": chunk_texts[idx],
                    "page_number": chunk.metadata.get("page"),
                    "chunk_index": idx,
                    "embedding": chunk_embeddings[idx],
                })
            if chunk_rows:
                # Delete old chunks for this pipeline before inserting new ones
                sb.table("rag_chunks").delete().eq("collection_id", collection_id).eq("pipeline_name", p["name"]).execute()
                for i in range(0, len(chunk_rows), 200):
                    sb.table("rag_chunks").insert(chunk_rows[i:i+200]).execute()
        except Exception as e:
            print(f"[WARN] Error building pipeline {p['name']}: {e}")
            continue
    
    if not collection_db_paths:
        return {"error": "Failed to build any pipelines. Check server logs.", "status_code": 500}
    
    PIPELINE_DB_PATHS[collection_id] = collection_db_paths
    QA_CACHE.setdefault(collection_id, {})
    
    # Clean up temp files
    for tmp in temp_paths:
        try:
            if os.path.exists(tmp):
                os.remove(tmp)
        except OSError:
            pass
    
    elapsed = round(time.time() - start, 2)
    
    return {
        "ok": True,
        "collection_id": collection_id,
        "message": "Index rebuilt successfully",
        "chunks_created": total_chunks,
        "chunks_deleted": 0,
        "time_taken_sec": elapsed,
        "pipelines_rebuilt": len(collection_db_paths),
        "failed_files": failed_files if failed_files else []
    }


def get_pipeline_config(collection_id: str, user_id: str, access_token: str):
    """Get pipeline configuration for a collection."""
    sb = get_supabase_user_client(access_token)
    
    res = sb.table("rag_collections") \
        .select("pipeline_config") \
        .eq("id", collection_id) \
        .eq("user_id", user_id) \
        .single() \
        .execute()
    
    if not res.data:
        return {"error": "Collection not found", "status_code": 404}
    
    return {
        "collection_id": collection_id,
        "pipeline_config": res.data.get("pipeline_config")
    }


def save_pipeline_config(collection_id: str, config_dict: dict, user_id: str, access_token: str):
    """Save pipeline configuration for a collection."""
    sb = get_supabase_user_client(access_token)
    
    sb.table("rag_collections").update({"pipeline_config": config_dict}) \
        .eq("id", collection_id) \
        .eq("user_id", user_id) \
        .execute()
    
    return {
        "ok": True,
        "collection_id": collection_id,
        "pipeline_config": config_dict
    }


def get_custom_pipeline(collection_id: str, user_id: str, access_token: str):
    """Get custom pipeline configuration for a collection."""
    sb = get_supabase_user_client(access_token)
    
    res = sb.table("rag_collections") \
        .select("custom_pipeline_config") \
        .eq("id", collection_id) \
        .eq("user_id", user_id) \
        .single() \
        .execute()
    
    if not res.data:
        return {"error": "Collection not found", "status_code": 404}
    
    return {
        "collection_id": collection_id,
        "custom_pipeline": res.data.get("custom_pipeline_config")
    }


def save_custom_pipeline(collection_id: str, config_dict: dict, user_id: str, access_token: str):
    """Save custom pipeline configuration for a collection."""
    sb = get_supabase_user_client(access_token)
    
    sb.table("rag_collections").update({"custom_pipeline_config": config_dict}) \
        .eq("id", collection_id) \
        .eq("user_id", user_id) \
        .execute()
    
    return {
        "ok": True,
        "collection_id": collection_id,
        "custom_pipeline": config_dict
    }


def get_pipeline_presets(collection_id: str, user_id: str, access_token: str):
    """Return available pipeline presets and the currently applied config."""
    sb = get_supabase_user_client(access_token)
    res = (
        sb.table("rag_collections")
        .select("id,pipeline_config")
        .eq("id", collection_id)
        .eq("user_id", user_id)
        .maybe_single()
        .execute()
    )
    if not res.data:
        return {"error": "Collection not found", "status_code": 404}

    return {
        "collection_id": collection_id,
        "current_pipeline_config": res.data.get("pipeline_config"),
        "presets": PIPELINE_PRESETS,
    }


def apply_pipeline_preset(
    collection_id: str,
    preset_key: str,
    user_id: str,
    access_token: str,
):
    """Apply one of the canonical presets to the collection pipeline config."""
    preset = get_pipeline_preset(preset_key)
    if not preset:
        return {
            "error": "Invalid preset key. Use one of: fast, balanced, accurate, deepsearch",
            "status_code": 400,
        }

    sb = get_supabase_user_client(access_token)
    update_res = (
        sb.table("rag_collections")
        .update({"pipeline_config": preset})
        .eq("id", collection_id)
        .eq("user_id", user_id)
        .execute()
    )
    if not update_res.data:
        return {"error": "Collection not found", "status_code": 404}

    return {
        "ok": True,
        "collection_id": collection_id,
        "preset_key": preset_key,
        "pipeline_config": preset,
    }


def list_collection_files(collection_id: str, user_id: str, access_token: str):
    """List all files in a collection."""
    sb = get_supabase_user_client(access_token)
    
    res = sb.table("rag_files") \
        .select("id,filename,storage_path,created_at") \
        .eq("collection_id", collection_id) \
        .eq("user_id", user_id) \
        .order("created_at", desc=True) \
        .execute()
    
    return {"files": res.data or []}


def get_signed_pdf_url(collection_id: str, file_id: str, user_id: str, access_token: str):
    """Get a signed URL for a PDF file."""
    supabase_admin = get_supabase_admin()
    
    if not supabase_admin:
        return {"error": "SERVICE ROLE KEY missing", "status_code": 500}
    
    sb = get_supabase_user_client(access_token)
    
    res = sb.table("rag_files") \
        .select("id,storage_path,filename") \
        .eq("id", file_id) \
        .eq("collection_id", collection_id) \
        .eq("user_id", user_id) \
        .limit(1) \
        .execute()
    
    if not res.data:
        return {"error": "File not found", "status_code": 404}
    
    storage_path = res.data[0]["storage_path"]
    
    signed = supabase_admin.storage.from_(STORAGE_BUCKET).create_signed_url(storage_path, 600)
    
    return {
        "filename": res.data[0]["filename"],
        "signed_url": signed.get("signedURL") or signed.get("signedUrl") or signed.get("signed_url")
    }


def get_collection_history(collection_id: str, user_id: str, access_token: str):
    """Get chat history for a collection."""
    sb = get_supabase_user_client(access_token)
    
    res = sb.table("rag_chat_history") \
        .select("question,answer,mode,best_pipeline,created_at,citations") \
        .eq("collection_id", collection_id) \
        .eq("user_id", user_id) \
        .order("created_at", desc=True) \
        .limit(50) \
        .execute()
    
    return {"collection_id": collection_id, "history": res.data or []}


def clear_collection_history(collection_id: str, user_id: str, access_token: str):
    """Clear chat history for a collection."""
    sb = get_supabase_user_client(access_token)
    
    sb.table("rag_chat_history").delete() \
        .eq("collection_id", collection_id) \
        .eq("user_id", user_id) \
        .execute()
    
    return {"status": "cleared [OK]", "collection_id": collection_id}


def get_chunks(
    collection_id: str,
    user_id: str,
    access_token: str,
    q: Optional[str] = None,
    file_id: Optional[str] = None,
    page: Optional[int] = None,
    pipeline: Optional[str] = None,
    limit: int = 20,
    offset: int = 0
):
    """Fetch chunks for a collection with pagination and filtering."""
    sb = get_supabase_user_client(access_token)
    
    # Verify ownership
    collection_res = sb.table("rag_collections").select("id").eq("id", collection_id).eq("user_id", user_id).maybe_single().execute()
    if not collection_res.data:
        return {"error": "Collection not found", "status_code": 404}
    
    # Build query
    query = sb.table("rag_chunks").select("*", count="exact").eq("collection_id", collection_id)
    
    if pipeline:
        query = query.ilike("pipeline_name", f"%{pipeline}%")
    if file_id:
        query = query.eq("file_id", file_id)
    if page is not None:
        query = query.eq("page_number", page)
    if q:
        query = query.ilike("chunk_text", f"%{q}%")
    
    # Execute with pagination
    query = query.order("created_at", desc=True).range(offset, offset + limit - 1)
    result = query.execute()
    
    chunks = result.data or []
    total = result.count or 0
    
    # Fetch file names for chunks
    file_ids = list(set([c.get("file_id") for c in chunks if c.get("file_id")]))
    file_map = {}
    
    if file_ids:
        files_res = sb.table("rag_files").select("id,filename").in_("id", file_ids).execute()
        file_map = {f["id"]: f["filename"] for f in (files_res.data or [])}
    
    return {
        "collection_id": collection_id,
        "total": total,
        "limit": limit,
        "offset": offset,
        "chunks": chunks,
        "file_map": file_map
    }
