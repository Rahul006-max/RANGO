"""
Upload service - handles PDF/image upload and vectorstore building.
Optimised: all 4 pipelines are built in parallel via a thread-pool so total
upload time is ≈ the slowest single pipeline instead of the sum of all four.
"""
import os
import time
import uuid
import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import List, Optional
from langchain_community.document_loaders import PyPDFLoader
from langchain_core.documents import Document

from config import get_settings, STORAGE_BUCKET
from dependencies import (
    get_supabase_user_client,
    get_supabase_admin,
    PIPELINE_DB_PATHS,
    QA_CACHE,
    BUILD_STATS_CACHE,
    COLLECTION_FULLTEXT,
    get_embeddings,
)
from core.pipelines import SYSTEM_PIPELINES
from core.retrieval import build_vectordb_with_embeddings, store_fulltext
from core.llm import describe_image_with_groq
from utils.text_utils import docs_to_fulltext, split_documents

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"}
_MIME_MAP = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png",
            "webp": "image/webp", "gif": "image/gif", "bmp": "image/bmp"}


def _ext_mime(ext: str) -> str:
    return _MIME_MAP.get(ext.lstrip(".").lower(), "image/jpeg")


def _extract_pdf_image_docs(file_path: str, filename: str) -> list:
    """
    Extract embedded images from a PDF and describe via Groq Vision.
    Only called when extract_images=True is passed to upload_multiple_pdfs.
    This is intentionally skipped by default because each Vision API call
    adds 2-4 seconds per image, making uploads very slow for image-heavy PDFs.
    """
    try:
        import fitz  # pymupdf
    except ImportError:
        return []

    image_docs = []
    try:
        doc = fitz.open(file_path)
        for page_num, page in enumerate(doc):
            for img_idx, img in enumerate(page.get_images(full=True)):
                xref = img[0]
                try:
                    base_image = doc.extract_image(xref)
                    image_bytes = base_image["image"]
                    if len(image_bytes) < 5_000:  # skip tiny icons/decorations
                        continue
                    ext = base_image.get("ext", "png")
                    description = describe_image_with_groq(image_bytes, _ext_mime(ext))
                    if description:
                        image_docs.append(Document(
                            page_content=f"[Image on page {page_num + 1}]: {description}",
                            metadata={"source": filename, "page": page_num,
                                      "type": "image", "img_index": img_idx},
                        ))
                except Exception as e:
                    print(f"[WARN] Image extract failed (page {page_num}, img {img_idx}): {e}")
    except Exception as e:
        print(f"[WARN] PDF image extraction failed for {filename}: {e}")
    return image_docs


def _build_pipeline_sync(
    p: dict,
    all_documents: list,
    collection_folder: str,
    cid: str,
    user_id: str,
    file_id_map: dict,
    supabase_admin,
    sb,
    is_new_collection: bool,
) -> dict:
    """
    Build one pipeline completely (split → embed → Chroma → Supabase).
    Designed to run inside a ThreadPoolExecutor worker.
    Returns a stats dict.
    """
    from utils.text_utils import split_documents
    from core.retrieval import build_vectordb_with_embeddings
    from dependencies import get_embeddings

    pipeline_start = time.time()

    db_path = os.path.join(collection_folder, f"chroma_{p['name'].replace(' ', '_').lower()}")

    # 1. Split documents into chunks for this pipeline
    chunks = split_documents(all_documents, chunk_size=p["chunk_size"], chunk_overlap=p["overlap"])
    chunk_texts = [chunk.page_content[:4000] for chunk in chunks]

    # 2. Embed all chunks in one batch
    embeddings_model = get_embeddings()
    chunk_embeddings = embeddings_model.embed_documents([c.page_content for c in chunks])

    # 3. Build/extend Chroma store
    _, final_path = build_vectordb_with_embeddings(chunks, chunk_embeddings, db_path, fresh=is_new_collection)

    build_time_sec = round(time.time() - pipeline_start, 3)

    # 4. Record pipeline build metadata in Supabase
    try:
        sb.table("rag_pipeline_builds").insert({
            "user_id": user_id,
            "collection_id": cid,
            "pipeline_name": p["name"],
            "chunk_size": p["chunk_size"],
            "overlap": p["overlap"],
            "search_type": p["search_type"],
            "top_k": p["k"],
            "chunks_created": len(chunks),
            "build_time_sec": build_time_sec,
        }).execute()
    except Exception as e:
        print(f"[WARN] rag_pipeline_builds insert failed ({p['name']}): {e}")

    # 5. Insert chunk rows in larger batches (500 instead of 200)
    chunk_rows = []
    for idx, chunk in enumerate(chunks):
        source_path = chunk.metadata.get("source", "")
        matched_file_id = file_id_map.get(source_path) or file_id_map.get(os.path.abspath(source_path))
        if not matched_file_id and file_id_map:
            matched_file_id = next(iter(file_id_map.values()))
        chunk_rows.append({
            "user_id": user_id,
            "collection_id": cid,
            "pipeline_name": p["name"],
            "chunk_size": p["chunk_size"],
            "overlap": p["overlap"],
            "chunk_text": chunk_texts[idx],
            "embedding": chunk_embeddings[idx],
            "page_number": chunk.metadata.get("page"),
            "chunk_index": idx,
            "file_id": matched_file_id,
        })

    for i in range(0, len(chunk_rows), 500):
        try:
            supabase_admin.table("rag_chunks").insert(chunk_rows[i:i + 500]).execute()
        except Exception as e:
            print(f"[WARN] rag_chunks insert batch {i} failed ({p['name']}): {e}")

    return {
        "pipeline_name": p["name"],
        "final_path": final_path,
        "stats": {
            "chunks_created": len(chunks),
            "chunk_size": p["chunk_size"],
            "overlap": p["overlap"],
            "search_type": p["search_type"],
            "top_k": p["k"],
            "build_time_sec": build_time_sec,
        },
    }


