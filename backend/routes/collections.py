"""
Collection routes - endpoints for collection CRUD operations.
"""
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException

from dependencies import get_current_user, get_supabase_user_client
from models import ApplyPresetRequest, RenameRequest, PipelineConfigRequest, CustomPipelineConfig, ChunkRow, ChunkListResponse
from services import collection_service


router = APIRouter()


@router.get("/collections")
def list_collections(user=Depends(get_current_user)):
    """List all collections for the current user."""
    return collection_service.list_collections_for_user(user["sub"], user["access_token"])


@router.post("/collections/{collection_id}/rename")
def rename_collection(collection_id: str, data: RenameRequest, user=Depends(get_current_user)):
    """Rename a collection."""
    result = collection_service.rename_collection(
        collection_id, data.name, user["sub"], user["access_token"]
    )
    if "error" in result:
        raise HTTPException(status_code=result.get("status_code", 400), detail=result["error"])
    return result


@router.delete("/collections/{collection_id}")
def delete_collection(collection_id: str, user=Depends(get_current_user)):
    """Delete a collection and all associated data."""
    return collection_service.delete_collection(collection_id, user["sub"], user["access_token"])


@router.post("/collections/{collection_id}/rebuild-index")
async def rebuild_index(collection_id: str, user=Depends(get_current_user)):
    """Rebuild local vectorstore from Supabase files for an existing collection."""
    result = collection_service.rebuild_collection_index(
        collection_id, user["sub"], user["access_token"]
    )
    if "error" in result:
        raise HTTPException(status_code=result.get("status_code", 500), detail=result["error"])
    return result


@router.get("/collections/{collection_id}/pipeline-config")
def get_pipeline_config(collection_id: str, user=Depends(get_current_user)):
    """Get pipeline configuration for a collection."""
    result = collection_service.get_pipeline_config(
        collection_id, user["sub"], user["access_token"]
    )
    if "error" in result:
        raise HTTPException(status_code=result.get("status_code", 404), detail=result["error"])
    return result


@router.post("/collections/{collection_id}/pipeline-config")
def save_pipeline_config(
    collection_id: str,
    config: PipelineConfigRequest,
    user=Depends(get_current_user)
):
    """Save pipeline configuration for a collection."""
    config_dict = {
        "preset_name": config.preset_name,
        "chunk_size": config.chunk_size,
        "overlap": config.overlap,
        "top_k": config.top_k,
        "search_type": config.search_type,
    }
    return collection_service.save_pipeline_config(
        collection_id, config_dict, user["sub"], user["access_token"]
    )


@router.get("/collections/{collection_id}/custom-pipeline")
def get_custom_pipeline(collection_id: str, user=Depends(get_current_user)):
    """Get custom pipeline configuration for a collection."""
    result = collection_service.get_custom_pipeline(
        collection_id, user["sub"], user["access_token"]
    )
    if "error" in result:
        raise HTTPException(status_code=result.get("status_code", 404), detail=result["error"])
    return result


@router.post("/collections/{collection_id}/custom-pipeline")
def save_custom_pipeline(
    collection_id: str,
    config: CustomPipelineConfig,
    user=Depends(get_current_user)
):
    """Save custom pipeline configuration for a collection."""
    config_dict = {
        "enabled": config.enabled,
        "preset_name": config.preset_name,
        "chunk_size": config.chunk_size,
        "overlap": config.overlap,
        "top_k": config.top_k,
        "search_type": config.search_type,
    }
    return collection_service.save_custom_pipeline(
        collection_id, config_dict, user["sub"], user["access_token"]
    )


@router.get("/collections/{collection_id}/pipeline-presets")
def get_pipeline_presets(collection_id: str, user=Depends(get_current_user)):
    """Get available pipeline presets and current collection config."""
    result = collection_service.get_pipeline_presets(
        collection_id, user["sub"], user["access_token"]
    )
    if "error" in result:
        raise HTTPException(status_code=result.get("status_code", 404), detail=result["error"])
    return result


