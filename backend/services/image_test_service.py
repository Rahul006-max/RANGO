"""Image test service for RAG vision accuracy testing."""

from __future__ import annotations

import os
import time
import uuid
from typing import Tuple

from config import get_settings
from core.llm import (
    FAILURE_LLM,
    FAILURE_STORAGE,
    answer_from_context,
    calculate_confidence,
    check_vision_model,
    generate_image_description,
    llm_grade_confidence,
)
from dependencies import get_supabase_admin
from utils.timing_utils import elapsed_ms as _elapsed_ms, now_ms
from utils.token_utils import estimate_cost_usd

settings = get_settings()

SUPPORTED_IMAGE_TYPES = frozenset(["image/png", "image/jpeg", "image/webp", "image/gif"])
SIGNED_URL_EXPIRY_SEC = 3600


def build_empty_metrics(start_time: float | None = None) -> dict:
    total_ms = 0
    if start_time is not None:
        total_ms = int((time.perf_counter() - start_time) * 1000)
    return {
        "latency": {"vision_ms": 0, "llm_ms": 0, "total_ms": total_ms},
        "tokens": {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
            "estimated_cost_usd": 0.0,
            "model": settings.groq_model,
        },
    }


def upload_image_to_supabase(
    image_bytes: bytes,
    user_id: str,
    collection_id: str | None,
    timestamp: int,
    file_ext: str,
    content_type: str = "image/jpeg",
) -> str | None:
    supabase_admin = get_supabase_admin()
    if not supabase_admin:
        return None

    storage_path = f"{user_id}/{collection_id or 'standalone'}/{timestamp}_{uuid.uuid4().hex[:8]}{file_ext}"

    try:
        try:
            supabase_admin.storage.from_(settings.image_storage_bucket).upload(
                storage_path,
                image_bytes,
                {"content-type": content_type},
            )
        except Exception as upload_err:
            err_msg = str(upload_err).lower()
            if "not found" in err_msg or "does not exist" in err_msg:
                print(f"[WARN] Bucket '{settings.image_storage_bucket}' missing, creating...")
                supabase_admin.storage.create_bucket(settings.image_storage_bucket, {"public": False})
                supabase_admin.storage.from_(settings.image_storage_bucket).upload(
                    storage_path,
                    image_bytes,
                    {"content-type": content_type},
                )
            else:
                raise

        signed = supabase_admin.storage.from_(settings.image_storage_bucket).create_signed_url(
            storage_path,
            SIGNED_URL_EXPIRY_SEC,
        )
        if isinstance(signed, dict):
            return signed.get("signedURL") or signed.get("signedUrl") or signed.get("signed_url")
        return getattr(signed, "signed_url", None) or getattr(signed, "signedURL", None)
    except Exception as exc:
        print(f"[WARN] Supabase image upload failed ({FAILURE_STORAGE}): {exc}")
        return None


def process_image_test(
    image_bytes: bytes,
    question: str,
    user_id: str,
    collection_id: str | None,
    filename: str,
    content_type: str = "image/jpeg",
) -> dict:
    start_total = time.perf_counter()
    failure_type = None

    # Preprocess
    t_preprocess_start = now_ms()
    os.makedirs(settings.image_upload_root, exist_ok=True)
    timestamp = int(time.time() * 1000)
    file_ext = os.path.splitext(filename or "")[1] or ".jpg"
    local_path = os.path.join(settings.image_upload_root, f"{user_id}_{timestamp}{file_ext}")

    with open(local_path, "wb") as file:
        file.write(image_bytes)

    image_signed_url = upload_image_to_supabase(image_bytes, user_id, collection_id, timestamp, file_ext, content_type)
    supabase_ok = image_signed_url is not None
    if not image_signed_url:
        image_signed_url = f"local://{local_path}"
        print(f"[WARN] Using local fallback URL: {local_path}")
    elif os.path.exists(local_path):
        # Clean up local file after successful Supabase upload
        try:
            os.remove(local_path)
        except OSError:
            pass

    vision_preprocess_ms = _elapsed_ms(t_preprocess_start)

    # Vision model
    vision_available = check_vision_model()
    t_vision_model_start = now_ms()

    if vision_available:
        extracted_description, vision_failure = generate_image_description(image_bytes)
    else:
        extracted_description, vision_failure = "", "vision_unavailable"

    vision_model_ms = _elapsed_ms(t_vision_model_start)

    if vision_failure:
        failure_type = vision_failure
        extracted_description = (
            f"[Vision unavailable] Image saved. File: {filename}. "
            f"Ensure GROQ_API_KEY is set in backend/.env."
        )
        print(f"[WARN] Vision step failed: {vision_failure}")

    # LLM answer
    t_llm_start = now_ms()
    final_answer, token_usage, llm_failure = answer_from_context(question, extracted_description)
    vision_llm_ms = _elapsed_ms(t_llm_start)

    if llm_failure:
        failure_type = failure_type or llm_failure
        final_answer = f"[LLM unavailable] Question: '{question}'. Description: {extracted_description[:200]}"
        print(f"[WARN] LLM step failed: {llm_failure}")

    # Confidence — LLM self-grades how well the answer is supported by the description
    confidence_score = llm_grade_confidence(question, extracted_description, final_answer, failure_type)

    # Metrics
    total_ms = round((time.perf_counter() - start_total) * 1000, 2)
    metrics = {
        "latency": {
            "vision_preprocess_ms": round(vision_preprocess_ms, 2),
            "vision_model_ms": round(vision_model_ms, 2),
            "vision_llm_ms": round(vision_llm_ms, 2),
            "vision_total_ms": round(total_ms, 2),
            "vision_ms": round(vision_model_ms, 2),
            "llm_ms": round(vision_llm_ms, 2),
            "total_ms": round(total_ms, 2),
        },
        "tokens": {
            "prompt_tokens": token_usage.get("prompt_tokens", 0),
            "completion_tokens": token_usage.get("completion_tokens", 0),
            "total_tokens": token_usage.get("total_tokens", 0),
            "estimated_cost_usd": estimate_cost_usd(token_usage, model=token_usage.get("model", settings.groq_model)),
            "model": token_usage.get("model", settings.groq_model),
        },
    }

    return {
        "ok": True,
        "image_signed_url": image_signed_url,
        "question": question,
        "extracted_description": extracted_description,
        "final_answer": final_answer,
        "confidence_score": round(confidence_score, 1),
        "metrics": metrics,
        "failure_type": failure_type,
    }