async def upload_multiple_pdfs(
    files: List,  # List[UploadFile]
    user_id: str,
    access_token: str,
    collection_id: Optional[str] = None,
    pipeline_config: Optional[str] = None,
    extract_images: bool = False,  # disabled by default — each Vision call adds 2-4s per image
    index_type: str = "vector",  # "vector" or "tree"
):
    """
    Upload multiple PDFs, store in Supabase, and build vectorstores for all system pipelines.
    
    Args:
        files: List of UploadFile objects
        user_id: User ID from JWT
        access_token: User's access token
        collection_id: Optional existing collection ID
        pipeline_config: Optional pipeline configuration (unused for now)
    
    Returns:
        dict with status, collection_id, files_uploaded, pages_loaded, pipelines_built, total_time_taken_sec
    """
    supabase_admin = get_supabase_admin()
    
    if not supabase_admin:
        return {"error": "SERVICE ROLE KEY missing in backend .env", "status_code": 500}
    
    sb = get_supabase_user_client(access_token)
    
    start = time.time()
    os.makedirs("uploads", exist_ok=True)
    os.makedirs("collections", exist_ok=True)
    
    # Create or use existing collection
    if collection_id:
        cid = collection_id
    else:
        cid = str(uuid.uuid4())
        # Extract name from first file (without extension)
        first_filename = files[0].filename if files else "Untitled"
        collection_name = os.path.splitext(first_filename)[0]
        
        # If multiple files, add count indicator
        if len(files) > 1:
            collection_name = f"{collection_name} (+{len(files)-1} more)"
        
        sb.table("rag_collections").insert({
            "id": cid,
            "user_id": user_id,
            "name": collection_name,
            "index_type": index_type,
        }).execute()
    
    collection_folder = os.path.join("collections", cid)
    os.makedirs(collection_folder, exist_ok=True)
    
    all_documents = []
    uploaded_file_names = []
    temp_files = []
    file_id_map = {}  # temp_file_path -> rag_files.id
    images_described = 0

    # Process each file (PDF or image)
    for f in files:
        ext = os.path.splitext(f.filename)[1].lower()

        # Save locally
        file_path = os.path.join("uploads", f"{cid}_{f.filename}")
        content = await f.read()
        with open(file_path, "wb") as out:
            out.write(content)
        temp_files.append(file_path)

        if ext in IMAGE_EXTENSIONS:
            # ---- Standalone image file ----
            mime = _ext_mime(ext)
            description = describe_image_with_groq(content, mime)
            if description:
                images_described += 1
            docs = [Document(
                page_content=f"[Image document: {f.filename}]\n{description}",
                metadata={"source": file_path, "page": 0, "type": "image"},
            )] if description else []
        else:
            # ---- PDF file ----
            loader = PyPDFLoader(file_path)
            docs = loader.load()
            # Only describe embedded images when explicitly requested
            # (each Groq Vision call takes 2-4 s — skipping saves the bulk of upload time)
            if extract_images:
                image_docs = _extract_pdf_image_docs(file_path, f.filename)
                if image_docs:
                    docs.extend(image_docs)
                    images_described += len(image_docs)
                    print(f"[OK] Extracted {len(image_docs)} image(s) from {f.filename}")

        all_documents.extend(docs)
        
        # Upload to Supabase storage
        ext = os.path.splitext(f.filename)[1].lower()
        storage_path = f"{user_id}/{cid}/{str(uuid.uuid4())}_{f.filename}"
        content_type = "application/pdf" if ext == ".pdf" else _ext_mime(ext)

        with open(file_path, "rb") as fp:
            supabase_admin.storage.from_(STORAGE_BUCKET).upload(
                storage_path,
                fp,
                {"content-type": content_type}
            )
        
        # Record in database
        insert_result = sb.table("rag_files").insert({
            "user_id": user_id,
            "collection_id": cid,
            "filename": f.filename,
            "storage_path": storage_path
        }).execute()
        if insert_result.data:
            # Store by both relative and absolute path so chunk source matching works
            file_id_map[file_path] = insert_result.data[0]["id"]
            file_id_map[os.path.abspath(file_path)] = insert_result.data[0]["id"]
        
        uploaded_file_names.append(f.filename)
    
    # Store fulltext for smart extraction (persisted to disk)
    store_fulltext(cid, all_documents)

    pipeline_stats = {}

    if index_type == "tree":
        # ------------------------------------------------------------------ #
        # TREE INDEX: build a hierarchical PageIndex tree (no embeddings)     #
        # ------------------------------------------------------------------ #
        from services.page_index_service import build_and_store_tree

        tree_stats = build_and_store_tree(
            collection_id=cid,
            documents=all_documents,
            supabase_admin=supabase_admin,
            user_id=user_id,
            file_id_map=file_id_map,
        )
        pipeline_stats["PageIndex Tree"] = tree_stats
    else:
        # ------------------------------------------------------------------ #
        # VECTOR INDEX: Build ALL system pipelines IN PARALLEL.               #
        # Each worker: split → embed → Chroma → Supabase insert              #
        # This cuts total time from (sum of all pipelines) to (slowest one).  #
        # ------------------------------------------------------------------ #
        is_new_collection = collection_id is None
        collection_db_paths = {}

        loop = asyncio.get_event_loop()
        with ThreadPoolExecutor(max_workers=4) as pool:
            futures = {
                loop.run_in_executor(
                    pool,
                    _build_pipeline_sync,
                    p,
                    all_documents,
                    collection_folder,
                    cid,
                    user_id,
                    file_id_map,
                    supabase_admin,
                    sb,
                    is_new_collection,
                ): p["name"]
                for p in SYSTEM_PIPELINES
            }
            results = await asyncio.gather(*futures.keys(), return_exceptions=True)

        for result in results:
            if isinstance(result, Exception):
                print(f"[WARN] Pipeline build failed: {result}")
                continue
            collection_db_paths[result["pipeline_name"]] = result["final_path"]
            pipeline_stats[result["pipeline_name"]] = result["stats"]

        # Store in memory
        PIPELINE_DB_PATHS[cid] = collection_db_paths

    # Always clear the QA cache for this collection so stale "I don't know"
    # answers aren't served after new documents have been added.
    QA_CACHE[cid] = {}
    # Clear cached build stats so the next request fetches fresh chunk counts.
    BUILD_STATS_CACHE.pop(cid, None)
    
    # Clean up temp files
    for tmp in temp_files:
        try:
            if os.path.exists(tmp):
                os.remove(tmp)
        except OSError:
            pass
    
    elapsed = round(time.time() - start, 2)
    
    return {
        "status": "success",
        "collection_id": cid,
        "index_type": index_type,
        "files_uploaded": uploaded_file_names,
        "pages_loaded": len(all_documents),
        "images_described": images_described,
        "pipelines_built": pipeline_stats,
        "total_time_taken_sec": elapsed,
    }
