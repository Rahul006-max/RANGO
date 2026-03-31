"""
PageIndex routes — endpoints for inspecting tree-indexed collections.
"""

from fastapi import APIRouter, Depends, HTTPException

from dependencies import get_current_user, get_supabase_user_client
from services import page_index_service

router = APIRouter()


@router.get("/page-index/tree/{collection_id}")
def get_page_index_tree(collection_id: str, user=Depends(get_current_user)):
    """Return the raw PageIndex tree JSON for a collection."""
    sb = get_supabase_user_client(user["access_token"])

    # Verify collection ownership
    col = (
        sb.table("rag_collections")
        .select("id")
        .eq("id", collection_id)
        .eq("user_id", user["sub"])
        .maybe_single()
        .execute()
    )
    if not col.data:
        raise HTTPException(status_code=404, detail="Collection not found")

    tree = page_index_service.load_tree(collection_id, sb)
    if not tree:
        raise HTTPException(status_code=404, detail="No PageIndex tree found for this collection")

    return {"collection_id": collection_id, "tree": tree}