@router.post("/collections/{collection_id}/apply-preset")
def apply_pipeline_preset(
    collection_id: str,
    data: ApplyPresetRequest,
    user=Depends(get_current_user)
):
    """Apply preset key (fast|balanced|accurate|deepsearch) to collection."""
    result = collection_service.apply_pipeline_preset(
        collection_id, data.preset_key, user["sub"], user["access_token"]
    )
    if "error" in result:
        raise HTTPException(status_code=result.get("status_code", 400), detail=result["error"])
    return result


@router.get("/collections/{collection_id}/files")
def list_collection_files(collection_id: str, user=Depends(get_current_user)):
    """List all files in a collection."""
    return collection_service.list_collection_files(
        collection_id, user["sub"], user["access_token"]
    )


@router.get("/collections/{collection_id}/files/{file_id}/signed-url")
def get_signed_pdf_url(collection_id: str, file_id: str, user=Depends(get_current_user)):
    """Get a signed URL for a PDF file."""
    result = collection_service.get_signed_pdf_url(
        collection_id, file_id, user["sub"], user["access_token"]
    )
    if "error" in result:
        raise HTTPException(status_code=result.get("status_code", 500), detail=result["error"])
    return result


@router.get("/collections/{collection_id}/history")
def get_collection_history(collection_id: str, user=Depends(get_current_user)):
    """Get chat history for a collection."""
    return collection_service.get_collection_history(
        collection_id, user["sub"], user["access_token"]
    )


@router.delete("/collections/{collection_id}/history")
def clear_collection_history(collection_id: str, user=Depends(get_current_user)):
    """Clear chat history for a collection."""
    return collection_service.clear_collection_history(
        collection_id, user["sub"], user["access_token"]
    )


@router.get("/collections/{collection_id}/chunks")
def get_chunks(
    collection_id: str,
    q: Optional[str] = None,
    file_id: Optional[str] = None,
    page: Optional[int] = None,
    pipeline: Optional[str] = None,
    limit: int = 20,
    offset: int = 0,
    user=Depends(get_current_user)
):
    """Fetch chunks for a collection with pagination and filtering."""
    result = collection_service.get_chunks(
        collection_id=collection_id,
        user_id=user["sub"],
        access_token=user["access_token"],
        q=q,
        file_id=file_id,
        page=page,
        pipeline=pipeline,
        limit=limit,
        offset=offset
    )
    
    if "error" in result:
        raise HTTPException(status_code=result.get("status_code", 404), detail=result["error"])
    
    # Format response with ChunkRow models
    chunk_rows = []
    file_map = result.get("file_map", {})
    for c in result.get("chunks", []):
        chunk_rows.append(ChunkRow(
            id=c.get("id"),
            file_id=c.get("file_id"),
            filename=file_map.get(c.get("file_id")),
            pipeline_name=c.get("pipeline_name"),
            chunk_size=c.get("chunk_size"),
            overlap=c.get("overlap"),
            chunk_index=c.get("chunk_index"),
            page_number=c.get("page_number"),
            chunk_text=c.get("chunk_text", ""),
            created_at=c.get("created_at")
        ))
    
    return ChunkListResponse(
        collection_id=collection_id,
        total=result.get("total", 0),
        limit=result.get("limit", 20),
        offset=result.get("offset", 0),
        chunks=chunk_rows
    )


@router.get("/collections/{collection_id}/ask-history")
def get_ask_history(
    collection_id: str,
    limit: int = 30,
    user=Depends(get_current_user),
):
    """Fetch past fast/compare Q&A history for a collection."""
    sb = get_supabase_user_client(user["access_token"])
    res = (
        sb.table("rag_chat_history")
        .select("id,question,answer,best_pipeline,mode,created_at,retrieval_comparison,metrics")
        .eq("collection_id", collection_id)
        .eq("user_id", user["sub"])
        .order("created_at", desc=False)
        .limit(limit)
        .execute()
    )
    return {"history": res.data or []}
