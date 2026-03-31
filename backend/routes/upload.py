"""
Upload routes - endpoints for PDF upload.
"""
from typing import List, Optional
from fastapi import APIRouter, Depends, File, Form, UploadFile, HTTPException

from dependencies import get_current_user
from services import upload_service


router = APIRouter()


@router.post("/upload-multi")
async def upload_multiple_pdfs(
    files: List[UploadFile] = File(...),
    collection_id: Optional[str] = Form(None),
    pipeline_config: Optional[str] = Form(None),
    index_type: Optional[str] = Form("vector"),
    user=Depends(get_current_user),
):
    """Upload multiple PDFs and build vectorstores."""
    try:
        result = await upload_service.upload_multiple_pdfs(
            files=files,
            user_id=user["sub"],
            access_token=user["access_token"],
            collection_id=collection_id,
            pipeline_config=pipeline_config,
            index_type=index_type or "vector",
        )

        if "error" in result:
            raise HTTPException(status_code=result.get("status_code", 500), detail=result["error"])

        return result
    except HTTPException:
        raise
    except Exception as exc:
        # Catch-all so FastAPI always returns a proper JSON 500 with CORS headers
        print(f"[ERROR] /upload-multi unhandled exception: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))
