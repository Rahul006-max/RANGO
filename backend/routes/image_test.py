"""
Image test routes - endpoints for vision-based RAG testing.
"""
import asyncio
from typing import Optional
from fastapi import APIRouter, Depends, File, Form, UploadFile, HTTPException

from dependencies import get_current_user
from services.image_test_service import process_image_test, SUPPORTED_IMAGE_TYPES


router = APIRouter()

MAX_IMAGE_SIZE_BYTES = 20 * 1024 * 1024  # 20 MB


@router.post("/image-test")
async def image_test(
    image: UploadFile = File(...),
    question: str = Form(...),
    collection_id: Optional[str] = Form(None),
    user=Depends(get_current_user),
):
    """
    Test RAG vision accuracy by uploading an image and asking a question.

    Response keys (stable contract):
        ok, image_signed_url, question, extracted_description,
        final_answer, confidence_score, metrics, failure_type
    """
    # Input validation
    if not question or not question.strip():
        raise HTTPException(status_code=400, detail="Question is required")
    if not image:
        raise HTTPException(status_code=400, detail="Image is required")
    if image.content_type and image.content_type not in SUPPORTED_IMAGE_TYPES:
        raise HTTPException(status_code=400, detail=f"Unsupported image type: {image.content_type}")

    # Read image bytes from UploadFile
    image_bytes = await image.read()

    if not image_bytes:
        raise HTTPException(status_code=400, detail="Image file is empty")
    if len(image_bytes) > MAX_IMAGE_SIZE_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"Image too large ({len(image_bytes) / (1024*1024):.1f} MB). Max is {MAX_IMAGE_SIZE_BYTES / (1024*1024):.0f} MB."
        )

    # Run sync service in a thread to avoid blocking the event loop
    result = await asyncio.to_thread(
        process_image_test,
        image_bytes=image_bytes,
        question=question,
        user_id=user["sub"],
        collection_id=collection_id,
        filename=image.filename or "image.jpg",
        content_type=image.content_type or "image/jpeg",
    )

    return result
